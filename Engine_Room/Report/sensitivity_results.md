# 민감도 분석 결과 보고서

**날짜**: 2026-06-16
**분석 대상**: 27개 sensitivity 케이스 + 새 baseline (`grid_mesh1_764327`)
**Reference**: paper Mesh5 (Lan 2023, ref_Mesh5.csv, 16 점)
**Mesh**: M1 (78×60×18 = 84k cells, 4 MPI ranks)
**T_END**: 300 s, statistics from t=100s

---

## 1. Baseline 결과 (paper와의 격차)

| Offset | low \[0,1\] | mid \[1,2\] | high \[2,3\] | full \[0,3\] | T_floor | T_mid | T_ceil |
|---|---|---|---|---|---|---|---|
| **+1.0m** | **27.4 °C** | 19.2 | 10.2 | 19.0 | 47.5°C | 140.3°C | 214.6°C |
| **+0.5m** | 18.9 | 17.1 | 8.4 | 14.2 | 63.6°C | 143.1°C | 229.2°C |

**핵심 관찰**:
- **paper 격차는 floor 영역 (z=[0,1])에 가장 크게 집중** (+1m에서 27.4°C)
- 천장 영역 (z=[2,3])은 격차 작음 (10.2°C)
- **모델의 결손은 주로 floor 부근**

---

## 2. Paper에 가장 가까운 케이스 (band별 TOP)

### LOW \[0, 1\] — floor 부근 (paper 격차 가장 큼)
| Rank | Case | mean (°C) | 변경 내용 |
|---|---|---|---|
| **1** | **sens_B2_floor_backing_exposed** | **20.4** | floor BACKING=EXPOSED (baseline 27.4 → −7.0) |
| 2 | sens_D1_walls_insulated_steel | 22.2 | partition walls INSULATED steel |
| 3 | sens_A1b_kappa_1p0 | 22.3 | KAPPA0=1.0 |

→ **Floor BACKING=EXPOSED**가 z=0 부근에서 paper에 가장 가까이. 후면 열손실이 floor T 낮춤.

### MID \[1, 2\] — fire plume 중심
| Rank | Case | mean (°C) |
|---|---|---|
| **1** | **sens_E2c_engine_thick_0p2** | **11.4** (baseline 19.2 → −7.8) |
| 2 | sens_D1_walls_insulated_steel | 14.1 |
| 3 | sens_B1a_floor_thick_0p005 | 14.8 |

→ **Engine 두께 0.2m** 또는 **얇은 floor (0.005m)**가 plume 영역에서 paper와 일치.

### HIGH \[2, 3\] — 천장 hot smoke layer
| Rank | Case | mean (°C) |
|---|---|---|
| **1** | **sens_A3b_soot_0p10** | **4.8** (baseline 10.2 → −5.4) |
| 2 | sens_E3_engine_backing_exposed | 8.5 |
| 3 | sens_E2a_engine_thick_0p001 | 9.5 |

→ **SOOT_YIELD 0.10 (2배)**이 ceiling smoke layer를 paper에 가장 가까이. soot 많을수록 복사 ↑.

### FULL \[0, 3\] — 종합
| Rank | Case | mean (°C) |
|---|---|---|
| **1** | **sens_E2c_engine_thick_0p2** | **15.0** |
| 2 | sens_D1_walls_insulated_steel | 16.3 |
| 3 | sens_A1b_kappa_1p0 | 16.5 |

---

## 3. 가장 영향력 있는 변수 (Δ vs baseline)

### LOW 영역 (floor)
| 1 | **sens_A1b KAPPA0=1.0** | Δ = 18.4 °C |
| 2 | sens_E3 engine BACKING=EXPOSED | Δ = 12.0 |
| 3 | sens_A4a HRR=700 | Δ = 9.3 |

### MID 영역 (plume 중심)
| 1 | **sens_A4b HRR=1100** | Δ = 27.8 ← 압도적 |
| 2 | sens_E2c engine_thick=0.2 | Δ = 13.4 |
| 3 | sens_B1c floor_thick=0.2 | Δ = 12.9 |

### HIGH 영역 (천장)
| 1 | **sens_A4b HRR=1100** | Δ = 24.9 |
| 2 | sens_A4a HRR=700 | Δ = 17.0 |
| 3 | sens_E3 engine BACKING=EXPOSED | Δ = 15.1 |

### FULL 종합
| 1 | sens_A4b HRR=1100 | Δ = 19.7 |
| 2 | sens_A1b KAPPA0=1.0 | Δ = 14.9 |
| 3 | sens_A4a HRR=700 | Δ = 12.1 |

---

## 4. 물리적 해석 (변수별 인사이트)

### 🔥 HRR (Group A4) — 모든 band에 강한 영향
- HRR=1100 → 천장 +25 °C, mid +28 °C (자명)
- HRR=700/1100 모두 **paper에서 멀어짐**
- → **paper HRR=863 가정이 거의 정확** (베이스라인 유지가 맞음)

### 💨 KAPPA0 (Group A1) — 비단조, low band 지배
- **KAPPA0=1.0**: Δ_full=14.9°C, **low band에서 특히 강함** (Δ=18°C)
- KAPPA0=0.5나 2.5/3.0은 일관성 떨어짐
- → **paper Table 2 (κ=1.7)보다 κ=1.0이 우리 setup에 더 적합**

### 🌫️ SOOT (Group A3) — 천장에서만 영향
- SOOT=0.10 → ceiling 영역만 paper에 가까이 (4.8 vs 10.2)
- low/mid band 영향 미미
- → soot은 **상층 smoke layer만 변경**, floor 부근엔 영향 X

### 🔧 Engine 두께 (E2) — 비단조, thick=0.2가 best
- thin (0.001, 0.05): 영향 작음
- **thick=0.2**: full=15.0°C, mid에서 paper 가장 가까이 (11.4°C)
- → engine 열용량 충분 → hot gas radiation 흡수 → smoke layer 안정화

### 🏗️ Floor 두께 (B1) — 0.01m baseline이 거의 best
- 0.005m: mid에서 paper 약간 가까이 (14.8°C)
- **0.2m**: 가장 멀어짐 (full=24.2°C) — 두꺼운 floor가 plume cool down
- → 현재 baseline (0.01m) 유지

### 🧱 Floor BACKING (B2) — low band 개선의 핵심
- **EXPOSED**: low 영역에서 paper 가장 가까이 (20.4°C, baseline 27.4 → −7.0)
- INSULATED (baseline): 후면 손실 없어 floor 너무 hot
- → **`--floor-backing EXPOSED`로 변경 권장**

### 🧊 Floor isothermal cold sink (B3)
- floor 20°C 고정 → 너무 차가워져서 paper에서 멀어짐 (22.9°C low)
- → 단순 cold sink는 over-correction

### 🏛️ Partition walls (D1) — 일관된 개선
- INSULATED steel → 모든 band에서 일관되게 paper에 가까이
- 단 Δ=6.9°C 정도, 강한 영향 아님
- → **`--cold-walls` 권장**

### 🌡️ Engine BACKING=EXPOSED (E3)
- low/high 양쪽에서 paper에 가까이
- 후면 열손실로 ceiling 영역도 cool down

---

## 5. 종합 결론

### 단일 변경 best 3
1. **`engine_thickness=0.2 m`** (E2c) — full=15.04°C (baseline 19.05에서 −4°C)
2. **`partition walls INSULATED steel`** (D1, `--cold-walls`) — full=16.28°C
3. **`KAPPA0=1.0`** (A1b) — full=16.51°C, low band에서 특히 강함 (Δ=18°C)

### Band별 best 변경
| Band | 추천 변경 | 효과 (°C 개선) |
|---|---|---|
| low \[0, 1\] | floor BACKING=EXPOSED | −7.0 |
| low \[0, 1\] | KAPPA0=1.0 | −5.1 |
| mid \[1, 2\] | engine_thick=0.2 | −7.8 |
| high \[2, 3\] | SOOT=0.10 | −5.4 |
| 일관 개선 | partition walls INSULATED | −3 |

### 거의 영향 없는 변수 (튜닝 의미 없음)
- D2 partition cold sink 20°C (`Δ=0` — 기본 INERT와 동일)
- E2b engine_thick=0.05 (`Δ=3.5`)
- B2 floor BACKING=EXPOSED (low 외 효과 작음)
- C3 divider INERT (`Δ=5.0`)

---

## 6. 결합 최적화 후보 (OPT1)

위 분석을 종합한 결합 케이스 — **`sens_OPT1_combined`** 제출 (Job 764799):

```bash
--engine-thickness 0.2        # E2c
--cold-walls                  # D1 (INSULATED partition)
--kappa0 1.0                  # A1b
--soot-yield 0.10             # A3b
--floor-backing EXPOSED       # B2
```

### Superposition 가정 예측 (선형 효과 가정, 실제론 비선형)
- baseline full = 19.05 °C
- −8.7 (E2c engine_thick) − 6.9 (D1 walls) − 14.9 (A1b KAPPA0) − 7.7 (A3b SOOT) − 5.3 (B2 floor)
- = **−24.5 °C → 음수 (over-correction 가능성)**
- 실제 결합 효과는 비선형이므로 **검증 필요**

### 예상 시나리오 vs 실제
| 시나리오 | OPT1 결과 (full) | 해석 |
|---|---|---|
| 이상적 | ~5°C | superposition 성립 |
| 부분 cancellation | ~10°C | 일부 변수 상쇄 |
| over-correction | <5°C 또는 paper 너머 | 일부 변수 과도 |
| 약한 결합 | ~15°C | 단일 best와 비슷 |
| **실제 (OPT1)** | **19.10°C** | **변수 효과 완전 상쇄** ✗ |

### OPT1 실제 결과 (Job 764799)

| Band | OPT1 | baseline | paper-gap 변화 |
|---|---|---|---|
| **low \[0, 1\]** | 23.72 | 27.39 | **−3.67** ✓ 개선 |
| **mid \[1, 2\]** | 23.68 | 19.16 | **+4.52** ✗ 악화 |
| **high \[2, 3\]** | 14.34 | 10.20 | **+4.14** ✗ 악화 |
| **full \[0, 3\]** | 19.10 | 19.05 | +0.05 (변화 없음) |

| Point | OPT1 | baseline | paper |
|---|---|---|---|
| T_floor (z≈0) | **73.7°C** | 47.5 | 51.2 — paper에서 멀어짐 ✗ |
| T_mid (z=1.5) | 165.3 | 153.7 | 169.6 — **paper에 가까워짐** ✓ |
| T_ceil (z≈3) | 221.6 | 217.0 | 247.5 — 약간 개선 |

### 결합 실패 원인 분석

**5개 best 변수가 강하게 상호 상쇄됨**:

1. **SOOT=0.10 vs KAPPA0=1.0**: 정반대 방향 작용
   - SOOT↑ → 더 많은 그을음 → 복사 ↑
   - KAPPA0↓ → 가스상 흡수계수 ↓ → 복사 ↓
   - 두 효과 거의 cancel out

2. **engine_thick=0.2 (mid 개선) + floor EXPOSED (low 개선)**:
   - Engine 큰 열용량이 plume radiation 흡수
   - Floor 후면 열손실로 floor 가스 cool down
   - 두 작용이 화원 주변에서 충돌 → mid band 악화

3. **T_floor=73.7°C ↑↑**: SOOT=0.10이 floor 복사 가열 압도
   - floor EXPOSED만으로는 SOOT 증가의 복사 가열 못 막음

### 결론 — **단순 superposition은 성립하지 않음**

- 단일 변수 best (engine_thick=0.2 → full=15.04°C)가 OPT1 (19.10°C)보다 **더 좋음**
- 결합 시 변수 간 강한 interaction → 효과 예측 불가
- → **2-variable interaction sweep** 또는 **subset 결합** 필요

### 추천 후속 작업
1. **OPT2**: 결합 변수 축소 (e.g., engine_thick=0.2 + cold-walls only)
2. **OPT3**: SOOT=0.10 제외 (KAPPA0과 충돌)
3. **2-way sweep**: best 2개 변수 (E2c + D1) 조합만 테스트

---

## 7. 남은 격차 & 후속 권장

### 현재 한계
- 모든 단일 변경이 **baseline 19.05 → 최대 15.04**까지만 (~4°C 개선)
- **남은 systematic gap ~ 15°C** 

### 가능한 원인 (분석 외 요인)
1. **Monitor x 위치**: 현재 x=8.0 vs paper PBX=8.10/8.40 → 0.1~0.4 m 차이
2. **Grid resolution**: M1 (84k) → M3/M5 사용 시 paper와 더 일치 가능 (paper는 fine mesh)
3. **Mesh 정의 차이**: paper "Mesh5"의 정확한 cell 크기 미확인
4. **Vent position 미세 차이**

### 후속 작업 권장
1. **OPT1 결과 분석** (Job 764799 완료 시)
2. **OPT1을 M3/M5 mesh로 격자 수렴 확인**
3. Monitor 위치 검토 — x=8.0 → 8.10 (paper PBX 일치)
4. 결합 효과가 실제로 어떻게 나타나는지에 따라 2차 fine-tune sweep

---

## 8. 산출 파일

### 그래프
```
analysis/sensitivity/sensitivity/
├── bars/    (8)  — z-band별 ranking bar chart
├── A/       (10) — Fire chem/rad sweep + T(z) overlay
├── B/       (4)  — Floor sweep + T(z)
├── C/       (4)  — Divider sweep + T(z)
├── D/       (2)  — Walls T(z) overlay
└── E/       (4)  — Engine sweep + T(z)
```

### 데이터 표
- `analysis/sensitivity/table_summary.csv` — 28 케이스 모든 metric
- `analysis/sensitivity/cases.json` — T(z) profile 포함

### 시각화
- `analysis/sensitivity/visualizations/{baseline, A, B, C, D, E}/` — 케이스별 5 slice (XZ, YZ, 3× XY) × 28 = 140 PNGs

---

*보고서 자동 생성, Job 764799 (OPT1 combined) 완료 후 결과 추가 예정.*
