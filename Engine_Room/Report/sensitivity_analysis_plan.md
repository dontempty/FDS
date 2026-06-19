# 민감도 분석 계획서

**목적**: 27개 sensitivity 케이스 (+ 새 baseline) 결과를 체계적으로 분석하여 각 파라미터가 T(z) 프로파일에 미치는 영향을 정량화하고, paper Fig 5와의 격차를 줄이는 방향을 도출.

**입력**: `Results/sens_*` (27개) + `Results/grid_mesh1_764189` (새 baseline)

**참고**: `Results_backup_old_geometry/` (옛 geometry), `analysis_backup_old_geometry/`

---

## 1. 분석 차원

각 케이스에서 추출할 metric:

| Metric | 의미 | 용도 |
|---|---|---|
| **T(z) profile** | 16개 균등점 (z=0–3m, step 0.2m) | overlay plot |
| **mean \|ΔT\|_mid vs paper** (z∈[0.95, 2.45]) | 안정 영역 paper 오차 | 절대 정확도 (mid) |
| **max \|ΔT\|_mid vs paper** (z∈[0.95, 2.45]) | 안정 영역 최대 paper 오차 | mid outlier |
| **mean \|ΔT\|_full vs paper** (z∈[0, 3.0]) | **전 영역 paper 오차 (boundary 포함)** | 절대 정확도 (full) |
| **max \|ΔT\|_full vs paper** (z∈[0, 3.0]) | **전 영역 최대 paper 오차** | floor/ceiling outlier |
| **Δ vs baseline_mid** (z∈[0.95, 2.45]) | baseline 대비 mid 변화량 | **민감도 (mid)** |
| **Δ vs baseline_full** (z∈[0, 3.0]) | baseline 대비 full 변화량 | **민감도 (full)** |
| **T_floor** (z≈0) | 바닥 근처 T | smoke stratification |
| **T_ceiling** (z≈3) | 천장 근처 T | hot smoke layer |
| **T_mid** (z≈1.5) | 화원 plume 중심 | fire impact |
| **HRR avg** (DEVC) | 평균 발열량 | run sanity 검증 |
| **run time** | 실시간 wall-clock | 비용 추적 |

> **mid vs full 해석 규칙**:
> - `mean_mid ≪ mean_full` → 경계 (z=0, z=3) 영향 큼 → ceiling/floor 조건 의심
> - `mean_mid ≈ mean_full` → 전 z에 균일하게 차이 → 본질적 모델 차이 (KAPPA0, fuel 등)
> - `mean_mid > mean_full` → 드물지만 mid에서 큰 차이, 경계 우연 일치

→ +1.0m와 +0.5m 각각에 대해 별도 추출 (28 cases × 2 offsets × 13 metrics ≈ 730 데이터 포인트)

---

## 2. 분석 단계

### Phase 1: Sanity check (필수)

- 모든 케이스가 정상 종료 (`STOP: FDS completed successfully`)
- HRR 시간평균이 입력값과 일치 (e.g., baseline=863 kW, A4a=700 kW, A4b=1100 kW)
- `_avg` DEVC 컬럼이 0이 아님 (t≥100s 평균 누적 확인)
- 격자/T_END 모두 동일 (M1, 300s)

→ 실패 케이스는 표에 명시 + 재실행

### Phase 2: 정량 분석

#### 2.1 마스터 표 생성

표 형식 (`Report/sensitivity_results.md` + `analysis/sensitivity/table_summary.csv`):

각 offset (+1.0m, +0.5m)별로 paper 대비/baseline 대비 모두 mid와 full 두 범위 출력.

| Case | Group | Var | Val | +1m mean_mid | +1m mean_full | +1m max_full | +1m Δ_mid | +1m Δ_full | +0.5m mean_mid | +0.5m mean_full | +0.5m Δ_mid | +0.5m Δ_full | T_floor | T_mid | T_ceil | HRR | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | — | — | — | X.X | X.X | X.X | 0.00 | 0.00 | X.X | X.X | 0.00 | 0.00 | X.X | X.X | X.X | 863 | ✅ |
| sens_A1a | A | KAPPA0 | 0.5 | … | … | … | … | … | … | … | … | … | … | … | … | … | ✅/⚠️/❌ |
| ... | | | | | | | | | | | | | | | | | |

> 표 컬럼이 많아 가독성 위해 mid/full 별도 split 표 추가 가능:
> - `table_paper.md` — paper 대비만 (mid + full)
> - `table_baseline.md` — baseline 대비만 (mid + full, 민감도 ranking 핵심)
> - `table_diag.md` — T_floor/mid/ceil + HRR + status
| ... | | | | | | | | | |

#### 2.2 민감도 순위 (bar chart)

각 offset (+1m, +0.5m) × 각 범위 (mid, full) = **4개 bar chart**:

| Plot | metric | 의미 |
|---|---|---|
| `sensitivity_bars_p1p0m_mid.png` | Δ vs baseline_mid at +1m | 안정 영역만 민감도 |
| `sensitivity_bars_p1p0m_full.png` | Δ vs baseline_full at +1m | 경계 포함 민감도 |
| `sensitivity_bars_p0p5m_mid.png` | Δ vs baseline_mid at +0.5m | |
| `sensitivity_bars_p0p5m_full.png` | Δ vs baseline_full at +0.5m | |

- 가로축: Δ mean|ΔT| vs baseline (°C), 정렬
- 세로축: case label
- 색: 그룹별 (A/B/C/D/E)

→ mid vs full 순위 비교: **boundary에서만 영향 주는 변수** (예: floor 두께)는 full에서 위로, mid에서 아래로 → 식별 가능

#### 2.3 그룹별 sweep curve (monotonic)

연속 변수에 대해 (KAPPA0, RAD_FRAC, SOOT, HRR, floor_thickness, divider_thickness, engine_thickness) — sweep 값 vs metric 그래프:

```
mean|ΔT| (°C)
    │
 X  │  ●
    │       ●
 X  │            ●─── baseline
    │                  ●
 X  │
    │                      ●
    └─────────────────────────────
       0.5   1.0  1.7   2.5   3.0   KAPPA0
```

→ 단조 변화 vs 비단조 식별, optimal 값 추정 가능

각 sweep plot에 **두 곡선** 표시 (이중 y축 또는 같은 축에 다른 색):
- **mean|ΔT|_mid** (실선, 안정 영역 기준)
- **mean|ΔT|_full** (점선, 전 영역 기준)

→ 변수가 mid보다 full에 더 영향 주는지 (e.g., floor_thickness가 z=0 근처만 변경) 판단 가능.

#### 2.4 그룹별 T(z) overlay

- Group A/B/C/D/E 각각 +1m, +0.5m → 10개 plot
- baseline (회색 굵은 선) + paper (검은 점선) + 그룹 내 변형들

→ T(z) **모양 변화** 관찰 (천장만 바뀜? 바닥만? 전체 시프트?)

### Phase 3: 정성 분석

#### 3.1 Top-3 후보 (paper에 가장 가까운 케이스)

mean|ΔT|_**full** 가장 작은 3개 케이스 → 슬라이스 plot 생성 (paper 전 영역 일치 평가에 full이 더 엄격):
- XZ at y=1.45
- YZ at x=8.0 (fire 중심)
- XY at z=2.0

→ paper Fig 18과 직접 시각 비교

mid 기준 top-3와 full 기준 top-3 비교 시:
- 같으면 → 정말 좋은 케이스 (mid도 full도 우수)
- 다르면 → 어떤 영역에서 잘 맞는지 차이 명시

#### 3.2 Worst-3 (paper에서 가장 멀어진 케이스)

→ 동일 슬라이스 plot. 어떤 메커니즘으로 멀어졌는지 진단.
mean|ΔT|_full 기준 (전 영역에서 망가진 정도 측정).

#### 3.3 Best case 조합 가능성 평가

각 변수의 best 값을 모아 한 케이스로 결합하면 어떻게 될지 예측 (linear superposition 가정, 검증 필요).

### Phase 4: 결론 & 권장사항

- Most influential parameters 순위 (top 5)
- Optimal sweep values
- Paper와 systematic offset 21°C 줄일 수 있는 조합 제안
- 후속 sweep 권장 (예: 2-variable interaction)

---

## 3. 산출물

### 텍스트
- [Report/sensitivity_results.md](Report/sensitivity_results.md) — 메인 보고서 (모든 표 + 결론)

### 머신 가독
- `analysis/sensitivity/table_summary.csv` — 전체 데이터 표 (Excel 사용 가능)

### 그래프
- `analysis/sensitivity/sensitivity_bars_p1p0m.png` (랭킹)
- `analysis/sensitivity/sensitivity_bars_p0p5m.png`
- `analysis/sensitivity/sweep_kappa0_p1p0m.png` (KAPPA0 단조)
- `analysis/sensitivity/sweep_kappa0_p0p5m.png`
- `analysis/sensitivity/sweep_radfrac_*.png` (4 sweep × 2 offset)
- `analysis/sensitivity/sweep_soot_*.png`
- `analysis/sensitivity/sweep_hrr_*.png`
- `analysis/sensitivity/sweep_floor_thick_*.png`
- `analysis/sensitivity/sweep_divider_thick_*.png`
- `analysis/sensitivity/sweep_engine_thick_*.png`
- `analysis/sensitivity/T_z_group_A_p1p0m.png` (5 group × 2 offset = 10)
- ...
- `analysis/sensitivity/best_3/` — top-3 케이스 슬라이스 plots
- `analysis/sensitivity/worst_3/` — worst-3 case slices

---

## 4. 구현 코드 구조

### 4.1 `analysis/sensitivity/extract.py` (Phase 1+2.1)

```python
def extract_one(case_id) -> dict:
    """Returns {T_z_p1m, T_z_p05m, hrr_avg, completed: bool, ...}"""
def extract_all() -> pd.DataFrame   # 28 rows × ~20 columns
def save_csv(df, path)
def save_md_table(df, path)
```

### 4.2 `analysis/sensitivity/plot_bars.py` (Phase 2.2)

```python
def plot_ranking(df, offset, sort_by="delta_vs_base") → png
```

### 4.3 `analysis/sensitivity/plot_sweeps.py` (Phase 2.3)

```python
SWEEP_VARS = {
    "kappa0":         [0.5, 1.0, 1.7, 2.5, 3.0],
    "rad_frac":       [0.2, 0.3, 0.4],
    "soot":           [0.02, 0.05, 0.10],
    "hrr":            [700, 863, 1100],
    "floor_thick":    [0.005, 0.01, 0.05, 0.2],
    "divider_thick":  [0.05, 0.2, 0.5],
    "engine_thick":   [0.001, 0.01, 0.05, 0.2],
}
def plot_sweep(var, df) → png  # x=sweep value, y=metric, marks baseline
```

### 4.4 `analysis/sensitivity/plot_groups.py` (Phase 2.4)

```python
def plot_group_overlay(group, offset, df) → png  # T(z) overlay
```

### 4.5 `analysis/sensitivity/find_extremes.py` (Phase 3.1, 3.2)

```python
def top_n(df, metric, n=3) → list[case_id]
# Then run plot_all_slices.py for each → best_3/, worst_3/
```

### 4.6 `analysis/sensitivity/run_all.sh`

```bash
#!/bin/bash
# Orchestrates everything once all FDS runs complete
python3 extract.py
python3 plot_bars.py
python3 plot_sweeps.py
python3 plot_groups.py
python3 find_extremes.py
# Generate report
python3 generate_report.py
```

---

## 5. 일정 & 의존성

| Phase | 의존성 | 시간 |
|---|---|---|
| Phase 0: 모든 FDS run 완료 | 27 cases + baseline | ~60–90분 |
| Phase 1: Sanity check | Phase 0 | 1분 |
| Phase 2.1: Master table | Phase 1 | 1분 |
| Phase 2.2: Bar charts | Phase 2.1 | 30초 |
| Phase 2.3: Sweep curves | Phase 2.1 | 30초 |
| Phase 2.4: T(z) overlays | Phase 2.1 | 1분 |
| Phase 3: Top/worst-3 slices | Phase 2.2 | 5분 (10 slice plots) |
| Phase 4: 결론 보고서 작성 | All above | 수동 (해석 필요) |

**총 자동 분석 시간**: ~10분 (FDS sweep 완료 후)

---

## 6. 의사 결정 포인트 (구현 전 확인)

1. **Δ vs baseline metric**: `mean(|T_case − T_baseline|)` (L1 norm) vs `RMS` ? → L1 권장 (외란에 robust)
2. ~~**중간 안정 band**: z∈[0.95, 2.45] vs 전체 z∈[0,3]~~ → **둘 다 사용** (mid + full)
3. **베이스라인 두 개?**: 옛 baseline (759273) vs 새 baseline (764189) 둘 다 표시할지, 새 것만 사용할지
4. **결합 최적화**: best-of-best 조합 케이스 1개 추가 실행? (예: KAPPA0=best + RAD_FRAC=best + floor=best 동시 적용)
5. **추가 sweep**: 1차 결과 보고 sensitivity high 변수에 대해 2차 fine sweep?

---

## 7. Sanity check 자동화 plan

```python
def sanity_check(case_id) -> dict:
    """Return dict with:
       completed: bool (STOP: completed successfully in .out)
       avg_filled: bool (_avg column != 0)
       hrr_match: bool (devc HRR avg within 5% of expected peak)
       finite: bool (no NaN/inf in T_z)
    """
    # parse .out tail, _devc.csv, _line.csv
    ...
```

→ 표에 `status` 컬럼: ✅ OK / ⚠️ WARN / ❌ FAIL  
실패 케이스는 자동으로 재제출 가능 (옵션).

---

## 8. 다음 행동 권장

1. 사용자 확인 사항 (#6) 결정
2. `extract.py` + `plot_bars.py` 구현 → 백업 데이터로 dry-run 테스트 가능 (옛 baseline 759273 + 일부 cold-walls 케이스 활용)
3. FDS sweep 진행 모니터링
4. 완료 → run_all.sh 실행

---

*초안 2026-06-16. FDS sweep 진행 중. 분석 코드 사전 작성 권장.*
