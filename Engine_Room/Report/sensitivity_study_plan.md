# 민감도 분석 계획 — FDS Engine Room

**목표**: 튜닝 가능한 *각각의* 경계/물성/복사 파라미터가 T(z) 프로파일 (+0.5m, +1.0m)에 미치는 영향을 Lan 2023 Fig 5 대비 정량화. **각 케이스는 baseline에서 변수 하나만 변경**, 나머지는 동일하게 유지.

**참고**: [tunable_conditions.md](tunable_conditions.md) — 잠금 vs 튜닝 가능 파라미터 목록

---

## Baseline (기준 케이스)

| 항목 | 값 | 비고 |
|---|---|---|
| Job | **grid_mesh1_759273** | M1, T_END=300 s |
| Mesh | 78×60×18 (84 k cells, 4 ranks) | |
| Fire | x=7.9–8.9, HRR_PEAK = 863 kW | 형상 잠금 |
| KAPPA0 | 1.7 m⁻¹ | paper Table 2 |
| RADIATIVE_FRACTION | 0.3 | |
| SOOT_YIELD / CO_YIELD | 0.05 / 0.02 | |
| Floor/ceiling SURF | STEEL, 0.01 m, INSULATED, GRAY | DEFAULT=.TRUE. |
| osr_north_wall SURF | STEEL, **0.2 m**, EXPOSED, WHITE | 유일한 EXPOSED steel |
| 기타 내부 벽 | INERT | FDS 기본 cold-sink |
| Engine + 부속 | STEEL, 0.01 m, INSULATED, PURPLE | |
| Ventilation | Method 2, v=1 m/s, flip ON (잠금) | |
| TMPA | 20.0 °C | |
| Mean \|ΔT\| vs paper | **+1m: 7.9 °C, +0.5m: 10.6 °C** | 기준 지표 |

---

## 케이스 명명 규칙

```
sens_<group><level>_<variable>_<value>
```

| Group | 변수 그룹 |
|---|---|
| A | Fire 화학 & 복사 |
| B | Floor / ceiling |
| C | osr_north_wall (OSR↔MER divider) |
| D | 기타 내부 벽 (현재 INERT) |
| E | Engine + 부속 |

예시:
- `sens_A1a_kappa_0p5` → KAPPA0 sweep, 레벨 0.5 m⁻¹
- `sens_B2_floor_backing_exposed` → floor/ceiling BACKING 변경
- `sens_E1_engine_tmp20` → engine isothermal 20°C

각 출력 디렉토리: `Results/<case_id>/<case_id>_*.csv`, `_devc.csv` 등

> ⚠️ **CHID 명명 규약**: FDS는 CHID에 `.` (마침표) 금지 → 소수점은 `p`로 표기 (예: `0.5` → `0p5`)

---

## 민감도 매트릭스

### Group A — Fire 화학·복사 (영향 최대 예상)

| Case ID | 변수 | Baseline | 시험값 | CLI / 소스 |
|---|---|---|---|---|
| `sens_A1a_kappa_0p5` | KAPPA0 | 1.7 | **0.5** | `--kappa0 0.5` |
| `sens_A1b_kappa_1p0` | KAPPA0 | 1.7 | 1.0 | |
| `sens_A1c_kappa_2p5` | KAPPA0 | 1.7 | 2.5 | |
| `sens_A1d_kappa_3p0` | KAPPA0 | 1.7 | 3.0 | |
| `sens_A2a_radfrac_0p2` | RADIATIVE_FRACTION | 0.3 | **0.2** | `--radiative-fraction 0.2` |
| `sens_A2b_radfrac_0p4` | RADIATIVE_FRACTION | 0.3 | 0.4 | `--radiative-fraction 0.4` |
| `sens_A3a_soot_0p02` | SOOT_YIELD | 0.05 | **0.02** | `--soot-yield 0.02` |
| `sens_A3b_soot_0p10` | SOOT_YIELD | 0.05 | 0.10 | `--soot-yield 0.10` |
| `sens_A4a_hrr_700` | HRR_PEAK_KW | 863 | 700 | `--hrr-peak 700` |
| `sens_A4b_hrr_1100` | HRR_PEAK_KW | 863 | 1100 | `--hrr-peak 1100` |

**소계**: 10 케이스

### Group B — Floor & Ceiling SURF

| Case ID | 변수 | Baseline | 시험값 |
|---|---|---|---|
| `sens_B1a_floor_thick_0p005` | THICKNESS | 0.01 | **0.005** m |
| `sens_B1b_floor_thick_0p05` | THICKNESS | 0.01 | 0.05 m |
| `sens_B1c_floor_thick_0p2` | THICKNESS | 0.01 | 0.2 m |
| `sens_B2_floor_backing_exposed` | BACKING | INSULATED | EXPOSED |
| `sens_B3_floor_coldsink20` | (모델) | STEEL+INSULATED | **TMP_FRONT=20** (isothermal) |

**소계**: 5 케이스 (B2b INSULATED는 baseline과 동일하므로 제거)

### Group C — osr_north_wall (OSR↔MER 강철 격벽)

| Case ID | 변수 | Baseline | 시험값 |
|---|---|---|---|
| `sens_C1a_divider_thick_0p05` | THICKNESS | 0.2 | 0.05 m |
| `sens_C1b_divider_thick_0p5` | THICKNESS | 0.2 | 0.5 m |
| `sens_C2_divider_backing_insulated` | BACKING | EXPOSED | INSULATED |
| `sens_C3_divider_inert` | SURF | steel SURF | INERT (cold sink) |

**소계**: 4 케이스

### Group D — 기타 내부 벽 (방 partition, 현재 INERT)

| Case ID | 변수 | Baseline | 시험값 |
|---|---|---|---|
| `sens_D1_walls_insulated_steel` | SURF | INERT | INSULATED steel 0.01 m (`--cold-walls`) |
| `sens_D2_walls_coldsink20` | SURF | INERT | isothermal 20°C (`--walls-tmp 20`) |
| `sens_D3_walls_exposed_steel` | SURF | INERT | EXPOSED steel 0.2 m (`--walls-exposed-steel`) |

**소계**: 3 케이스

### Group E — Engine + 부속

| Case ID | 변수 | Baseline | 시험값 |
|---|---|---|---|
| `sens_E1_engine_tmp20` | 모델 | STEEL INSULATED | **TMP_FRONT=20** (`--engine-tmp 20`) |
| `sens_E2a_engine_thick_0p001` | THICKNESS | 0.01 | 0.001 m |
| `sens_E2b_engine_thick_0p05` | THICKNESS | 0.01 | 0.05 m |
| `sens_E2c_engine_thick_0p2` | THICKNESS | 0.01 | 0.2 m |
| `sens_E3_engine_backing_exposed` | BACKING | INSULATED | EXPOSED |

**소계**: 5 케이스

### Group F — Mesh (별도 격자 수렴 연구로 이미 완료)

| Case | Job | Cells |
|---|---|---|
| M1 baseline | 759273 | 84 k |
| M3 | 759807 | 390 k |
| M5 | 759808 | 1.07 M |
| M6 | 760359 | 1.60 M |

→ 이미 plot됨 (Cauchy 잔차 분석). 재실행 불필요.

---

## 총 케이스 수

| Group | 케이스 |
|---|---|
| A — Fire 화학/복사 | 10 |
| B — Floor/ceiling | 5 |
| C — osr_north_wall | 4 |
| D — 기타 내부 벽 | 3 |
| E — Engine | 5 |
| **TOTAL 신규 M1 runs** | **27** |

---

## 리소스 추정

| 항목 | 케이스당 | 총 (27 케이스) |
|---|---|---|
| Mesh | 78×60×18 = 84k | — |
| MPI ranks | 4 | — |
| Wall time | ~15 분 | ~7 h sequential |
| KISTI cpu 큐 | 케이스당 4 CPU | 4–6 parallel 안전 |
| Disk 케이스당 | ~20 MB | ~540 MB |

**전략**: 4–6 개 batch 병렬 제출; CPU free 상태에서 sweep 완료 **약 2 시간** wall time.

> 큐 제출 limit 회피 위해 `submit_sensitivity.sh`는 `QOSMaxSubmitJobPerUserLimit` 발생 시 30초 대기 후 재시도하는 retry 로직 포함.

---

## 구현 단계

1. **코드 변경 — `gen_engine_room.py`에 신규 CLI flag 추가**:
   - `--kappa0 FLOAT`
   - `--soot-yield FLOAT`
   - `--co-yield FLOAT`
   - `--floor-thickness FLOAT`
   - `--floor-backing {EXPOSED|INSULATED}`
   - `--floor-tmp FLOAT` (isothermal 모드)
   - `--divider-thickness FLOAT`
   - `--divider-backing ...`
   - `--divider-inert`
   - `--walls-tmp FLOAT`
   - `--walls-exposed-steel`
   - `--engine-thickness FLOAT`
   - `--engine-backing ...`

2. **`submit_sensitivity.sh` wrapper 작성**:
   - 매트릭스를 인라인으로 정의
   - 각 케이스: input 렌더 → 고유 CHID로 sbatch 제출
   - Submit limit 시 30초 대기 후 재시도

3. **Sweep 실행** (~2 h wall time).

4. **결과 집계 — `analyze_sensitivity.py` 작성**:
   - 각 케이스의 `_line.csv` 로드
   - +1m, +0.5m에서 paper 대비 mean \|ΔT\| 계산
   - Baseline (759273) 대비 Δ 계산: `mean(|T_case − T_baseline|)`
   - 표 작성 + 민감도 bar chart plot

5. **산출물**:
   - `Report/sensitivity_results.md` — (케이스, mean \|ΔT\| vs paper, Δ vs baseline) 표
   - `analysis/sensitivity/sensitivity_bars.png` — 순위 bar chart
   - `analysis/sensitivity/T(z)_<group>.png` — 그룹별 overlay plot

---

## 출력 포맷 (계획)

### 민감도 bar chart (offset별 1개)

```
변수                       |  Δ mean|ΔT| vs baseline (°C)
KAPPA0=0.5                 |  ▆▆▆▆▆▆▆▆ +18.2
KAPPA0=3.0                 |  ▆▆▆▆▆ +11.5
RADIATIVE_FRACTION=0.4     |  ▆▆▆ +7.8
floor BACKING=EXPOSED      |  ▆▆ +4.5
engine cold sink 20°C      |  ▆ +2.3
...
```

→ 어떤 파라미터가 T(z)에 가장 큰 영향을 주는지 확인하여 추가 fine-tuning 방향 결정.

### 그룹별 T(z) overlay plot

- Group A/B/C/D/E 각각 1개 plot, 모든 변형 곡선 + paper 참조
- 모양 변화 확인 (예: 천장 vs 바닥 민감도)

---

## 결정 사항 (사용자 확인 사항이었음)

1. ~~**Scope**: 28 케이스 진행할지, 또는 Group A + B만 (16 케이스)?~~ → **27 케이스 전부 진행**
2. **Sweep 범위**: KAPPA0 0.5–3.0, RAD_FRAC 0.2–0.4 등 적절한가? → 진행
3. **CLI flag 추가**: gen_engine_room.py에 13개 flag 추가 OK? → 추가 완료
4. **Mesh**: 모두 M1으로 (빠른 sweep)? → M1 84k cells 사용

---

## 실행 상태 (2026-06-16 갱신)

- ✅ CLI flags 13개 추가 완료
- ✅ Cfg dataclass + build_input() 수정 완료
- ✅ `submit_sensitivity.sh` 작성 + dry-render 검증 통과
- 🔄 **27 케이스 batch 제출 중** (queue limit retry loop)
- ⏳ 모든 완료 후 → `analyze_sensitivity.py` 실행 + `Report/sensitivity_results.md` 작성

---

*초안 2026-06-16. 27 케이스 sweep 진행 중.*
