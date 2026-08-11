# KRISO-Fire 2차년도 — 1D/3D 커플링 EV 화재 FDS 해석 프로젝트 브리프

**작성일:** 2026-07-29
**수행:** 연세대학교 Multi-Physics Modeling and Computation Lab (Jung-Il Choi)
**발주:** KRISO (선박해양플랜트연구소)
**과제:** 친환경 연료 화재폭발 안전성 평가 및 화재대응 — 선박 화재폭발 CFD 수치해석 평가 프로세스 구축

---

## 0. 이 문서의 사용법

이 문서를 읽는 대상은 **간단한 예제 FDS input 파일을 작성하는 작업자(또는 AI)** 입니다.

- **1~5장**: 왜 이런 모델 구성을 택했는지에 대한 배경. 설계 의도를 이해하는 데 필요.
- **6장**: 예제 문제의 완전한 정의. 여기부터가 실제 작업 지시.
- **7장**: FDS input 스켈레톤. 6장의 값을 넣으면 동작해야 함.
- **8~9장**: 검증 항목과 미결 사항.

> **중요:** 이 문서의 모든 수치는 **플레이스홀더**입니다. 실제 1D 팀 데이터가 도착하기 전 파이프라인을 검증하기 위한 값이며, 물리적으로 그럴듯한 크기 정도만 맞춰져 있습니다. 최종 해석에 그대로 쓰면 안 됩니다. 플레이스홀더는 `[PH]` 로 표시했습니다.

---

## 1. 프로젝트 목표

### 최종 목표 (4~5차년도)
연세대가 납품한 소프트웨어로 **EV 화재 실험 횟수를 최소화**. 실험을 대체가 아니라 보조하는 것이 KRISO의 명시적 입장.

### 2차년도(올해) 목표
**단일 케이스에 대해 1D 배터리 모델과 3D FDS를 커플링해서 해석 1건 완수.**

- 대상 차량: 현대 코나 일렉트릭 롱레인지 (CATL 각형 셀, CTP 구조 가능성 확인 필요)
  - 회의록상 IONIQ 5(LG 파우치형)로 변경 검토 중 — 매물 확보 용이성 사유
- 3D FDS + 1D Amesim 구조
- 소화(suppression) 해석 연동은 후반부 목표

### 일정
| 시점 | 마일스톤 |
|---|---|
| 9~10월 | 다음 회의. 해석 1건 결과 필요 |
| 10월 초중순 | 해석 데이터 제공 |
| 10월 말 | 최종 데이터 확정 |
| 11월 중순 | 보고서 작성 |

---

## 2. 역할 분담

| 주체 | 담당 | 산출물 |
|---|---|---|
| MPSE 팀 | 1D 배터리 모델 (Amesim) | 셀간 열전이, 화학분해 발열, 가스 생성률 |
| 연세대 | 3D FDS | 차체 화재 확산, 구획 내 열/연기/독성가스, 소화 |
| KRISO | 발주/검증 | 열저항 모델 피팅 요청 |

**데이터 흐름은 올해 단방향(1D → 3D) + 1회 반복.** 상세는 5장.

---

## 3. 물리 모델 설계 결정사항

### 3.1 열 경로를 두 갈래로 분리 (가장 중요한 결정)

배터리 팩이 3D 공간에 열을 주는 경로는 물리적으로 둘이며, **FDS에서 반드시 분리해야 합니다.**

| 경로 | 물리 | FDS 처리 |
|---|---|---|
| ① 팩 내부 축열 → 케이싱 표면 | 전도·복사, 기상 연소 없음 | **고체 경계조건** (`NET_HEAT_FLUX`) |
| ② 벤트가스 방출 → 기상 연소 | 가연성 가스 분출 + 화염 | **기체 연료 소스** (`MASS_FLUX` + `SPEC_ID`) |

**왜 통짜 HRR(t)를 쓰지 않는가:**

실험에서 측정한 팩 HRR은 산소 소모율 기반이라 ①+②가 이미 합쳐진 값입니다. 이를 `HRRPUA` + `RAMP_Q`로 그대로 넣으면 편하지만:

- FDS가 연소를 계산할 여지가 사라짐
- **물분무를 뿌려도 정해진 Q(t)가 그대로 방출됨 → 소화 해석 불가**
- 밀폐 구획의 산소 부족으로 인한 미연소 가스 축적 표현 불가

올해 과업에 소화 모델 연동이 포함되어 있으므로 ②번 방식이 필수입니다.

> **단계적 접근 권장:** 1단계로 통짜 HRR 방식으로 파이프라인을 빠르게 검증하고, 2단계에서 ①+② 분리 방식으로 전환. 본 문서의 예제는 **2단계 방식**을 기준으로 작성합니다.

### 3.2 차체 가연물 모델 선택: 증발 모델

FDS 화재 모델링은 3가지 선택지가 있으며, 차이는 **ṁ″(가연성 가스 발생률)를 어떻게 결정하느냐**입니다. 최종적으로는 모두 `q̇″ = ṁ″ × ΔH_e`.

| | 단순 모델 | 열분해 모델 | **증발 모델 (채택)** |
|---|---|---|---|
| ṁ″ 결정 | 입력 테이블 재생 | 아레니우스 반응 | Clausius-Clapeyron + 물질전달 |
| 핵심 입력 | HRRPUA(t), T_ig | A, E, n | T_b, h_v, W |
| 환경 피드백 | **없음** | 있음 | 있음 |
| 물성 확보 | 콘칼로리미터 | TGA 필요 | 중간 |
| 계산비용 | 낮음 | 높음 | 중간 |

**증발 모델 채택 사유:**
- 열유속 피드백이 살아 있어 팩 화염에 차체가 반응함
- A, E 같은 민감 파라미터가 불필요 (열분해 모델은 A·E 편차가 매우 큼)
- 복합소재 고체가연물을 "등가 액체연료"로 치환하는 개념

**알려진 한계:** 액체 취급이므로 char가 남지 않아, 탄화 소재(고무 등)의 **후반부 감쇠 구간을 과대예측**합니다. 보고서에 명시할 것.

### 3.3 스케일 인식

Kang et al. (2023) Fig. 6 기준:
- LIB 팩 자체 HRR 피크: **약 1 MW**
- BEV 전체 HRR 피크: **약 7.5 MW**

**즉 1D가 제공하는 것은 사실상 "점화원과 그 타이밍"이고, 피크 HRR을 결정하는 것은 차체 가연물 모델입니다.** 튜닝 노력은 차체 쪽에 집중해야 합니다.

---

## 4. 화학종(species) 처리 방식

### 4.1 연료는 2종

| | 연료 species | 실체 |
|---|---|---|
| 배터리 | `BATTERY_GAS` | H₂ + CO + CO₂ + CH₄ + C₂H₄ 혼합 (lumped) |
| 차량 | `CAR_BODY_FUEL` | 등가 액체연료 (PU폼+PP+고무+시트 통합) |

FDS는 `REAC` 라인을 여러 개 쓸 수 있으며, 각 simple chemistry 반응이 고유한 연료를 가지면 됩니다 (User Guide 13.1, 13.2.4).

### 4.2 lumped species 메커니즘

FDS는 화학종을 전부 추적하지 않고, **묶음(lumped) 단위로 계산한 뒤 개별 성분을 역산**합니다.

```
성분 조성 입력  →  변환행렬 A 구성  →  Z(lumped)만 수송방정식  →  Y = A·Z 로 역산 출력
```

변환행렬 원소: `a_αi = ν_αi·W_α / Σ_β ν_βi·W_β` (ν = 부피분율, W = 분자량)

**결과:** 성분이 몇 종이든 수송방정식은 lumped 개수만큼만 증가. 출력은 `DEVC`/`SLCF`로 개별 성분(CO, CO₂, O₂, soot) 그대로 조회 가능.

**손실되는 물리 3가지 (보고서 한계 항목):**
1. lumped 내부 성분의 확산계수가 전부 동일 → H₂만 먼저 확산해 천장에 축적되는 거동 불가
2. 성분이 항상 고정 비율로 함께 소모 → H₂ 먼저 타고 CO 남는 거동 불가
3. **조성이 시간에 따라 변하지 않음** ← 실무적으로 가장 큰 제약

3번 대응 옵션:
- (a) 시간평균 조성 1개 — **올해 채택**
- (b) `VENT_EARLY` / `VENT_LATE` 2개 연료로 계단 근사 — 조성 변동폭이 크면 승격
- (c) 성분 전부 개별 추적 — complex stoichiometry 필요, 올해 범위 초과

### 4.3 CO₂를 연료 species 안에 포함시킬 것

벤트가스의 25~30%가 CO₂입니다. 이를 빼고 가연분만 넣으면 질량유량이 틀리고 희석·질식 효과가 사라집니다.

**연료 lumped species 안에 넣어도 원자 balance상 산소 요구량 0으로 자동 처리됩니다** (CO₂: x=1, z=2 → ν_O₂ = 1 + 0 + 0 − 1 = 0).

### 4.4 파라미터가 들어가는 4개 층

| 층 | 대상 | 설정 항목 |
|---|---|---|
| 1 | 성분 (primitive) | `VOLUME_FRACTION`만. Appendix A 등재 species면 물성 입력 불필요 |
| 2 | 혼합물 (lumped) | 조성 벡터 하나 ← **1D 팀에서 받는 값** |
| 3 | 반응 (`REAC`) | `HEAT_OF_COMBUSTION`, `SOOT_YIELD`, `CO_YIELD`, `RADIATIVE_FRACTION` |
| 4 | 소스 (`SURF`/`MATL`) | 배터리: `MASS_FLUX`+`RAMP_MF` / 차체: 액체 물성 |

### 4.5 함정 3가지 — 반드시 확인

**① `HEAT_OF_COMBUSTION` 기준 질량**
불활성분을 **포함한** lumped species 1 kg당 값입니다. 가연분 기준 값을 넣으면 HRR이 통째로 과대평가됩니다.

```
ΔH_c,mix = Σ_i Y_i · ΔH_c,i     (Y_i = 전체 벤트가스 질량 기준 질량분율)
성분별 (MJ/kg):  H₂ 120,  CO 10.1,  CH₄ 50,  C₂H₄ 47.2,  CO₂ 0,  N₂ 0
```

**② `CO_YIELD` 이중 계상**
벤트가스 조성에 이미 CO가 있는데, `CO_YIELD`는 *연소 후 추가 생성되는* CO입니다. 조성의 CO를 여기 또 넣으면 안 됩니다. **조성 CO는 층 2, 불완전연소 CO는 층 3 — 별개입니다.**

**③ `RADIATIVE_FRACTION` 기본값 부적합**
기본값 ≈ 0.35는 탄화수소 기준. H₂ 비중이 큰 벤트가스 화염은 실제 0.1~0.2입니다. 기본값을 쓰면 팩→차체 복사열유속이 과대평가되고, 이는 **차체 착화 시점을 직접 결정**합니다. 민감도 케이스 필수.

**④ HF는 lumped fuel에 못 들어감**
lumped component는 C, H, N, O 원자만 허용. F를 포함한 HF는 불가. **비반응 추적 species로 별도 주입**할 것.

---

## 5. 1D → 3D 인터페이스 스펙

### 5.1 요청 데이터 (CSV)

모듈(존)별로 행을 나눌 것. **시간 해상도 Δt ≤ 1 s** (TR 이벤트는 초 단위로 급변하고, FDS `RAMP`는 점 사이를 선형보간하므로 벤트 개시 부근이 성기면 피크가 뭉개짐).

| 변수 | 기호 | 단위 | 용도 |
|---|---|---|---|
| 시간 | t | s | `RAMP` 축 |
| 존/모듈 ID | — | — | 열폭주 전파 위치 |
| 케이싱 표면 순 열유속 | q″_cas(t) | kW/m² | 경로 ① |
| 벤트가스 질량유량 | ṁ_vent(t) | kg/s | 경로 ② |
| 벤트가스 온도 | T_vent(t) | K | 경로 ② 엔탈피 |
| 벤트가스 조성 | Y_H₂, Y_CO, Y_CO₂, Y_CH₄, Y_C₂H₄ | 질량분율 | `SPEC` 조성 |
| HF (옵션) | Y_HF | 질량분율 | 독성 추적 |
| 벤트 위치·면적·방향 | — | m², 벡터 | 소스 지오메트리 |
| 누적 발열량 | THR(t) | MJ | 정합성 검증 |

**필수 확인:** q″_cas와 ṁ_vent가 **서로 겹치지 않는 분해**인지. 겹치면 에너지 이중 계상.

### 5.2 커플링 방식: 단방향 + 1회 반복 (loose coupling)

1D 모델도 팩 외부 표면 경계조건이 필요하며, 1D 팀은 반드시 무언가를 가정했습니다 (단열 / 20℃ 대기 자연대류 / 고정 열유속). 그런데 실제로는 차체 착화 후 팩이 800~1000℃ 화염 아래 놓여 입사 열유속이 50~100 kW/m²가 됩니다.

```
1. 1D 1차 해석  (외부 열유속을 가정)
       ↓ mdot_vent.csv, T_vent.csv
2. FDS 1차 해석 (차체 화재까지 계산)
       ↓ q_inc_pack.csv
3. 팩 표면 열유속 비교 (가정값 vs 계산값)
       ↓
4. 1D 2차 해석  (FDS 값을 경계조건으로 교체)
       ↓ mdot_vent_v2.csv
5. FDS 2차 해석 (갱신된 벤트 이력 사용)
```

"되먹인다"는 것은 **1D 입력파일의 경계조건 한 줄을 FDS가 계산한 시간이력 CSV로 바꿔 끼우는 것**입니다. 각 코드는 끝까지 완주한 뒤 파일을 넘기므로 loose(약결합)입니다.

**수렴 판정 (1차 FDS vs 2차 FDS):**
- 피크 HRR 변화 10% 이내
- 피크 시점 변화 10% 이내
- 총 THR 변화 5% 이내

기준을 크게 벗어나면 "단방향으로는 이 문제를 못 푼다"는 결론이며, 그 자체가 4~5차년도 양방향 커플링 필요성의 근거가 됩니다.

**단방향 가정의 유효 범위:** 개방 조건에서 유효, **밀폐 선박 구획에서는 비보수적**. 상층 연기층 온도 상승으로 실제 TR 전파가 더 빨라지기 때문.

---

## 6. 예제 문제 정의 (작업 지시)

> **목적:** 실제 1D 데이터가 오기 전, FDS 입력 구조와 커플링 파이프라인을 검증하는 최소 예제.
> **의도적 단순화:** 개방 공간(선박 구획 아님), 차량 1대, 모듈 3존, 단시간.

### 6.1 도메인 및 격자

| 항목 | 값 |
|---|---|
| 도메인 | 10 (x) × 6 (y) × 5 (z) m |
| 격자 | 균일 0.10 m → 100 × 60 × 50 = 300,000 cells |
| 경계 | 바닥 제외 전면 `OPEN` |
| 해석 시간 | 900 s (파이프라인 검증용. 실제는 3600 s) |
| 주변 온도 | 20 ℃ |

**격자 타당성 (참고):** 피크 HRR 7 MW 기준 D* ≈ 2.1 m. D*/δx = 10~16 → δx = 0.13~0.21 m. 예제의 0.10 m는 충분히 세밀. 실제 해석에서는 차량 하부·타이어 근처만 국부 세밀화하고 원방은 0.2 m로 완화 권장 (`MULT` / multi-mesh).

### 6.2 지오메트리

```
차체 (OBST):  XB = 3.0, 7.4,  2.1, 3.9,  0.40, 1.90   (4.4 × 1.8 × 1.5 m)
배터리 팩:    XB = 4.2, 6.2,  2.4, 3.6,  0.25, 0.40   (2.0 × 1.2 × 0.15 m)
```

배터리 팩은 **연소하지 않는 `OBST`** 로 두고 표면에만 경계조건을 인가합니다.

**벤트 존 3개** (팩 상면 z = 0.40, 전→후 배치):

| 존 | XB | 면적 | 벤트 개시 |
|---|---|---|---|
| Z1 | 4.4, 4.9, 2.7, 3.3, 0.40, 0.40 | 0.30 m² | 60 s |
| Z2 | 5.0, 5.5, 2.7, 3.3, 0.40, 0.40 | 0.30 m² | 240 s |
| Z3 | 5.6, 6.1, 2.7, 3.3, 0.40, 0.40 | 0.30 m² | 420 s |

시차 배치는 **열폭주 전파를 모사**하기 위함입니다. Kang et al. 시험에서 Module 9 가열 시 후방 모듈에서 벤트 제트가 발생해 타이어를 태운 거동에 대응.

> **벤트 제트는 해상하지 말 것.** 실제 제트는 100 m/s 급이라 FDS 격자로 못 잡습니다. 실제 벤트 면적보다 넓은 등가 면적에 분산시켜 운동량을 낮추고, 제트 방향성은 별도 민감도 케이스로 다룰 것.

### 6.3 배터리 벤트가스 물성 `[PH]`

**조성 (부피분율, %)**

| H₂ | CO | CO₂ | CH₄ | C₂H₄ |
|---|---|---|---|---|
| 28 | 23 | 28 | 12 | 9 |

**유도값 (위 조성에서 계산)**

| 항목 | 값 | 산출 |
|---|---|---|
| 유효 분자량 | 23.8 g/mol | Σ x_i W_i |
| ΔH_c,mix | **14,600 kJ/kg** | Σ Y_i ΔH_c,i (CO₂ 기여 0) |

**REAC 파라미터**

| 항목 | 값 | 비고 |
|---|---|---|
| `HEAT_OF_COMBUSTION` | 14600 | 불활성 포함 기준 |
| `SOOT_YIELD` | 0.02 | H₂/CO 우세로 낮음 |
| `CO_YIELD` | 0.05 | 조성 CO와 별개 |
| `RADIATIVE_FRACTION` | 0.15 | 기본값 0.35 사용 금지 |

**벤트 유량 (존당)**

| 항목 | 값 |
|---|---|
| 존당 총 방출 질량 | 9 kg |
| 피크 `MASS_FLUX` | 0.15 kg/(m²·s) |
| 방출 지속 | 200 s (사다리꼴 램프) |
| 벤트가스 온도 | 600 ℃ |

존당 피크 HRR ≈ 0.15 × 0.30 × 14,600 ≈ **660 kW**. 3존 시차 방출로 배터리 기여 총 THR ≈ 400 MJ.

### 6.4 차체 가연물 물성 `[PH]`

증발(액체) 모델. `BOILING_TEMPERATURE`를 `MATL`에 넣으면 FDS가 액체 열분해 모델을 사용하며 `N_REACTIONS=1`이 자동 설정되어 유일한 "반응"이 액체→기체 상변화가 됩니다. 따라서 `HEAT_OF_REACTION`은 **기화 잠열**로 해석됩니다.

**발표자료 슬라이드 5의 Input Parameters ↔ FDS 키워드 매핑**

| 슬라이드 기호 | FDS 키워드 | 위치 | 값 `[PH]` |
|---|---|---|---|
| ρ_s (density) | `DENSITY` | MATL | 900 kg/m³ |
| c_p,s (specific heat) | `SPECIFIC_HEAT` | MATL | 1.5 kJ/(kg·K) |
| k_s (conductivity) | `CONDUCTIVITY` | MATL | 0.20 W/(m·K) |
| T_b (boiling temp) | `BOILING_TEMPERATURE` | MATL | 350 ℃ |
| h_v (heat of vaporization) | `HEAT_OF_REACTION` | MATL | 500 kJ/kg |
| κ_s (absorption coeff.) | `ABSORPTION_COEFFICIENT` | MATL | 1000 1/m |
| ε (emissivity) | `EMISSIVITY` | MATL | 0.90 |
| Fuel gas species | `SPEC_ID` | MATL | `CAR_BODY_FUEL` |
| Fuel gas yield | `NU_SPEC` | MATL | 1.0 |
| W (molecular weight) | `FORMULA` | SPEC | C₆H₁₀O₁ |
| ΔH_e (effective ΔH_c) | `HEAT_OF_COMBUSTION` | REAC | 25,000 kJ/kg |

**REAC 추가 파라미터:** `SOOT_YIELD` = 0.10 (타이어·PVC 고려), `CO_YIELD` = 0.05, `RADIATIVE_FRACTION` = 0.35

> **`THICKNESS`가 총 발열량을 결정합니다.** 연료 총량 = ρ × THICKNESS × 면적.
> 예제: 노출 연소면적 ≈ 25 m², THICKNESS = 0.012 m → 연료 270 kg → 6.7 GJ.
> Kang et al.의 BEV 총 THR(약 7~8 GJ)에 맞추는 **주 튜닝 노브**가 이것입니다.
> `ABSORPTION_COEFFICIENT`도 연소율에 미치는 영향이 크므로 함께 볼 것.

### 6.5 케이싱 열유속 `[PH]`

팩 측면·상면 중 벤트가 아닌 영역에 인가. `TMP_FRONT`(온도 지정)가 아니라 **`NET_HEAT_FLUX`(열유속 지정)** 를 쓸 것 — 온도를 고정하면 FDS가 계산한 화염 복사가 팩 표면에 영향을 못 주고, 나중에 양방향 커플링으로 확장할 때 열유속 방식이 그대로 이어집니다.

피크 5 kW/m², 0→900 s에 걸쳐 완만히 상승.

### 6.6 HF 추적 (옵션)

비반응 추적 species로 벤트에서 연료와 동시 주입. 농도장 매핑 용도.
`[PH]` 벤트가스 질량의 0.5%.

**주의:** `HYDROGEN FLUORIDE`가 FDS Appendix A에 등재되어 있는지 **먼저 확인**할 것. 미등재면 `FORMULA='HF'` + 열물성(`SPECIFIC_HEAT`, `ENTHALPY_OF_FORMATION`, `CONDUCTIVITY`, `VISCOSITY`, `DIFFUSIVITY`)을 직접 입력해야 합니다.

---

## 7. FDS Input 스켈레톤

```fortran
&HEAD CHID='EV_fire_example', TITLE='KRISO-Fire 1D-3D coupling example' /

&MESH IJK=100,60,50, XB=0.0,10.0, 0.0,6.0, 0.0,5.0 /

&TIME T_END=900. /
&MISC TMPA=20. /
&DUMP DT_HRR=1., DT_DEVC=1., DT_SLCF=5., DT_BNDF=10. /

! ===========================================================
!  화학종 정의
! ===========================================================
! --- 벤트가스 성분 (Appendix A 등재 → 물성 입력 불필요)
&SPEC ID='HYDROGEN',        LUMPED_COMPONENT_ONLY=T /
&SPEC ID='CARBON MONOXIDE', LUMPED_COMPONENT_ONLY=T /
&SPEC ID='CARBON DIOXIDE',  LUMPED_COMPONENT_ONLY=T /
&SPEC ID='METHANE',         LUMPED_COMPONENT_ONLY=T /
&SPEC ID='ETHYLENE',        LUMPED_COMPONENT_ONLY=T /

! --- 배터리 벤트가스 (lumped fuel). CO2를 안에 포함시킬 것
&SPEC ID='BATTERY_GAS'
      SPEC_ID(1)='HYDROGEN',        VOLUME_FRACTION(1)=28.
      SPEC_ID(2)='CARBON MONOXIDE', VOLUME_FRACTION(2)=23.
      SPEC_ID(3)='CARBON DIOXIDE',  VOLUME_FRACTION(3)=28.
      SPEC_ID(4)='METHANE',         VOLUME_FRACTION(4)=12.
      SPEC_ID(5)='ETHYLENE',        VOLUME_FRACTION(5)= 9. /

! --- 차체 등가연료
&SPEC ID='CAR_BODY_FUEL', FORMULA='C6H10O1' /

! ===========================================================
!  반응 (연료 2종 → REAC 2줄)
! ===========================================================
&REAC ID='BATT', FUEL='BATTERY_GAS',
      HEAT_OF_COMBUSTION=14600.,
      SOOT_YIELD=0.02, CO_YIELD=0.05,
      RADIATIVE_FRACTION=0.15 /

&REAC ID='BODY', FUEL='CAR_BODY_FUEL',
      HEAT_OF_COMBUSTION=25000.,
      SOOT_YIELD=0.10, CO_YIELD=0.05,
      RADIATIVE_FRACTION=0.35 /

! ===========================================================
!  차체 재료 (증발 모델 = 액체 열분해)
! ===========================================================
&MATL ID='CAR_BODY_LIQUID'
      SPEC_ID='CAR_BODY_FUEL'
      NU_SPEC=1.0
      BOILING_TEMPERATURE=350.      ! 이 줄이 액체 모델을 켬
      HEAT_OF_REACTION=500.         ! = 기화 잠열 h_v
      DENSITY=900.
      CONDUCTIVITY=0.20
      SPECIFIC_HEAT=1.5
      ABSORPTION_COEFFICIENT=1000.
      EMISSIVITY=0.90 /

&SURF ID='CAR_BODY', MATL_ID='CAR_BODY_LIQUID',
      THICKNESS=0.012, COLOR='SILVER' /

! ===========================================================
!  배터리 팩 케이싱 (경로 1: 고체 경계조건)
! ===========================================================
&SURF ID='PACK_CASE', COLOR='GRAY',
      NET_HEAT_FLUX=5.0, RAMP_Q='cas_q' /

&RAMP ID='cas_q', T=  0., F=0.00 /
&RAMP ID='cas_q', T=300., F=0.30 /
&RAMP ID='cas_q', T=600., F=0.80 /
&RAMP ID='cas_q', T=900., F=1.00 /

! ===========================================================
!  벤트가스 소스 (경로 2: 기체 연료). 존별로 RAMP 분리
! ===========================================================
&SURF ID='VENT_Z1', SPEC_ID(1)='BATTERY_GAS',
      MASS_FLUX(1)=0.15, RAMP_MF(1)='mdot_z1',
      TMP_FRONT=600., COLOR='ORANGE' /
&SURF ID='VENT_Z2', SPEC_ID(1)='BATTERY_GAS',
      MASS_FLUX(1)=0.15, RAMP_MF(1)='mdot_z2',
      TMP_FRONT=600., COLOR='ORANGE' /
&SURF ID='VENT_Z3', SPEC_ID(1)='BATTERY_GAS',
      MASS_FLUX(1)=0.15, RAMP_MF(1)='mdot_z3',
      TMP_FRONT=600., COLOR='ORANGE' /

! 사다리꼴 램프 — 실제 해석에서는 1D CSV로 대체 (Dt <= 1 s)
&RAMP ID='mdot_z1', T= 55., F=0.0 /
&RAMP ID='mdot_z1', T= 60., F=1.0 /
&RAMP ID='mdot_z1', T=240., F=1.0 /
&RAMP ID='mdot_z1', T=260., F=0.0 /

&RAMP ID='mdot_z2', T=235., F=0.0 /
&RAMP ID='mdot_z2', T=240., F=1.0 /
&RAMP ID='mdot_z2', T=420., F=1.0 /
&RAMP ID='mdot_z2', T=440., F=0.0 /

&RAMP ID='mdot_z3', T=415., F=0.0 /
&RAMP ID='mdot_z3', T=420., F=1.0 /
&RAMP ID='mdot_z3', T=600., F=1.0 /
&RAMP ID='mdot_z3', T=620., F=0.0 /

! ===========================================================
!  지오메트리
! ===========================================================
&OBST XB=3.0,7.4, 2.1,3.9, 0.40,1.90, SURF_ID='CAR_BODY' /
&OBST XB=4.2,6.2, 2.4,3.6, 0.25,0.40, SURF_ID='PACK_CASE' /

&VENT XB=4.4,4.9, 2.7,3.3, 0.40,0.40, SURF_ID='VENT_Z1' /
&VENT XB=5.0,5.5, 2.7,3.3, 0.40,0.40, SURF_ID='VENT_Z2' /
&VENT XB=5.6,6.1, 2.7,3.3, 0.40,0.40, SURF_ID='VENT_Z3' /

&VENT MB='XMIN', SURF_ID='OPEN' /
&VENT MB='XMAX', SURF_ID='OPEN' /
&VENT MB='YMIN', SURF_ID='OPEN' /
&VENT MB='YMAX', SURF_ID='OPEN' /
&VENT MB='ZMAX', SURF_ID='OPEN' /

! ===========================================================
!  출력
! ===========================================================
! 팩 표면 입사 열유속 — 1D 되먹임용 (5.2절)
&BNDF QUANTITY='GAUGE HEAT FLUX' /
&BNDF QUANTITY='NET HEAT FLUX' /
&BNDF QUANTITY='WALL TEMPERATURE' /

&DEVC XB=4.2,6.2, 2.4,3.6, 0.40,0.40, IOR=3, ID='q_pack_top',
      QUANTITY='GAUGE HEAT FLUX', STATISTICS='SURFACE INTEGRAL' /

! 미연소 벤트가스 축적 — 별도 모델 없이 이걸로 확인
&SLCF PBY=3.0, QUANTITY='MASS FRACTION', SPEC_ID='BATTERY_GAS' /
&SLCF PBY=3.0, QUANTITY='TEMPERATURE' /
&SLCF PBY=3.0, QUANTITY='HRRPUV' /
&SLCF PBY=3.0, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /
&SLCF PBY=3.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /

&TAIL /
```

### 7.1 작성 시 주의

1. **`&HEAD` 다음에 `&MESH`, `&TIME`** 순서 권장. `&SPEC`은 반드시 `&REAC` 앞.
2. `BACKGROUND` species를 명시적으로 정의할 경우 **가장 먼저** 선언해야 함. 예제는 FDS 기본 AIR를 사용하므로 생략.
3. `MASS_FLUX`는 **RAMP의 F=1.0에 해당하는 기준값**. 실제 유량 = `MASS_FLUX` × F(t).
4. `&RAMP`는 점 사이를 선형보간. 1D CSV를 넣을 때는 데이터 점을 그대로 `&RAMP` 라인으로 변환하는 스크립트를 작성할 것.
5. 예제는 단일 MESH. 실제 해석은 MPI 병렬을 위해 multi-mesh로 분할 필요.

---

## 8. 검증 체크리스트

해석 후 반드시 확인:

| # | 항목 | 방법 | 판정 |
|---|---|---|---|
| 1 | 에너지 보존 | FDS `_hrr.csv`의 ∫HRR dt 중 배터리 기여분 vs 1D THR | 일치. 벗어나면 미연소분 존재 → 환기조건 타당성 확인 |
| 2 | 케이싱 열유속 역산 | `q_pack_top` DEVC vs 1D 가정 경계조건 | 차이 크면 5.2절 반복 수행 |
| 3 | HRR 곡선 형상 | Kang et al. (2023) Fig. 6과 비교 | 피크 시점·상승 기울기 |
| 4 | 총 THR | `THICKNESS` 튜닝 후 | BEV 기준 7~8 GJ |
| 5 | 격자 민감도 | δx = 0.10 / 0.15 / 0.20 m | 피크 HRR 변화 10% 이내 |
| 6 | 복사분율 민감도 | `RADIATIVE_FRACTION` 0.10 / 0.15 / 0.25 | 차체 착화 시점 변화폭 기록 |
| 7 | 미연소 가스 | `BATTERY_GAS` 질량분율 슬라이스 | 개방 조건에서는 미미해야 정상 |

**5, 6번은 보고서 필수 항목.** 특히 6번은 팩→차체 복사가 착화 시점을 지배하기 때문.

---

## 9. 미결 사항 / 확인 필요

### 9.1 1D 팀(MPSE)에 확인

- [ ] q″_cas(t)와 ṁ_vent(t)를 **분리해서** 제공 가능한가? (불가하면 통짜 HRR 방식으로 후퇴 → 소화 해석 제약)
- [ ] 벤트가스 조성을 **고정 대표값**으로 줄 것인가, **시변 Y_i(t)** 로 줄 것인가?
- [ ] 팩 외부 표면 **경계조건으로 무엇을 가정**했는가? (단열 / 대기 대류 / 고정 열유속)
- [ ] 그 경계조건을 **시간이력 곡선으로 바꿔 재실행**이 가능한가? (불가하면 1회 반복 자체가 불가 → 1차만 하고 한계 명시)
- [ ] 벤트 시점·전파 순서가 **고정 시나리오**인가, 온도 입력에 **반응**하는가?
- [ ] 시간 해상도 Δt ≤ 1 s 확보 가능한가?

### 9.2 KRISO에 확인

- [ ] CATL 셀 데이터 및 코나 롱레인지 연소 데이터 **보유 여부**
- [ ] 데이터 **공개 및 과제 적용 가능 여부** (논문/보고서 사용 가능 여부)
- [ ] 대상 차량 확정: 코나(CATL 각형) vs IONIQ 5(LG 파우치)
- [ ] 코나 롱레인지의 CATL **팩 구조(CTP) 도입 여부** 확인
- [ ] 소화 모델 요구 수준 및 제공 가능한 정보 범위

### 9.3 기술적 확인

- [ ] `HYDROGEN FLUORIDE`의 FDS Appendix A 등재 여부
- [ ] 사용할 FDS 버전 확정 (본 문서는 FDS 6.10 계열 User Guide 기준)
- [ ] 차체 등가연료 화학식 `C6H10O1`의 타당성 — 실제 차량 가연물 구성비로 재산출 필요

---

## 10. 참고문헌

| 용도 | 문헌 |
|---|---|
| BEV 전차량 화재시험 HRR/THR, TR 개시 방법 | S. Kang et al., "Full-scale fire testing of battery electric vehicles," *Applied Energy* 332 (2023): 120497 |
| 18650 셀 연소거동, 콘칼로리미터 | Y. Fu et al., *Journal of Power Sources* 273 (2015): 216-222 |
| EV 화재 연소가스 조성 (조성 sanity check) | Hynynen et al., *Fire Safety Journal* (2023) |
| LIB 열모델 기초 | T. D. Hatchard et al., *J. Electrochem. Soc.* 148 (7) (2001): A755 |
| 3D 열남용 모델 | G.-H. Kim et al., *Journal of Power Sources* 170 (2007): 476-489 |
| 열남용 실험/계산 특성화 | C. F. Lopez et al., *J. Electrochem. Soc.* 162 (10) (2015): A2163 |
| 파우치셀 벤팅 조성·속도 | K. Zou et al., *Int. J. Heat and Mass Transfer* 195 (2022): 123133 |
| 각형셀 예압-벤팅 거동 | Z. Jia et al., *Applied Energy* 327 (2022): 120100 |
| CTP 열특성 | H. Wang et al., *Energy* 227 (2021): 120338 |
| HF 방출 정량 | A. F. Alsewailem et al., *Journal of Power Sources* 667 (2026): 239221 |
| 승용차 화재 연소거동 | Okamoto et al., *Fire Safety Journal* (2009) |
| FDS 사용법 | FDS User Guide — 9.2.7(액체연료), 12.2(lumped species), 13.1~13.2(연소) |
| FDS 이론 | FDS Technical Reference Guide — 2장, 5.1절(lumped/primitive 변환) |
