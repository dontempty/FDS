# FDS Engine Room 시뮬레이션 — 조정 가능한 조건

**논문**: Lan et al. 2023, *Effects of ventilation system design on flame behavior and smoke characteristics for mitigating marine engine room fire hazards*, Ocean Engineering 281:114890

**범위**: 형상 (도메인, 벽, 문, 장비, vent 위치, fire 위치)은 고정. 본 문서는 사용자가 튜닝할 수 있는 모든 파라미터를 정리합니다.

## ⚠️ 고정 (수정 금지)

다음 형상 파라미터는 **변경 금지** — Lan 2023 Fig 1에 정박되어 있어 튜닝 대상이 아닙니다:

| 카테고리 | 항목 | 고정 위치 |
|---|---|---|
| **도메인** | 외부 cabin 경계 | 0–13 m × 0–10 m × 0–3 m |
| **외부 벽** | outer_south, outer_north, outer_east, outer_west (0.2 m 두께) | y=0–0.2 / 9.8–10, x=0–0.2 / 12.8–13 |
| **내부 벽** | osr_north_wall + 7 partition walls (rooms 1–5) | `gen_engine_room.py`의 `default_walls()` 참고 |
| **문 (HOLE 개구)** | door1 (Room1↔MER), door2 (OSR↔MER) | door1: x=2.2–2.6, y=8.2–9.1, z=0–2 ; door2: x=7.5–8.5, y=2.7–3.1, z=0–2 |
| **장비** | main_engine, fuel_oil_supply, preheater | `default_equipment()` 참고 |
| **Fire footprint** | 1×1 m pool, OSR 바닥 | x=7.5–8.5, y=1.0–2.0, z=0 |
| **Vent 위치** | 4 inlets (top) + 4 outlets (bottom), Method 2 | 각각 0.6 × 0.6 m, `vents_for_method(2)` 참고 |
| **환기 방법** | Method 2 (paper Table 4 No.3) | 2로 고정 |
| **환기 속도** | 각 vent 법선 속도 | **1.0 m/s** 고정 |
| **Vent 부호 규약** | sign-flip ON (`vent_intake VEL=−1`) | BNDF로 inlet=SUPPLY 검증 완료 |
| **공급 공기 온도** | `vent_intake TMP_FRONT` | **20.0 °C** 고정 (paper 주위 공기) |

이러한 항목을 변경하는 CLI flag (`--xb`, `--fire-xb`, `--close-osr-mer-door`, `--vent-z-swap`, `--ventilation-method`, `--ventilation-velocity`, `--no-vent-sign-flip`) — **사용 금지**.

---

## 1. 격자 & 시간

| 파라미터 | 현재 값 | 설명 / 효과 |
|---|---|---|
| `IJK` (mesh 해상도) | M1: 78×60×18 (84k) … M6: 208×160×48 (1.6M) | 미세할수록 정확도 ↑, 비용 ↑ |
| `MESH_SPLIT` (MPI ranks) | M1: 2×2×1 (4 ranks) … M5: 2×7×2 (28) | IJK를 정확히 나눠야 함 |
| `T_END` | 300 s | paper Fig 5 검증 기간 |
| `DT_DEVC` | 1 s | DEVC 샘플링 주기 (출력만) |
| `DT_HRR` | 1 s | HRR 출력 주기 |
| `DT_SLCF` | 10 s | Slice 파일 출력 주기 (시각화) |
| `STATISTICS_START` | 100 s | `_avg` 컬럼 시간평균 시작 |

**격자 수렴 (현재 baseline 기준)**:

| Mesh | Cells | Δcell (m) | +1m mean\|ΔT\| vs paper | +0.5m mean\|ΔT\| vs paper |
|---|---|---|---|---|
| M1 | 84 k | 0.167 | 7.9 °C | 10.6 °C |
| M3 | 390 k | 0.100 | 26.2 °C | 6.8 °C |
| M5 | 1.07 M | 0.072 | 20.7 °C | 8.1 °C |
| M6 | 1.60 M | 0.063 | 21.8 °C | 8.1 °C |

Cauchy 잔차 M5→M6 = 8.3 °C (+1m) / 7.8 °C (+0.5m) → M5/M6 수준에서 격자 수렴됨.

---

## 2. Fire — 화학 & 복사

| 파라미터 | 현재 값 | 설명 / 효과 |
|---|---|---|
| `FUEL` | `N-HEPTANE` | paper의 디젤 surrogate |
| `HEAT_OF_COMBUSTION` | 42 600 kJ/kg | paper Table 2 (FDS N-Heptane에 대해 고정) |
| `HRR_PEAK_KW` | **863 kW** | paper Eq (2): Q = m'·(1−e⁻ᵏᴰ)·ΔH·χ_chem·(π/4)·D² |
| HRRPUA | 863 kW/m² (1×1 m pool) | HRR_PEAK_KW / fire_area 자동 계산 |
| `HRR_T2_TPEAK` | 60 s | t² 성장 시간: Q(t) = (t/60)²·863, t<60s |
| `HRR_T2_POINTS` | 6 | t² ramp anchor 점 수 |
| **`KAPPA0`** | **1.7 m⁻¹** | paper Table 2 일정 흡수 계수. **↑ → 가스상 IR 흡수 ↑ → smoke layer 더 hot** |
| `RADIATIVE_FRACTION` | **0.3** | paper Table 2. ↑ → 복사 손실 ↑, 대류 가열 ↓ |
| `SOOT_YIELD` | 0.05 | Soot 질량 생성 (visibility 영향) |
| `CO_YIELD` | 0.02 | CO 질량 생성 |
| `TMP_FRONT` (fire SURF) | 400 °C | Fire 초기 표면 T (cosmetic; HRR이 열 동인) |

**민감도 힌트**:
- KAPPA0 sweep 0.5 → 3.0 → 천장 smoke layer T 강력 변조
- RADIATIVE_FRACTION → 가스 vs 복사 가열 비율 영향

---

## 3. 벽 열물성

모든 STEEL 표면은 동일 MATL 정의 공유 (paper Table 1):

```fortran
&MATL ID='STEEL'
      DENSITY=7850.0 kg/m³
      SPECIFIC_HEAT=0.46 kJ/kg·K
      CONDUCTIVITY=45.8 W/m·K
      EMISSIVITY=0.95 /
```

### 표면별 SURF 정의:

| Surface 라벨 | MATL | THICKNESS | BACKING | COLOR | 적용 위치 |
|---|---|---|---|---|---|
| `surf_floor_ceiling` (`DEFAULT=.TRUE.`) | STEEL | **0.01 m** | INSULATED | GRAY | 바닥 + 천장 + 명시 SURF 없는 모든 OBST |
| `surf_wall_white` | STEEL | **0.2 m** | EXPOSED | WHITE | osr_north_wall (OSR↔MER 격벽) |
| `surf_eq_purple` | STEEL | 0.01 m | INSULATED | PURPLE | main_engine + fuel_oil_supply + preheater |
| `surf_wall_coldsink` (`--cold-walls` 시) | STEEL | 0.01 m | INSULATED | YELLOW | 7 partition walls (rooms 1-5) |

### 표면별 튜닝 가능 파라미터:

| 파라미터 | 옵션 | 효과 |
|---|---|---|
| `MATL_ID` | STEEL / CONCRETE / custom | 다른 ρ, cp, k 물성 |
| `THICKNESS` | 0.001 m – 0.3 m | 두꺼울수록 열용량 ↑, 가열 느림 |
| `BACKING` | `EXPOSED` / `INSULATED` | EXPOSED: 후면 가스 노출, INSULATED: 후면 열손실 없음 |
| `TMP_FRONT` (MATL_ID 없음) | scalar °C | **Isothermal cold sink** — 표면 T를 이 값으로 강제 (e.g. 20°C) |
| `EMISSIVITY` (MATL 통해) | 0–1 | IR 방출/흡수 |

### Engine 특수 케이스:

| 모드 | SURF 설정 |
|---|---|
| Default (baseline) | `MATL_ID='STEEL', THICKNESS=0.01, BACKING='INSULATED'` — engine 자유 가열 |
| `--engine-tmp 20` | `TMP_FRONT=20.0`만 (MATL_ID 없음) — **isothermal 20°C cold sink** |

### Partition walls (rooms 1–5) 특수 케이스:

| 모드 | 동작 |
|---|---|
| Default (flag 없음) | `INERT` — FDS 기본 cold sink at TMPA (20°C); 뒤쪽 방이 사실상 20°C 유지 |
| `--cold-walls` | INSULATED steel 0.01 m, YELLOW — 표면은 자유 가열, 뒤쪽 방으로 열 전달 안 됨 |

---

## 4. 환기 ⚠️ **잠금 — 수정 금지**

모든 환기 관련 파라미터는 paper Method 2 baseline으로 고정:

| 파라미터 | **잠금 값** | 비고 |
|---|---|---|
| `VENTILATION_METHOD` | **2** | paper Table 4 No.3: 4 inlets + 4 outlets |
| `VENTILATION_VELOCITY` | **1.0 m/s** | paper Method 2 |
| `vent_intake` `TMP_FRONT` | **20.0 °C** | 공급 공기 온도 (cold ambient) |
| Sign-flip | **flip ON** (default) | `vent_intake VEL=−1`, `vent_exhaust VEL=+1` |

### 검증된 흐름 방향 (BNDF V-성분 샘플링, t≥20s 평균):

| Vent | 위치 | 기본 flip 동작 |
|---|---|---|
| inlet_01..04 (top, z=2.4–3.0) | outer_south + osr_north_wall | **IN → room** (cold 20°C 공급, V≈+0.6 ~ +0.8 m/s) |
| outlet_01..04 (bottom, z=0–0.6) | osr_north + outer_north | **OUT → solid** (hot smoke 배출, V≈+0.3 ~ +0.7 m/s) |

→ **표준 displacement 환기** (top 공급, bottom 배기 — 물리적 정확).

**검증**: BNDF 표면 온도 (engine cold sink 테스트) + PBZ slice V-성분 vent 위치 샘플링 (`/tmp/check_vent_v2.py`, flip vs no-flip 두 케이스 비교).

---

## 5. 환경

| 파라미터 | 현재 값 | 설명 |
|---|---|---|
| `TMPA` | **20.0 °C** | 주위 cabin 공기 초기 온도 (paper Table 3, T=293 K) |

---

## 6. 문 & 개구부

형상 고정, 그러나 개념적으로:

| 문 | 위치 (XB) | 상태 |
|---|---|---|
| `door1_main_to_room1` | x=2.2–2.6, y=8.2–9.1, z=0–2 | HOLE (개방) |
| `door2_main_to_osr` | x=7.5–8.5, y=2.7–3.1, z=0–2 | HOLE (개방) |

CLI: `--close-osr-mer-door`로 door2 제거 가능 (단 형상 변경이므로 사용 금지).

---

## 7. CLI Flags 요약

```bash
# 격자 & 시간
--ijk N N N             # 격자 해상도
--mesh-split N N N      # MPI rank 분할
--t-end SECONDS         # 시뮬레이션 시간

# Fire
--hrr-peak KW           # peak HRR
--hrr-t2-tpeak SECONDS  # t² 성장 시간
--hrr-csv PATH          # custom HRR curve
--radiative-fraction X  # 0–1, default 0.3
--fuel NAME             # default N-HEPTANE
--kappa0 X              # 흡수계수 (default 1.7)
--soot-yield X          # default 0.05
--co-yield X            # default 0.02

# 열 경계 (튜닝 가능)
--engine-tmp T          # isothermal engine 표면 T°C
--engine-thickness X    # default 0.01m
--engine-backing X      # EXPOSED|INSULATED
--cold-walls            # 7 partition walls = INSULATED steel YELLOW
--floor-thickness X     # default 0.01m
--floor-backing X       # EXPOSED|INSULATED
--floor-tmp T           # isothermal floor (no MATL)
--divider-thickness X   # default 0.2m
--divider-backing X     # EXPOSED|INSULATED
--divider-inert         # divider = INERT
--walls-tmp T           # isothermal partition walls
--walls-exposed-steel   # partition = EXPOSED steel 0.2m

# ⚠️ 형상 & 환기 — 사용 금지 (사용자 요청으로 잠금)
# --xb x1 x2 y1 y2 z1 z2   # 도메인 경계
# --fire-xb x1 x2 y1 y2    # fire footprint
# --close-osr-mer-door     # door2 HOLE 제거
# --vent-z-swap            # intake/exhaust z 위치 교환
# --ventilation-method N   # 2로 잠금
# --ventilation-velocity V # 1.0 m/s로 잠금
# --no-vent-sign-flip      # sign-flip ON (default)으로 잠금
```

---

## 8. 현재 Baseline (`grid_mesh1_764327`) — 참조 설정

| 항목 | 값 |
|---|---|
| Mesh | 78×60×18 = 84 k cells |
| 도메인 | 13 × 10 × 3 m |
| Fire XB | x=7.5–8.5, y=1.0–2.0 (1×1 m, HRR=863 kW) |
| Door 1 | (2.2–2.6, 8.2–9.1, 0–2.0) MER↔Room1 |
| Door 2 | (7.5–8.5, 2.7–3.1, 0–2.0) MER↔OSR (fire와 정렬) |
| 환기 | Method 2, v=1 m/s, sign-flip ON |
| 바닥/천장 | STEEL 0.01 m INSULATED |
| osr_north_wall | STEEL 0.2 m EXPOSED |
| 기타 내부 벽 | INERT |
| Engine + 장비 | STEEL 0.01 m INSULATED |
| TMPA / KAPPA0 | 20 °C / 1.7 m⁻¹ |
| T_END | 300 s |

---

## 9. 권장 튜닝 방향

격자 수렴 완료 (M5–M6 Cauchy 잔차 ≈ 8 °C). 남은 ~21 °C +1m 센서 paper 격차는 **비격자 파라미터 systematic offset** — 다음 sweep 후보:

| 파라미터 | Sweep 범위 | 가설 |
|---|---|---|
| `KAPPA0` | 0.5 → 3.0 m⁻¹ | κ↑ → 가스상 IR 흡수 ↑ → smoke layer hot |
| `RADIATIVE_FRACTION` | 0.2 → 0.4 | 높을수록 복사 손실 ↑ → 대류 plume cool |
| Floor/ceiling `BACKING` | INSULATED → EXPOSED | deck 통한 열손실 영향 |
| Floor/ceiling `THICKNESS` | 0.01 → 0.2 m | 열용량 ↑ → transient 감쇠 |
| osr_north_wall `BACKING` | EXPOSED → INSULATED | OSR/MER 사이 격벽 열전달 |
| `vent_intake TMP_FRONT` | 15 → 25 °C | 공급 공기 온도 offset |

---

*문서 생성 2026-06-16. 출처: `gen_engine_room.py`, `run_grid_conv.sbatch`, baseline 입력 `grid_mesh1_764327.fds`.*
