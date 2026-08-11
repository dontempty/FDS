#!/usr/bin/env python3
"""
1D 배터리 모델(Amesim, MPSE 팀) 산출물을 모사한 더미 CSV 생성기.
=================================================================

브리프 5.1절 "요청 데이터 (CSV)" 스펙을 그대로 따른다.
**실제 1D 데이터가 도착하면 이 스크립트를 실행하지 말고, 같은 컬럼 이름/단위로
된 CSV를 이 디렉터리에 그대로 덮어쓰면 된다.** 상위 노트북
(`../build_fds_input.ipynb`)은 이 CSV만 읽으므로 다른 코드 수정이 필요 없다.

생성 파일
---------
vent_zone1.csv, vent_zone2.csv, vent_zone3.csv
    t_s        : 시간 [s]                        (Δt <= 1 s, 브리프 5.1 필수조건)
    mdot_kg_s  : 벤트가스 질량유량 [kg/s]         (경로 ②)
    T_vent_K   : 벤트가스 온도 [K]                (경로 ② 엔탈피)
    Y_H2 .. Y_C2H4 : 벤트가스 조성 [질량분율]     (SPEC 조성. 합=1-Y_HF)
    Y_HF       : HF 질량분율 [-]                  (독성 추적, 옵션)

casing_heat_flux.csv
    t_s          : 시간 [s]
    q_net_kW_m2  : 케이싱 표면 순 열유속 [kW/m2]  (경로 ①)

thr_1d.csv
    t_s      : 시간 [s]
    THR_MJ   : 1D가 계산한 누적 발열량 [MJ]       (FDS 결과와 정합성 검증용, 8장 #1)

주의: 여기 수치는 전부 브리프의 `[PH]` 플레이스홀더 수준이며 물리적 크기만
      그럴듯하게 맞춰 놓은 것이다. 최종 해석에 그대로 쓰면 안 된다.
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 설정 [PH]
DT = 0.5  # [s]  1D 데이터 시간 해상도 (브리프 요구: Δt <= 1 s)
T_END = 900.0  # [s]

# 존별 열폭주/벤트 시나리오 (브리프 6.2 표)
ZONES = [
    # name,  t_open, t_rise, t_hold, t_fall,  mass_kg,  T_peak_C
    ("zone1", 60.0, 5.0, 180.0, 20.0, 9.0, 620.0),
    ("zone2", 240.0, 5.0, 180.0, 20.0, 9.0, 640.0),
    ("zone3", 420.0, 5.0, 180.0, 20.0, 9.0, 660.0),
]

# 벤트가스 조성 (부피분율 %) — 브리프 6.3
COMP_VOL_PCT = {
    "H2": 28.0,
    "CO": 23.0,
    "CO2": 28.0,
    "CH4": 12.0,
    "C2H4": 9.0,
}
MW = {"H2": 2.016, "CO": 28.010, "CO2": 44.010, "CH4": 16.043, "C2H4": 28.054}
DHC_MJ_KG = {"H2": 120.0, "CO": 10.1, "CO2": 0.0, "CH4": 50.0, "C2H4": 47.2}

Y_HF = 0.005  # 벤트가스 질량의 0.5% — 브리프 6.6 [PH]

# 케이싱 열유속 (경로 ①) — 브리프 6.5
CASING_PEAK_KW_M2 = 5.0
CASING_SHAPE = [(0.0, 0.00), (300.0, 0.30), (600.0, 0.80), (900.0, 1.00)]


def vol_to_mass_fraction(vol_pct: dict) -> dict:
    """부피분율(%) -> 질량분율. Y_i = x_i W_i / sum(x_j W_j)."""
    x = {k: v / sum(vol_pct.values()) for k, v in vol_pct.items()}
    w_mix = sum(x[k] * MW[k] for k in x)
    return {k: x[k] * MW[k] / w_mix for k in x}


_trapz = getattr(np, "trapezoid", None) or np.trapz


def trapezoid(t, t_open, t_rise, t_hold, t_fall):
    """사다리꼴 형상 함수. 최대값 1.0으로 정규화되어 있지 않은 raw shape."""
    f = np.zeros_like(t)
    t1, t2, t3, t4 = t_open, t_open + t_rise, t_open + t_rise + t_hold, t_open + t_rise + t_hold + t_fall
    up = (t >= t1) & (t < t2)
    hold = (t >= t2) & (t < t3)
    dn = (t >= t3) & (t < t4)
    f[up] = (t[up] - t1) / max(t_rise, 1e-12)
    f[hold] = 1.0
    f[dn] = 1.0 - (t[dn] - t3) / max(t_fall, 1e-12)
    return f


def main():
    t = np.arange(0.0, T_END + 0.5 * DT, DT)
    Y = vol_to_mass_fraction(COMP_VOL_PCT)
    dhc_mix = sum(Y[k] * DHC_MJ_KG[k] for k in Y)  # [MJ/kg], 불활성 포함 기준

    print(f"[1D dummy] 유효 분자량      : {sum((v/100)*MW[k] for k,v in COMP_VOL_PCT.items()):.2f} g/mol")
    print(f"[1D dummy] 질량분율         : " + ", ".join(f"{k}={Y[k]:.4f}" for k in Y))
    print(f"[1D dummy] dHc,mix (불활성 포함): {dhc_mix*1000:.0f} kJ/kg")

    thr_total = np.zeros_like(t)

    for name, t_open, t_rise, t_hold, t_fall, mass_kg, tpeak_c in ZONES:
        shape = trapezoid(t, t_open, t_rise, t_hold, t_fall)
        area = _trapz(shape, t)
        mdot = shape * (mass_kg / area)  # [kg/s], 적분값이 정확히 mass_kg

        # 온도: 벤트 개시 직후 급상승 -> 완만한 감쇠. 벤트 없는 구간은 주변온도.
        tvent = np.full_like(t, 293.15)
        active = shape > 0
        tvent[active] = (tpeak_c + 273.15) * (0.7 + 0.3 * shape[active])

        df = pd.DataFrame({"t_s": t, "mdot_kg_s": mdot, "T_vent_K": tvent})
        for k in COMP_VOL_PCT:  # 올해는 시간불변 조성 (브리프 4.2 옵션 (a))
            df[f"Y_{k}"] = Y[k] * (1.0 - Y_HF)
        df["Y_HF"] = Y_HF
        df.to_csv(HERE / f"vent_{name}.csv", index=False, float_format="%.6g")

        thr_total += np.cumsum(mdot * dhc_mix) * DT  # [MJ]
        print(f"[1D dummy] {name}: 방출질량 {_trapz(mdot, t):.2f} kg, "
              f"피크 {mdot.max():.4f} kg/s, 기여 THR {_trapz(mdot, t)*dhc_mix:.1f} MJ")

    pd.DataFrame({"t_s": t, "THR_MJ": thr_total}).to_csv(
        HERE / "thr_1d.csv", index=False, float_format="%.6g")

    # ---- 케이싱 열유속 (경로 ①)
    ts, fs = zip(*CASING_SHAPE)
    q = np.interp(t, ts, fs) * CASING_PEAK_KW_M2
    pd.DataFrame({"t_s": t, "q_net_kW_m2": q}).to_csv(
        HERE / "casing_heat_flux.csv", index=False, float_format="%.6g")

    print(f"[1D dummy] 배터리 기여 총 THR : {thr_total[-1]:.1f} MJ")
    print(f"[1D dummy] 케이싱 피크 열유속 : {q.max():.2f} kW/m2")
    print(f"[1D dummy] 파일 {len(list(HERE.glob('*.csv')))}개 생성 -> {HERE}")


if __name__ == "__main__":
    main()
