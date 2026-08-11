# 전기차 화재 FDS 검증 프로젝트 — 작업 흐름

Kang et al. (2023) *Applied Energy* **332** 120497 의 전차량 화재시험(Test 4, BEV_3, 64 kWh)을
FDS 로 재현·검증한다. 이 문서만 보고 처음부터 다시 돌릴 수 있게 쓴다.

**중요 원칙: `.fds` 파일을 직접 편집하지 않는다.** 전부 노트북이 생성한다.
손으로 고치면 다음 생성 때 통째로 덮어써진다. 파라미터를 바꾸려면 노트북의
dataclass 기본값을 고치거나 `replace()` 로 케이스를 파생시킨다.

---

## 1. 디렉터리 구조

```
/scratch/x3319a05/FDS/electric_vehicle_battery/
├── readme.md                       ← 이 문서
├── paper/
│   ├── Kang et al, 2023, ... .pdf  검증 대상 논문 (open access, CC BY)
│   └── kang2023.txt                추출 텍스트
├── report/
│   ├── KRISO_Fire_FDS_project_brief.md
│   └── 1D_to_FDS_data_interface_spec.md   1D↔3D 커플링 규약
├── input/
│   ├── build_kang_validation.ipynb ★ 입력 생성기 (이 프로젝트의 본체)
│   ├── build_fds_input.ipynb        별개 노트북 (1D↔3D 파이프라인 검증용, 건드리지 말 것)
│   ├── run_notebook.py              Jupyter 없이 .ipynb 를 헤드리스 실행
│   ├── ref_data/                    논문 Fig.8 디지타이즈 HRR 곡선
│   │   ├── pack_HRR.csv             [시간(min), HRR(MW)]  팩 발열률 ★
│   │   ├── body_HRR.csv             차체 발열률
│   │   ├── total_HRR.csv            전체 발열률
│   │   └── plot.ipynb               곡선 확인용
│   ├── data_1d/                     1D 배터리 모델 인터페이스 (현재는 더미)
│   │   ├── vent_zone{1,2,3}.csv     벤트가스 시계열 (t_s, mdot_kg_s, T_vent_K, Y_HF)
│   │   ├── casing_heat_flux.csv     팩 케이싱 열유속
│   │   └── make_dummy_1d_data.py    없으면 자동 생성됨
│   └── cases/<CHID>/                ← 생성물이 여기 쌓인다
└── results/
    ├── postprocess.ipynb            결과 분석 (_hrr.csv, _devc.csv 를 읽음)
    └── <CHID>/                      ← FDS 실행 디렉터리
```

---

## 2. 전체 흐름

```
 [1] 파라미터 조정        build_kang_validation.ipynb 의 dataclass
        │
        ▼
 [2] 입력 생성 + 자동검사  python3 run_notebook.py build_kang_validation.ipynb
        │                 → input/cases/<CHID>/<CHID>.fds
        │                 → input/cases/<CHID>/run_<CHID>.sbatch
        ▼
 [3] 입력 문법 검증(선택)  T_END=0 으로 FDS 를 직접 돌려본다
        │
        ▼
 [4] 계산 제출            sbatch input/cases/<CHID>/run_<CHID>.sbatch
        │                 → results/<CHID>/ 에 결과
        ▼
 [5] 후처리               results/postprocess.ipynb
```

---

## 3. [1~2] 입력 생성

### 3.1 파이썬 환경 — conda 쓰지 말 것

시스템 파이썬을 쓴다. conda `mpm-std` 는 임포트가 5배 느리고 **plotly 가 없어서** 3D 시각화가 죽는다.

| | 경로 | 비고 |
|---|---|---|
| 인터프리터 | `/usr/bin/python3` (3.9.18) | numpy·pandas·matplotlib·plotly·ipykernel 전부 설치돼 있음 |
| Jupyter 커널 | `fds-py39` (표시명 `Python 3.9 (FDS)`) | `~/.local/share/jupyter/kernels/fds-py39` |

노트북 metadata 의 kernelspec 이 `fds-py39` 로 박혀 있으므로 VSCode 에서 열면 자동으로 잡힌다.
잡히지 않으면 우측 상단 **Select Kernel → Python 3.9 (FDS)**.

노트북 cell 2 는 커널 여부를 감지해 백엔드를 자동으로 고른다 (커널이면 `%matplotlib inline`,
헤드리스면 `Agg`). `matplotlib.use("Agg")` 를 무조건 걸면 안 된다 — 커널에서 그림이
`Figure(...)` 텍스트로만 나온다.

### 3.2 실행

```bash
cd /scratch/x3319a05/FDS/electric_vehicle_battery/input

# 헤드리스 (권장, 30초 남짓)
python3 run_notebook.py build_kang_validation.ipynb

# 앞쪽 N개 코드셀만
python3 run_notebook.py build_kang_validation.ipynb --upto 8
```

VSCode 에서 셀 단위로 실행해도 결과는 같다. 형상만 빠르게 반복 확인할 때는 노트북 5.2절의

```python
quick_check()                          # 현재 기본값으로 형상표 + 인터랙티브 3D
quick_check(dx=0.10)                   # 격자만 바꿔서
quick_check(pack=dict(length=1.8))     # 이름이 겹치면 그룹을 명시
```

### 3.3 생성물

`input/cases/<CHID>/` 에 다음이 생긴다.

| 파일 | 내용 |
|---|---|
| `<CHID>.fds` | FDS 입력 (직접 편집 금지) |
| `run_<CHID>.sbatch` | Slurm 제출 스크립트 |
| `params.json` | 이 케이스의 전체 파라미터 + QA 결과 + 논문 값. **재현에 필요한 건 전부 여기 있다** |
| `<CHID>_domain.png` | 도메인 전체 3단면 (정적) |
| `<CHID>_geometry.html` | 인터랙티브 3D (4.7 MB, 커널 없이 브라우저로 열림) |

현재 정의된 케이스 (노트북 8절 `CASES`):

| CHID | 용도 | `t_end` | walltime |
|---|---|---|---|
| `KANG_T4` | 본 계산 | 1800 s | 24:00:00 |
| `KANG_T4_quick` | 스모크 테스트 | 300 s | 06:00:00 |

---

## 4. 조정할 값과 그 의미

차량은 **타이어 / 유리 / 프레임 / 배터리팩** 네 부품으로 나뉘고, 각 부품이 자기 형상
파라미터와 자기 재료 파라미터를 독립으로 갖는다. 전부 노트북 cell 6 의 dataclass 다.

### 4.1 좌표계 — 먼저 이해할 것

```
x = 차량 폭     (좌 −, 우 +)      차량 중심 x = 0
y = 차량 길이   (후 −, 전 +)      차량 중심 y = 0
z = 높이                          지면(플랫폼 상면) z = 0
```

**차량 중심이 도메인 원점 (0,0)** 이다. 논문 Fig.4 는 리그 구석을 원점으로 쓰므로
`(−1.550, −2.600) m` 만큼 평행이동한다. 논문 값은 mm 단위 그대로 두고 FDS 로 나갈 때만
`px()` / `py()` 를 통과시킨다.

```python
PAPER_ORIGIN = (1.550, 2.600)          # 논문 좌표에서 차량 중심
px = lambda x_mm: x_mm*mm - 1.550
py = lambda y_mm: y_mm*mm - 2.600
```

새 센서를 추가하면 **반드시 `px()`/`py()` 를 통과시킬 것.** 이걸 빼먹어서 3D 그림의
센서·리그가 차량과 어긋난 적이 있다.

`Grid.__post_init__` 이 `xmin/dx`, `ymin/dx` 가 정수인지 검사한다. 원점이 격자선 위에
있어야 좌/우 미러가 정확히 같은 셀 수로 떨어지기 때문이다. 도메인 크기를 바꿀 때
`dx` 의 정수배를 유지할 것.

### 4.2 `Grid` — 격자·도메인

| 필드 | 기본값 | 의미 |
|---|---|---|
| `xmin/xmax` | ∓4.0 | 차량 중심 기준 폭 방향 도메인 |
| `ymin/ymax` | ∓5.0 | 길이 방향 |
| `zmin/zmax` | 0 / 6.0 | 높이. 플룸이 빠져나갈 여유 |
| `dx` | **0.125** | 균일 격자. **가장 중요한 노브** |
| `nmesh` | (2,2,1) | MPI 메쉬 분할 → rank 수 |
| `cuts` | 자동 | 분할면. 센서 좌표를 2셀 이상 피해 자동 선정 |

현재 `64×80×48 = 245,760 cells`, 4 rank. `D*/dx = 16.9` 로 **권장 10~16 을 넘는다**
(D\* 는 논문 pHRR 7.25 MW 기준 특성 화재직경). 정밀도를 올리려면 `dx` 를 줄인다.

### 4.3 `Vehicle` — 차체 뼈대

| 필드 | 기본값 | 의미 |
|---|---|---|
| `length/width/height` | 4.18 / 1.80 / 1.57 | 전장·전폭·전고 (논문 Table 2) |
| `z_floor` | 0.45 | 차체 바닥 하면. 팩과 띄우려고 올린 값 |
| `z_belt` | 1.00 | 벨트라인 = 유리 하단 |
| `cabin_len` | 2.00 | 캐빈(사람 타는 구역) 길이 |
| `cabin_dy` | 0.00 | 캐빈 전후 오프셋 (0 = 전후 대칭) |
| `cabin_inset` | 0.15 | 편측 폭 축소 → 캐빈 반폭 = width/2 − inset |
| `pillar_b` | 0.25 | B필러 폭. y 대칭을 위해 2셀(=2·dx) 필요 |

### 4.4 `Tire` — 타이어 (235/45 R18)

외경은 규격에서 계산한다: `rim_inch×0.0254 + 2×section_width×aspect_ratio` = 668.7 mm.

| 필드 | 기본값 | 의미 |
|---|---|---|
| `section_width_mm` / `aspect_ratio_pct` / `rim_inch` | 235 / 45 / 18 | 타이어 규격 |
| `wheelbase` | 2.60 | 축거 → 축 위치 y = ±1.30 |
| `outer_x` | 0.85 | 타이어 바깥면 \|x\| |
| `mass_kg` | 40.0 | 4짝 합. 타이어 `THICKNESS` 역산에 쓴다 |
| 재료 | density 1100, cp 1.8, k 0.25, T_boil 420, ΔH_rxn 2200 | 프레임과 독립 |

### 4.5 `Glass` — 유리

유리는 형상에서 **빼지 않는다.** 프레임과 다른 SURF(`CAR_GLASS`)로 채워 넣어
물성을 독립으로 손볼 수 있게 한다.

| 필드 | 기본값 | 의미 |
|---|---|---|
| `thickness` | 0.006 | 유리 두께 |
| `density/specific_heat/conductivity/emissivity` | 2500 / 0.84 / 1.05 / 0.90 | 소다석회유리 |
| `combustible` | False | True 면 프레임 재료로 연소시킨다 |
| `open_windows` | `("FL","RL")` | 열린 창. 논문 2.4절 — 좌측 앞·뒷 도어창 반개방 |
| `open_height` | 0.25 | 유리 하단에서 이만큼 내림 (창을 내린 높이) |

`F`/`R` = 앞/뒤, `L`/`R` = 좌/우. 좌측(`L`)은 x 음수 쪽이다.

### 4.6 `Frame` — 차체 프레임

| 필드 | 기본값 | 의미 |
|---|---|---|
| `shell` | 0.125 | **쉘 두께(형상)**. 내부는 비어 있다. 1셀 |
| `heat_of_reaction` | 1800 | **pHRR·성장속도 주 튜닝 노브** |
| `boiling_temperature` | 380 | 증발 모델 |
| `heat_of_combustion` | 28800 | 논문 Table 6 실측 (고정) |
| `fuel_mass_kg` | 262.0 | 논문 Table 6 소실질량 (타이어 포함, 고정) |
| `formula` | C6H10O1 | 등가 연료 |
| `soot_yield / co_yield / radiative_fraction` | 0.10 / 0.05 / 0.35 | 연소 생성물 |

`THICKNESS` 는 추정하지 않는다. 격자에 래스터화해 **가스와 접한 면만** 세어 실제
노출 연소면적을 구하고 `fuel_mass_kg` 로 나눠 **역산**한다. 타이어는 `Tire.mass_kg`,
프레임은 `fuel_mass_kg − Tire.mass_kg` 로 각자 독립 역산한다.

### 4.7 `Pack` — 배터리 (단순 직육면체)

셀·모듈은 무시한다.

| 필드 | 기본값 | 의미 |
|---|---|---|
| `length/width/height` | 1.60 / 1.20 / 0.15 | y / x / z |
| `gap_to_floor` | 0.10 | **팩 상면 ~ 차체 바닥 하면 간격** |
| `z_bot` | None | 직접 지정할 때만. None → `gap_to_floor` 에서 역산 |
| `dy` | 0.0 | 차량 중심 대비 오프셋 |

6면 전부에 발열 경계조건을 주므로 **지면·차체 어디에도 닿으면 안 된다.**
닿은 면은 기체와 접하지 않아 `&VENT` 가 죽는다. 최소 1셀씩 띄울 것.

### 4.8 `PackHRR` — 팩 발열률 (실측 곡선 직접 지정)

| 필드 | 기본값 | 의미 |
|---|---|---|
| `csv` | `pack_HRR.csv` | `input/ref_data/` 안의 파일. [시간(min), HRR(MW)] 2열 |
| `t_unit` | 60.0 | csv 시간 → 초 |
| `q_unit` | 1000.0 | csv HRR → kW |
| `scale` | 1.0 | 곡선 전체 배율 (튜닝 노브) |
| `clip_negative` | True | 디지타이즈 잡음으로 생긴 음수 HRR 제거 |

**팩 6면에 같은 `HRRPUA` 를 준다.** 그러면 면별 기여가 면적에 자동으로 비례하고
6면 합이 곡선값과 일치한다.

```
HRRPUA = pHRR / A_total = 1519.5 kW / 4.4375 m² = 342.43 kW/m²
6면 합 = HRRPUA × A_total × RAMP_Q(t) = 곡선값
```

REAC 가 둘(`BATT`/`BODY`)이므로 `SPEC_ID='BATTERY_GAS'` 를 반드시 명시한다.
안 쓰면 FDS 가 첫 번째 REAC 의 FUEL 을 집어간다 (User Guide 2702행).

### 4.9 `BatteryGas` — 벤트가스 조성

`composition` 은 부피분율 dict (H2 28, CO 23, CO2 28, CH4 12, C2H4 9).
`heat_of_combustion=None` 이면 조성에서 자동 유도한다 (현재 14.6 MJ/kg).
`track_hf=True` 면 HF 를 비반응 추적종으로 함께 방출한다.

### 4.10 `Case` — 케이스 묶음

`chid`, `title`, `t_end`(1800 s), `tmpa`(20 ℃), 위 dataclass 들, 출력 주기
(`dt_hrr`/`dt_devc` 1 s, `dt_slcf` 5 s, `dt_bndf` 20 s), `walltime`,
`ramp_eps`(0.004 — RAMP 점 솎아내는 RDP 허용오차).

### 4.11 파라미터 바꾸는 법

```python
from dataclasses import replace

# 격자만 조이기
c = replace(BASE, grid=replace(BASE.grid, dx=0.10))

# 팩 위치·크기
c = replace(BASE, pack=replace(BASE.pack, gap_to_floor=0.15, height=0.20))

# HRR 곡선 배율
c = replace(BASE, hrr=replace(BASE.hrr, scale=1.2))

# 또는 quick_check 처럼 필드명만 (그룹 자동 판별)
c = make_case(chid="TEST", dx=0.10, gap_to_floor=0.15)
```

---

## 5. 자동 검사 — 통과 여부를 여기서 판단한다

노트북이 매 케이스마다 아래를 출력한다. **하나라도 `!!` 가 뜨면 FDS 를 돌리지 말 것.**

```
격자          : 64 x 80 x 48 = 245,760 cells, dx=0.125 m
D* (7.25 MW)  : 2.12 m,  D*/dx = 16.9  (권장 10~16)
노출면적      : 프레임 38.69 m2  유리 3.56  타이어 4.12  팩 4.44
THICKNESS     : 프레임 6.38 mm (222 kg 역산), 타이어 8.82 mm (40 kg 역산)
차체 THR      : 7.55 GJ   (논문 Table 4: 7.53 GJ)
좌우 대칭     : 구조 통과  |  유리 4개 비대칭 (좌측 창 개방 - 의도)
프레임 연결   : 1개 성분 (전부 하나로 연결)
팩 6면 노출   : 6면 전부 기체와 접함
팩 위치       : z 0.250~0.375 m  |  지상고 0.250  바닥(0.500)과 간격 0.125 m
실내 중공     : 2.867 m3 (창 닫은 기준)
스냅 ...      : 요청 → 격자 (오차)
DEVC 배치 검사 통과 (16개 점 센서)
```

| 검사 | 무엇을 보는가 | 실패하면 |
|---|---|---|
| **좌우 대칭** | 모든 부재가 x=0 에 대해 미러인가 | 유리 4개 비대칭은 정상(좌측 창만 개방). 구조가 뜨면 스냅/좌표 버그 |
| **프레임 연결** | `CAR_BODY` 셀의 6-이웃 연결성분 개수 | 2 이상이면 캐빈이 차체에서 떠 있다. 판이 모서리로만 닿는 게 원인 |
| **팩 6면 노출** | 각 면이 기체와 접하는가 | 막히면 그 면의 `&VENT` 가 죽어 HRR 이 빠진다 |
| **실내 중공** | 바깥에서 기체로 도달 못 하는 밀폐 체적 | 0 이면 내부가 안 비었거나 쉘에 구멍 |
| **DEVC 배치** | 점 센서가 solid 내부/메쉬 경계면에 있는가 | 걸리면 FDS `ERROR(427)` |
| **스냅 오차** | 요청 치수 vs 격자에 떨어진 치수 | 큰 오차는 `dx` 를 줄여야 한다는 신호 |

### 스냅 오차 현황 (`dx=0.125`)

```
차량 전폭    1.800 → 1.750  ( -50 mm)
차량 전장    4.180 → 4.250  ( +70 mm)
팩 폭        1.200 → 1.250  ( +50 mm)
팩 길이      1.600 → 1.500  (-100 mm)
팩 높이      0.150 → 0.125  ( -25 mm)   ← -17%, 1셀로 뭉개짐
팩-바닥 간격 0.100 → 0.125  ( +25 mm)
타이어 폭    0.235 → 0.250  ( +15 mm)
타이어 외경  0.669 → 0.625  ( -44 mm)   ← -7%
```

---

## 6. [3] 입력 문법 검증 (권장)

제출 전에 FDS 로 직접 읽혀 본다. `T_END=0` 이면 셋업만 하고 끝난다. 30초면 된다.

```bash
cd /tmp && mkdir -p fdschk && cd fdschk
sed -e "s/&TIME T_END=[0-9.]*/\&TIME T_END=0.0/" \
    -e "s/CHID='KANG_T4'/CHID='CHK'/" \
    /scratch/x3319a05/FDS/electric_vehicle_battery/input/cases/KANG_T4/KANG_T4.fds > CHK.fds

source /scratch/x3319a05/FDS/setup_docs/scripts/fds_env_kisti.sh
mpiexec -n 4 "$FDS_BIN" CHK.fds
# 정상: "STOP: Set-up only (CHID: CHK)"
```

이 단계에서 실제로 `ERROR(394) RAMP ... must be monotonically increasing` 을 잡은 적이 있다.
노트북 QA 는 통과했는데 FDS 가 거부한 사례이므로 생략하지 말 것.

---

## 7. [4] 계산 제출

```bash
cd /scratch/x3319a05/FDS/electric_vehicle_battery
sbatch input/cases/KANG_T4/run_KANG_T4.sbatch

squeue -u $USER          # 상태 확인
```

sbatch 스크립트가 하는 일:

```bash
#SBATCH -p cpu  --nodes=1  --ntasks=4  --cpus-per-task=1  --time=24:00:00
#SBATCH --comment=etc

source /scratch/x3319a05/FDS/setup_docs/scripts/fds_env_kisti.sh
export OMP_NUM_THREADS=1 I_MPI_FABRICS=shm:ofi I_MPI_PIN=1
RUNDIR=<ROOT>/results/KANG_T4
mkdir -p "$RUNDIR"; cp <입력>.fds "$RUNDIR"/; cd "$RUNDIR"
mpiexec -n "$SLURM_NTASKS" "$FDS_BIN" KANG_T4.fds
```

- `--ntasks` 는 `Grid.nmesh` 의 곱과 같아야 한다 (현재 2×2×1 = 4).
- 파티션은 `cpu`. GPU 파티션 쓰지 말 것.
- `--comment=etc` 는 Neuron 과제 분류용으로 이 프로젝트가 계속 써 온 값이다.
  (없을 때 거부되는지는 확인하지 않았다. 기존 스크립트를 그대로 따르는 편이 안전하다.)
- 환경 스크립트가 `intel/25.3.0`, `mpi/impi-21.17`, `mkl/2025.3` 을 로드하고
  `I_MPI_ROOT` 를 직접 잡아준다 (모듈이 안 잡아줘서 MPI_Init 이 죽는 문제 회피).

---

## 8. 결과 위치

```
results/<CHID>/
├── <CHID>.fds              실행에 쓰인 입력 사본
├── <CHID>.out              FDS 로그 (진행률·경고)
├── <CHID>_hrr.csv          HRR 시계열 ★
├── <CHID>_devc.csv         DEVC 시계열 (TC, 열유속계) ★
├── <CHID>_mass.csv         질량 (MASS_FILE=T)
├── <CHID>_*.sf / .bf / .q  Smokeview 용 슬라이스·경계·플롯3D
├── <CHID>.smv              Smokeview 진입점
└── slurm-<jobid>.{out,err}
```

Smokeview 는 이 저장소 안에 없다. 쓰려면 따로 빌드해야 하고, 로그인 노드에는 디스플레이가
없으므로 헤드리스 처리가 필요하다. 형상 확인만 목적이라면 노트북이 굽는
`input/cases/<CHID>/<CHID>_geometry.html` 로 충분하다 (브라우저만 있으면 회전·확대·호버 가능).

---

## 9. 후처리 · 검증 목표

`results/postprocess.ipynb` 에서 `_hrr.csv`, `_devc.csv` 를 읽어 비교한다.

| # | 항목 | 논문 값 (Test 4) | 비교 방법 |
|---|---|---|---|
| 1 | pHRR | 7.25 MW | `_hrr.csv` 최대값 |
| 2 | pHRR 도달 시각 | 11~17 분 | 최대값 시각 |
| 3 | THR | 9.03 GJ | ∫HRR dt |
| 4 | 화재성장계수 θ | 0.0085~0.020 MW/s² | 성장구간 `Q = θt²` 피팅 |
| 5 | 소실질량 Δm | 296 kg (17.6 %) | `_mass.csv` |
| 6 | 팩 vs 차체 기여 | 1.30 / 7.53 GJ | `HRR_BATT` / `HRR_BODY` 적분 |
| 7 | 천장 가스온도 | Fig. 9 (피크 > 900 ℃) | `TC_G*` 6개 |
| 8 | 인접차량 입사열유속 | Fig. 10 | `HF_F/R/FD/RD` (+`_tot`) |

주 튜닝 노브는 `Frame.heat_of_reaction` 이다. `THICKNESS`(총 THR)는 소실질량 262 kg 으로
이미 고정돼 있으므로, 남은 자유도는 연소 **속도**뿐이다.

### 센서 배치 (논문 Fig. 4)

| ID | 위치 | z |
|---|---|---|
| `TC_GB / GW / GFW / GR / GRW / GCRW` | 천장 수냉파이프 열전대 6개 | 2.270 m |
| `TC_FW / TC_RW` | 좌측 앞·뒷 도어창 중간높이 (개구 안의 기체) | 1.270 m |
| `HF_F / HF_R / HF_FD / HF_RD` | Schmidt-Boelter 열유속계 4개, 리그 모서리 | 1.270 m |

열유속계는 `RADIOMETER`(복사만) 와 `GAUGE HEAT FLUX`(복사+대류, `_tot` 접미사) 두 개씩 낸다.
FDS 에서 이 둘은 **고체상 quantity** 라 벽면이 필요하다. 허공에 두면 `ERROR(427)` 로 죽으므로
1셀 블록(`SURF_ID='HF_GAUGE'`, `TMP_FRONT`=주변온도)을 세우고 차량을 향한 면에 붙였다.
실제 게이지도 수냉 몸체라 물리적으로도 맞다.

반면 `TC_FW`/`TC_RW` 는 **기체상** 열전대라 공중에 떠 있는 게 맞다. 논문 2.3절이
"positioned at the mid-height of the vehicle's front- and rear-seat windows" 라 하고,
2.4절이 좌측 창을 반쯤 열었다고 하므로 그 개구 안의 기체 온도를 재는 것이다.

---

## 10. 함정 모음 — 실제로 당한 것들

1. **conda 환경 쓰지 말 것.** `mpm-std` 는 plotly 가 없어 3D 시각화가 죽고 임포트가 5배 느리다.
   `/usr/bin/python3` + `fds-py39` 커널을 쓴다.

2. **`matplotlib.use("Agg")` 를 무조건 걸지 말 것.** 커널에서 그림이 안 뜨고
   `Figure(1700x580)` 텍스트만 남는다. cell 2 가 환경을 감지해 자동 분기한다.

3. **새 센서/장비는 반드시 `px()`/`py()` 를 통과시킬 것.** 논문 좌표(mm)를 그대로 그리면
   차량만 원점으로 옮겨져 장비가 어긋난다. `.fds` 는 맞는데 그림만 틀리는 형태로 나타난다.

4. **RAMP 의 T 는 순증가여야 한다 (`ERROR(394)`).** `pack_HRR.csv` 는 오름차순이지만
   `16.3551401869 min` 에 두 점이 있고 간격이 `2.3e-13 s` 다 (디지타이즈된 수직 구간).
   소수점으로 찍으면 뭉개져 FDS 가 거부한다. `make_ramp` 가 형식 최소단위만큼 밀어 해결한다.
   **새 CSV 를 넣을 때마다 이 검사가 돈다.**

5. **음수 HRR.** `pack_HRR.csv` 에 −0.0129 MW 가 하나 있다. 그대로 두면 음의 질량유속이 나간다.
   `PackHRR.clip_negative=True` 가 막는다.

6. **판이 모서리로만 닿으면 끊긴 것이다.** 6-이웃 연결성 기준이므로, 벨트레일과 데크가
   x·y 로 어긋난 채 z 만 인접하면 대각선 접촉이라 분리된다. 데크를 레일 폭만큼 안쪽까지 물려야 한다.

7. **두께 0 인 `&VENT` 패치를 그림에서 부풀릴 때 방향 주의.** 바깥으로 부풀리면
   팩과 차체 사이 1셀 간격을 덮어 붙어 보인다. 안쪽으로 부풀려야 한다.

8. **팩은 지면·차체와 반드시 이격.** 6면 전부에 `&VENT` 를 붙이므로 닿은 면은 죽는다.

9. **`&TIME T_END` 와 HRR 데이터 구간을 맞출 것.** 현재 `t_end=1800 s`(30분)인데
   `pack_HRR.csv` 는 69.7분까지 있다. THR 검증하려면 4200 s 로 늘려야 한다.

10. **`--comment=etc` 없으면 Neuron 에서 제출이 거부된다.**

---

## 11. 알려진 미결 사항

- **`t_end` 가 HRR 데이터보다 짧다.** 1800 s vs 4183 s. pHRR(18.5분)은 포함되나 THR 검증 불가.
- **`TC_FW` 가 B필러에서 5 mm 거리에 있다.** 캐빈을 명시 파라미터로 배치하면서 논문 센서
  y좌표와의 연결이 끊겼다. `cabin_len=1.600`, `cabin_dy=−0.270` 으로 바꾸면 두 센서가 각
  창 중앙으로 들어온다 (캐빈만 전후 비대칭이 됨). **미적용.**
- **`PACK_CASE` SURF 의 `NET_HEAT_FLUX` 가 무효.** 팩 6면이 전부 `VENT_PACK` 으로 덮여
  적용되지 않는다. `data_1d/casing_heat_flux.csv` 경로는 현재 死코드.
- **`data_1d/` 는 더미 데이터다.** 1D 배터리 모델 실데이터가 오면 재설계 필요.
  현재 1D 기준 팩 THR 은 0.40 GJ 로 논문 1.30 GJ 에 못 미친다 (벤트가스만으로는 부족).
  그래서 팩 발열은 1D 가 아니라 `ref_data/pack_HRR.csv` 실측 곡선으로 직접 준다.
- **`D*/dx = 16.9`** 로 권장 범위(10~16)를 벗어나 있고, 팩 높이가 1셀로 뭉개져 있다.
  `dx=0.05` 면 해소되지만 셀이 약 16배(3.84 M)가 된다.
