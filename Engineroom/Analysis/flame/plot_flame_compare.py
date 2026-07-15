#!/usr/bin/env python3
"""
Flame-metric + engine-top temperature comparison for one case series.

Reuses the logic of plot_fig9_10_compare.ipynb and plot_engine_temp_compare.ipynb
but parametrised by SERIES so the two fire-size studies stay separated:

    python3 plot_flame_compare.py peak     # 0.79 m2 fire  -> Analysis/flame/peak/
    python3 plot_flame_compare.py fire1    # 1.0  m2 fire  -> Analysis/flame/fire1/

Both series share the same HRR peak-time sweep (5/10/15/20 s), vents on from t=0.
Outputs (per series subdir): cmp_fig9_Ly.png, cmp_fig10_1_Hf.png,
cmp_fig10_2_thetaz.png, cmp_fig9_10_panel.png, engine_temp_profile_compare.png.
Reference CSVs (Fig9/Fig10_1/Fig10_2/engine_ref) are read from the flame/ top level.
"""
from __future__ import annotations
import sys, warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import fdsreader

plt.rcParams.update({"axes.labelsize": 14, "axes.titlesize": 15,
                     "xtick.labelsize": 11, "ytick.labelsize": 11,
                     "legend.fontsize": 11})

RES = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom/Results")
FLAME = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom/Analysis/flame")

# series -> dict(tag, tmax, win, cases=[(case_dir, label, color, event_time), ...])
# event_time = vertical dotted marker on the time plots (HRR peak time, or vent
# start time for the vent-sweep series).
_C4 = ("#2980b9", "#27ae60", "#e67e22", "#8e44ad")
SERIES = {
    "peak": dict(tag="0.79 m^2 fire, vent t=0", tmax=360.0, win=(300.0, 360.0),
                 cases=[(f"peak{tp:02d}_M5", f"peak @{tp} s", c, tp)
                        for tp, c in zip((5, 10, 15, 20), _C4)]),
    "fire1": dict(tag="1.0 m^2 fire, vent t=0", tmax=360.0, win=(300.0, 360.0),
                  cases=[(f"peak{tp:02d}_fire1_M5", f"peak @{tp} s", c, tp)
                         for tp, c in zip((5, 10, 15, 20), _C4)]),
    # 1 m fire, HRR peak fixed at 10 s, ventilation start swept 20/30/40 s, T_END=300
    "fire1_vent": dict(tag="1.0 m^2 fire, HRR peak 10 s, vent sweep",
                       tmax=300.0, win=(240.0, 300.0),
                       cases=[("fire1_p10_v20_M5", "vent @20 s", "#2980b9", 20),
                              ("fire1_p10_v30_M5", "vent @30 s", "#27ae60", 30),
                              ("fire1_p10_v40_M5", "vent @40 s", "#e67e22", 40)]),
}

# TMAX/WIN 은 main()에서 시리즈별 값으로 다시 대입됨(여기 값은 기본값).
#   TMAX : 시간축 플롯을 그릴 최대 시각 [s]
#   WIN  : 정상상태 평균을 낼 시간창 [s] (예: fire1_vent 는 240~300)
TMAX = 360.0            # rebound per-series in main()
WIN  = (300.0, 360.0)   # rebound per-series in main()
# --- 화염 metric 계산용 상수 (Lan et al. 2023 Fig 9/10 정의) ---
THRESH  = 150.0            # HRRPUV[kW/m³] 임계값: 이 값 초과 셀을 "화염"으로 봄 → L_x, L_y
FIRE_X  = (7.955, 8.845)   # 버너 x 범위. L_x(화염 x-편차)의 기준 중심 계산에만 사용
FIRE_Y  = (1.005, 1.895)   # 화염이 항상 들어있는 y-띠. 이 띠에 걸치는 메쉬만 골라 로드
HF_FRAC = 0.99            # 화염높이 H_f: 누적 HRR 이 전체의 99%에 도달하는 z 를 화염 끝으로
BLOCK   = 30              # 시간축 블록평균 크기(프레임 수): 30프레임을 1점으로 평활화
REF_FILES = {"Ly": "Fig9.csv", "Hf": "Fig10_1.csv", "theta": "Fig10_2.csv"}  # 논문 기준곡선

# --- 엔진 상부 온도 프로파일용 상수 (메인엔진 중심 위 연직선) ---
# 메인엔진 블록 = x[3.5,10], y[5.2,9], z[0,2] → 상판 중심 (6.75, 7.1), 상판 z=2.0
X_ENG, Y_TARGET, Z_LO, Z_HI = 6.75, 7.1, 2.0, 3.0   # x중심, y중심(슬라이스면), z=상판→천장
REF_CSV = "engine_ref.csv"   # 엔진상부 T(z) 논문 기준 (있으면 오버레이)


def block_mean(t, arr, n):
    """시간열(t, arr)을 n개씩 겹치지 않는 블록으로 묶어 각 블록 평균을 반환.
    역할: 매 프레임 노이즈가 큰 화염 metric 곡선을 30프레임 블록평균으로 평활화."""
    t = np.asarray(t, float); arr = np.asarray(arr, float)
    nb = len(arr) // n                       # 만들 수 있는 블록 개수
    if nb == 0:                              # 데이터가 n보다 적으면 전체 평균 1점
        return np.array([np.nanmean(t)]), np.array([np.nanmean(arr)])
    tt = t[:nb*n].reshape(nb, n); aa = arr[:nb*n].reshape(nb, n)   # (블록, n) 로 재배열
    return np.nanmean(tt, axis=1), np.nanmean(aa, axis=1)          # 블록별 평균 → (블록중심시각, 값)


def flame_metrics(sim):
    """3D HRRPUV(단위체적 발열률) 필드에서 시간별 화염 metric 3종을 계산.
    반환: (t, L_x, L_y, H)
      L_x = 화염의 x방향 편차(버너중심 대비), L_y = 화염 y방향 폭,
      H   = 화염 높이(누적 HRR 99% 도달 z).  (Lan et al. 2023 Fig 9/10 정의)
    """
    # HRRPUV 3D smoke 필드와 그 출력 시각들
    s3 = [s for s in sim.smoke_3d if "HRRPUV" in s.quantity.name.upper()][0]
    t  = np.array(s3.times)
    # 화염 y-띠에 걸치는 메쉬만 선택(불필요한 메쉬 로드 방지) → 공통 x/y/z 격자축 구성
    sel = [m for m in sim.meshes
           if m.coordinates["y"][0] < FIRE_Y[1] and m.coordinates["y"][-1] > FIRE_Y[0]]
    x_arr = np.unique(np.concatenate([m.coordinates["x"] for m in sel]))
    y_arr = np.unique(np.concatenate([m.coordinates["y"] for m in sel]))
    z_arr = np.unique(np.concatenate([m.coordinates["z"] for m in sel]))
    dz    = float(np.diff(z_arr).mean())
    # P: z를 따라 최댓값 취한 HRRPUV 투영 (t, x, y) → 평면상 화염 존재(L_x, L_y)용
    # B: y를 따라 적분한 HRRPUV        (t, x, z) → 연직 발열분포(H_f)용
    P = np.zeros((len(t), len(x_arr), len(y_arr)))
    B = np.zeros((len(t), len(x_arr), len(z_arr)))
    for m in sel:
        d  = s3[m].data                       # 이 메쉬의 HRRPUV (t, x, y, z)
        dy = float(np.diff(m.coordinates["y"]).mean())
        pm = d.max(axis=3); qy = d.sum(axis=2) * dy   # z-최대투영 / y-적분
        # 이 메쉬 로컬 좌표를 공통 전역격자 인덱스로 매핑
        ixg = np.clip(np.searchsorted(x_arr, m.coordinates["x"]), 0, len(x_arr)-1)
        iyg = np.clip(np.searchsorted(y_arr, m.coordinates["y"]), 0, len(y_arr)-1)
        izg = np.clip(np.searchsorted(z_arr, m.coordinates["z"]), 0, len(z_arr)-1)
        for a, xg in enumerate(ixg):
            P[:, xg, iyg]  = np.maximum(P[:, xg, iyg], pm[:, a, :])   # 겹치는 메쉬는 최댓값
            B[:, xg, izg] += qy[:, a, :]                             # 겹치는 메쉬는 합산
    XX, _   = np.meshgrid(x_arr, y_arr, indexing="ij")   # x 좌표 그리드(가중평균용)
    xc_burn = 0.5 * (FIRE_X[0] + FIRE_X[1])              # 버너 x 중심 (L_x 기준점)
    # --- 매 시각 L_x, L_y 계산 ---
    L_x = np.zeros(len(t)); L_y = np.zeros(len(t))
    for i in range(len(t)):
        mask = P[i] > THRESH                 # 임계 초과 = 화염 셀
        if not mask.any():
            continue
        iy = np.where(mask.any(axis=0))[0]   # 화염이 존재하는 y 인덱스들
        if len(iy) > 1:
            L_y[i] = y_arr[iy[-1]] - y_arr[iy[0]]        # 화염 y방향 폭
        w = P[i][mask]                                    # HRRPUV 가중치
        L_x[i] = abs((XX[mask]*w).sum()/w.sum() - xc_burn)  # 가중 x중심과 버너중심의 거리
    # --- 매 시각 화염높이 H 계산 ---
    A = B.sum(axis=2) * dz                    # (t, x): x별 총 발열 (연직·y 적분)
    H = np.zeros(len(t))
    for i in range(len(t)):
        a = A[i]
        if a.sum() <= 0:
            continue
        xcen = (x_arr*a).sum()/a.sum()        # 발열 가중 x중심
        ix = int(np.argmin(np.abs(x_arr - xcen)))       # 그 x열에서 연직분포 사용
        cum = np.cumsum(B[i, ix]) * dz; total = cum[-1] # z 누적 발열
        if total > 0:
            iz = int(np.searchsorted(cum, HF_FRAC*total))   # 누적 99% 도달 z 인덱스
            H[i] = z_arr[min(iz, len(z_arr)-1)]             # → 화염 높이
    return t, L_x, L_y, H


def engine_temp_profile(sim):
    """엔진 상판 중심 (x=6.75, y≈7.1) 위 연직선의 T(z), z=2.0~3.0 을 시간평균으로 추출.
    반환: (z, T평균, T표준편차, 실제y슬라이스위치).  밴드(표준편차)는 시간 요동 크기.
    """
    # XZ 평면(y 고정면, orientation==2) TEMPERATURE 슬라이스 중 y=7.1 에 가장 가까운 것
    xz = [s for s in sim.slices
          if s.orientation == 2 and "TEMP" in s.quantity.name.upper()]
    sl = min(xz, key=lambda s: abs(s.extent.y_start - Y_TARGET))
    ext = sl.extent
    T_all = sl.to_global(masked=True, fill=np.nan)   # (t, x, z), 고체셀=NaN
    t_arr = np.asarray(sl.times)
    x_arr = np.linspace(ext.x_start, ext.x_end, T_all.shape[1])   # x 좌표축
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])   # z 좌표축
    ix    = int(np.argmin(np.abs(x_arr - X_ENG)))                 # 엔진중심 x에 가장 가까운 열
    iz_lo = int(np.searchsorted(z_arr, Z_LO))                     # z=2.0(상판) 인덱스
    iz_hi = int(np.searchsorted(z_arr, Z_HI, side="right")) - 1   # z=3.0(천장) 인덱스
    z_sel = z_arr[iz_lo:iz_hi+1]
    # 정상상태 시간창 mask (없으면 마지막 프레임으로 폴백)
    t1 = min(WIN[1], float(t_arr.max()))
    mask = (t_arr >= WIN[0]) & (t_arr <= t1)
    if not mask.any():
        mask = np.array([int(np.argmax(t_arr))])
    # (창내 시간, 엔진중심 x열, z=상판~천장) 추출 → 시간축 평균/표준편차
    T_win = T_all[np.ix_(mask, [ix], np.arange(iz_lo, iz_hi+1))]
    return z_sel, np.nanmean(T_win, axis=0)[0], np.nanstd(T_win, axis=0)[0], float(ext.y_start)


def load_ref(name):
    """flame/ 최상단의 논문 기준 CSV 를 로드(없으면 None). 컬럼=(시간 또는 z, 값)."""
    p = FLAME / name
    return np.loadtxt(p, delimiter=",") if p.exists() else None


def main():
    # 1) 시리즈 결정 (CLI 인자, 기본 fire1). 시리즈별 케이스목록·TMAX·WIN 를 꺼냄
    series = sys.argv[1] if len(sys.argv) > 1 else "fire1"
    if series not in SERIES:
        sys.exit(f"series must be one of {list(SERIES)}")
    global TMAX, WIN
    spec = SERIES[series]
    tag = spec["tag"]; TMAX = spec["tmax"]; WIN = spec["win"]
    OUT = FLAME / series; OUT.mkdir(parents=True, exist_ok=True)   # 출력 하위폴더
    print(f"=== series '{series}' ({tag}) -> {OUT} ===")

    # 2) 각 케이스를 읽어 화염 metric + 엔진상부 T(z) 를 계산해 results 에 축적
    results = {}
    for case, label, color, ev in spec["cases"]:
        print(f"loading {case} ...", flush=True)
        sim = fdsreader.Simulation(str(RES / case))     # Results/<case> 로드
        t, Lx, Ly, Hf = flame_metrics(sim)              # 화염 L_x, L_y, H_f(시간열)
        Lxy = np.sqrt(Lx**2 + Ly**2)                    # 화염 수평 반경
        theta = np.full(len(t), np.nan)                 # 화염 경사각 θ_z
        gz = Hf > 0.05                                  # 화염높이가 유의미할 때만 각도 정의
        theta[gz] = np.degrees(np.arctan2(Lxy[gz], Hf[gz]))   # θ = atan(수평/높이)
        z, T, Tstd, ysl = engine_temp_profile(sim)      # 엔진상부 T(z) 프로파일
        # ev = 이벤트 시각(peak 또는 vent시작) → 나중에 수직 점선 위치로 사용(키명은 'peak')
        results[case] = dict(label=label, color=color, peak=ev,
                             t=t, Ly=Ly, Hf=Hf, theta=theta,
                             z=z, T=T, Tstd=Tstd, y=ysl)
        print(f"  -> {len(t)} frames t=[{t.min():.0f},{t.max():.0f}]s ; "
              f"engine T {np.nanmin(T):.1f}-{np.nanmax(T):.1f} C")

    # 3) 정상상태(WIN) 평균 요약표를 콘솔에 출력 — L_y, H_f, θ_z 와 z=2/2.5/3 온도
    print(f"\nSteady-state {WIN[0]:.0f}-{WIN[1]:.0f} s:")
    print(f"{'case':10s} {'L_y':>7s} {'H_f':>7s} {'theta_z':>8s} "
          f"{'T@2.0':>7s} {'T@2.5':>7s} {'T@3.0':>7s}")
    for tp, r in results.items():
        w = (r["t"] >= WIN[0]) & (r["t"] <= WIN[1])              # 정상상태 시간 마스크
        at = lambda zt: r["T"][int(np.argmin(np.abs(r["z"]-zt)))]  # 특정 z의 온도 조회
        print(f"{r['label']:10s} {np.nanmean(r['Ly'][w]):7.3f} "
              f"{np.nanmean(r['Hf'][w]):7.3f} {np.nanmean(r['theta'][w]):8.1f} "
              f"{at(2.0):7.1f} {at(2.5):7.1f} {at(3.0):7.1f}")

    refs = {k: load_ref(v) for k, v in REF_FILES.items()}   # 논문 기준곡선 3종 로드

    # 4) metric별 개별 시간축 그림 저장 (기준곡선 + 각 케이스 블록평균 + 이벤트 점선)
    def overlay(key, refkey, ylabel, fname):
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ref = refs.get(refkey)
        if ref is not None:                                  # 논문 기준(검은 사각선)
            ax.plot(ref[:, 0], ref[:, 1], "k-s", lw=1.5, ms=4, mfc="none",
                    label="Reference (Lan 2023)")
        for tp, r in results.items():
            m = r["t"] <= TMAX                               # TMAX 까지만
            tb, vb = block_mean(r["t"][m], r[key][m], BLOCK) # 블록평균으로 평활
            ax.plot(tb, vb, "-o", color=r["color"], lw=2.0, ms=4, label=r["label"])
            ax.axvline(r["peak"], color=r["color"], ls=":", lw=1.0, alpha=0.6)  # 이벤트 시각
        ax.set_xlabel("Time (s)"); ax.set_ylabel(ylabel)
        ax.set_xlim(0, TMAX); ax.grid(alpha=0.3)
        ax.legend(loc="best", framealpha=0.95)
        fig.tight_layout(); fig.savefig(OUT / fname, dpi=150); plt.close(fig)
        print("->", OUT / fname)

    overlay("Ly", "Ly", r"$L_y$ (m)", "cmp_fig9_Ly.png")          # 화염 폭
    overlay("Hf", "Hf", r"$H_f$ (m)", "cmp_fig10_1_Hf.png")       # 화염 높이
    overlay("theta", "theta", r"$\theta_z$ (deg)", "cmp_fig10_2_thetaz.png")  # 경사각

    # 5) 위 3개를 한 장(1×3 패널)으로 합쳐 저장 — overlay 와 동일 내용
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.6))
    for ax, (key, refkey, yl) in zip(
            axs, [("Ly", "Ly", r"$L_y$ (m)"), ("Hf", "Hf", r"$H_f$ (m)"),
                  ("theta", "theta", r"$\theta_z$ (deg)")]):
        ref = refs.get(refkey)
        if ref is not None:
            ax.plot(ref[:, 0], ref[:, 1], "k-s", lw=1.5, ms=4, mfc="none",
                    label="Reference (Lan 2023)")
        for tp, r in results.items():
            m = r["t"] <= TMAX
            tb, vb = block_mean(r["t"][m], r[key][m], BLOCK)
            ax.plot(tb, vb, "-o", color=r["color"], lw=2.0, ms=4, label=r["label"])
            ax.axvline(r["peak"], color=r["color"], ls=":", lw=1.0, alpha=0.6)
        ax.set_xlabel("Time (s)"); ax.set_ylabel(yl); ax.set_xlim(0, TMAX); ax.grid(alpha=0.3)
    axs[0].legend(loc="best")
    fig.suptitle(f"Case comparison [{series}: {tag}]  "
                 f"(30-step block avg; dotted line = event time)", fontsize=15)
    fig.tight_layout(); fig.savefig(OUT / "cmp_fig9_10_panel.png", dpi=150); plt.close(fig)
    print("->", OUT / "cmp_fig9_10_panel.png")

    # 6) 엔진 상부 온도 프로파일 T(z) 그림 — 케이스별 곡선 + ±표준편차 밴드
    ref = None
    p = FLAME / REF_CSV
    if p.exists():
        ref = np.loadtxt(p, delimiter=",")   # engine_ref.csv = (T, z) 순서 주의
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for tp, r in results.items():
        ax.plot(r["z"], r["T"], "-o", color=r["color"], lw=1.9, ms=5,
                label=r["label"], zorder=3)                        # 시간평균 T(z)
        ax.fill_between(r["z"], r["T"]-r["Tstd"], r["T"]+r["Tstd"],  # ±시간표준편차 음영
                        color=r["color"], alpha=0.15, zorder=1)
    if ref is not None:                       # 기준 CSV는 (T,z) 라 x=ref[:,1](z), y=ref[:,0](T)
        ax.plot(ref[:, 1], ref[:, 0], "k-s", lw=1.5, ms=5, mfc="none",
                label="Reference", zorder=5)
    ax.set_xlabel("z  (m)"); ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(Z_LO, Z_HI)
    lo = min(np.nanmin(r["T"]-r["Tstd"]) for r in results.values())
    hi = max(np.nanmax(r["T"]+r["Tstd"]) for r in results.values())
    if ref is not None:
        lo = min(lo, float(ref[:, 0].min())); hi = max(hi, float(ref[:, 0].max()))
    ax.set_ylim(max(0, lo-5), hi+8); ax.grid(alpha=0.3)
    ax.legend(loc="upper left", framealpha=0.95,
              title=("vent start" if "vent" in series else "HRR peak time"))
    ax.set_title(f"Engine-top T(z), {WIN[0]:.0f}-{WIN[1]:.0f} s  [{series}: {tag}]",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "engine_temp_profile_compare.png", dpi=150); plt.close(fig)
    print("->", OUT / "engine_temp_profile_compare.png")


if __name__ == "__main__":
    main()
