# Marine Engine-Room Fire — FDS 워크플로우

Lan et al. (2023, *Ocean Engineering* 281:114890, Fig 1) 선박 기관실 화재를 FDS로
재현하는 프로젝트입니다. 입력 생성 → 클러스터 실행(SLURM) → 후처리/시각화까지의
전 과정을 다룹니다.

이 문서 하나로 **빌드 → 입력 생성 → 실행 → 분석**을 처음부터 끝까지 할 수 있습니다.

---

## 0. 한눈에 보기 (Quick Start)

```bash
ENG=/shared/home/wel1come1234/workspace/FDS/Engineroom
cd $ENG

# 1) 입력(.fds) 생성  — 예: 1 m 화재, HRR 10 s에 peak, 환기 20 s부터
python3 gen_engine_room_wall.py \
    --chid fire1_p10_v20_M5 --out Inputs/fire1_p10_v20_M5.fds \
    --ijk 180 140 40 --mesh-split 4 4 2 --t-end 360 --floor-thickness 1.5 \
    --fire-diameter 1.0 --hrr-t2-tpeak 10 --vent-start 20

# 2) 실행용 sbatch를 만들고 제출 (아래 4장 참고, 기존 스크립트 복붙이 가장 빠름)
sbatch $ENG/sbatch/run_fire1_p10_v20_M5.sbatch

# 3) 결과 시각화 (miniconda python 사용)
/shared/home/wel1come1234/miniconda3/bin/python3 \
    Analysis/flame/plot_flame_compare.py fire1
```

---

## 1. 디렉토리 구조

```
FDS/
├── Build/impi_intel_linux/fds_impi_intel_linux   ← FDS 실행 바이너리 (Intel MPI)
└── Engineroom/
    ├── gen_engine_room_wall.py   ← 입력(.fds) 생성기 (핵심 스크립트)
    ├── README.md                 ← 이 문서
    ├── Inputs/                    ← 생성된 .fds 원본 (canonical, 실행 시 읽는 파일)
    ├── sbatch/                    ← 케이스별 SLURM 제출 스크립트 (모두 여기 모음)
    ├── Results/<chid>/            ← 실행 출력 (.out .smv 슬라이스 .s3d 로그 등)
    └── Analysis/
        ├── flame/                ← 화염 metric + 엔진상부 온도 비교 플롯
        ├── visualize/            ← 온도 슬라이스(컨투어+유선) 시각화
        └── convergence/          ← 격자수렴 / Δy 온도 프로파일 플롯
```

**핵심 규칙**: 실행은 `sbatch/`의 스크립트가 담당하며, **입력은 `Inputs/`에서 읽고
출력은 `Results/<chid>/`에 쌓입니다**. `Inputs/`의 원본은 실행 중 변경되지 않습니다.

---

## 2. 사전 준비 / 빌드

### 2.1 FDS 실행 바이너리

이미 빌드되어 있습니다:
```
/shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux
```
sbatch 스크립트가 이 절대경로를 직접 호출하므로, **정상적으로는 다시 빌드할 필요가
없습니다.** 소스를 고쳐 다시 빌드해야 할 때만 아래를 수행합니다.

### 2.2 (필요 시) 재빌드 — Intel oneAPI 2023.2

```bash
source /opt/intel/oneapi/setvars.sh              # Intel 컴파일러 + MPI + MKL 환경
cd /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux
./make_fds.sh --no-libs                          # 라이브러리 재빌드 없이 FDS만
```
> 참고: 이 환경(oneAPI 2023.2)은 MKL 라이브러리가 `lib/intel64`에 있습니다. 빌드
> 완료 후 `fds_impi_intel_linux` 바이너리가 갱신됩니다.

### 2.3 후처리용 Python

분석 스크립트는 `fdsreader`·`numpy`·`matplotlib`가 있는 **miniconda** 파이썬을
사용합니다:
```
/shared/home/wel1come1234/miniconda3/bin/python3     # fdsreader 1.11.7
```
Jupyter 노트북으로 돌릴 때는 커널 **"Python 3"** 또는 **"Python (miniconda-fds)"**
를 선택하세요 (둘 다 위 파이썬의 절대경로로 등록되어 있음).

---

## 3. 입력 생성 — `gen_engine_room_wall.py`

기관실 지오메트리(벽·문·장비·화재 pool·기계환기 vent)를 담은 `.fds` 파일을
생성합니다. 파일 상단의 **USER-EDITABLE SETTINGS** 블록에서 기본값을 바꿀 수도 있고,
아래 **CLI 플래그**로 한 번씩 덮어쓸 수도 있습니다.

### 3.1 시나리오 3대 knob (가장 자주 쓰는 것)

| 목적 | 플래그 | 예 | 설명 |
|---|---|---|---|
| **화재 크기** | `--fire-diameter D` | `--fire-diameter 1.0` | 중심 (8.4, 1.45)의 정사각 화염, 변 D m. `--fire-xb`보다 간편 |
| **HRR peak 시각** | `--hrr-t2-tpeak T` | `--hrr-t2-tpeak 10` | t² 성장으로 T초에 peak 도달, 이후 유지 |
| **환기 시작 시각** | `--vent-start T` | `--vent-start 20` | T초까지 vent 닫힘(화재만), 이후 full로 램프 |

> HRRPUA는 863 kW/m²로 고정입니다. 따라서 **화염 면적이 커지면 총 발열량(HRR)도
> 함께 증가**합니다 (예: 1.0 m² → 863 kW, 0.79 m² → 683 kW).

### 3.2 그리드 / 도메인 / 시간

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--chid NAME` | engine_room | 케이스 ID (출력 파일 접두사) |
| `--out PATH` | inputs/engine_room.fds | 출력 .fds 경로 |
| `--ijk NX NY NZ` | 130 100 30 | 전체 셀 수. **M5 기준 = `180 140 40`** (약 100만 셀) |
| `--mesh-split MX MY MZ` | 1 1 1 | MPI용 서브메쉬 분할. 곱 = **MPI 랭크 수**. IJK를 나눠떨어져야 함 |
| `--t-end T` | 600 | 종료 시각 [s] (현재 스터디는 360) |
| `--floor-thickness M` | 0.2 | 강철 바닥 두께 [m] (현재 스터디는 1.5) |

> **중요**: `--mesh-split`의 곱은 sbatch의 `-np` 값과 **반드시 같아야** 합니다.
> 이 FDS 빌드는 "메쉬 수 = MPI 랭크 수"를 요구합니다(아니면 ERROR 115).
> M5 표준: `--mesh-split 4 4 2` → 32 메쉬 → `-np 32`.

### 3.3 환기 (Lan et al. Fig 2 / Table 4)

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--ventilation-method {0,1,2,3}` | 2 | 0=환기없음, 1/2/3=논문 Method 1/2/3 (2=대칭 2흡기+2배기) |
| `--ventilation-velocity V` | 1.0 | 각 vent 법선 속도 [m/s] (논문 1 또는 3) |
| `--vent-start T` | 0.0 | 환기 시작 시각 [s] (3.1 참고) |
| `--vent-ramp-up DT` | 1.0 | vent 0→full 램프 시간 [s] |

### 3.4 화재 / 연료 / 출력 cadence (고급)

| 플래그 | 설명 |
|---|---|
| `--fire-xb XMIN XMAX YMIN YMAX` | 화염 footprint를 직접 지정 (`--fire-diameter`가 있으면 무시됨) |
| `--fire-off T` | T초에 화재 소화 (HRR→0) |
| `--fire-start T` | T초까지 화재 지연 점화 후 t² 성장 |
| `--hrr-peak KW` | peak HRR [kW] (기본 863) |
| `--hrr-csv FILE` | 외부 (t_s, q_kw) CSV로 HRR 곡선 지정 (t²보다 우선) |
| `--coldflow` | 화재 없이 환기만 (cold-flow 검증용) |
| `--dt-devc / --dt-hrr / --dt-slcf / --dt-bndf` | 각 출력 간격 [s] |

전체 목록은 `python3 gen_engine_room_wall.py --help`.

### 3.5 생성 예시

```bash
cd /shared/home/wel1come1234/workspace/FDS/Engineroom

# 1 m 화재 / HRR 10 s peak / 환기 20 s부터 (M5, 32메쉬, 360 s)
python3 gen_engine_room_wall.py \
    --chid fire1_p10_v20_M5 --out Inputs/fire1_p10_v20_M5.fds \
    --ijk 180 140 40 --mesh-split 4 4 2 --t-end 360 --floor-thickness 1.5 \
    --fire-diameter 1.0 --hrr-t2-tpeak 10 --vent-start 20
```
생성 후 확인:
```bash
grep -m1 "! Fire" Inputs/fire1_p10_v20_M5.fds          # 화염 면적/HRR
grep "fire_hrr" Inputs/fire1_p10_v20_M5.fds | grep "F=1.000000" | head -1   # peak 시각
grep "vent_ramp" Inputs/fire1_p10_v20_M5.fds           # 환기 램프
```

---

## 4. 실행 — SLURM `sbatch`

케이스별 제출 스크립트는 모두 `sbatch/`에 있습니다. 각 스크립트는:

1. `--output` → `Results/<chid>/<chid>.slurm.<jobid>.log` (절대경로)
2. `mkdir -p Results/<chid>` → 없으면 생성
3. `cd Results/<chid>` → FDS 출력이 여기 쌓임
4. `mpirun -np 32 <FDS binary> Inputs/<chid>.fds` → **원본 입력**을 읽음

### 4.1 새 케이스용 sbatch 만들기

기존 스크립트를 복사해 chid만 바꾸는 게 가장 빠릅니다. 표준 템플릿:

```bash
#!/bin/bash
#SBATCH --job-name=f1p10v20
#SBATCH --partition=batch
#SBATCH --exclude=cpu04                 # cpu04는 문제 노드 → 항상 제외
#SBATCH --nodes=1
#SBATCH --ntasks=32                     # = 메쉬 수 (mesh-split 곱)
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --time=36:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_M5/fire1_p10_v20_M5.slurm.%j.log

set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm                # 단일 노드 → 공유메모리 fabric
export I_MPI_HYDRA_BOOTSTRAP=fork
ENG=/shared/home/wel1come1234/workspace/FDS/Engineroom
mkdir -p $ENG/Results/fire1_p10_v20_M5
cd       $ENG/Results/fire1_p10_v20_M5
echo "host=$(hostname) ranks=32 start=$(date)"
stdbuf -oL -eL mpirun -np 32 \
    /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux \
    $ENG/Inputs/fire1_p10_v20_M5.fds
echo "done=$(date)"
```

### 4.2 제출 / 모니터링

```bash
ENG=/shared/home/wel1come1234/workspace/FDS/Engineroom
sbatch $ENG/sbatch/run_fire1_p10_v20_M5.sbatch     # 제출
squeue -u $USER                                    # 큐 확인
# 진행 상황(시뮬레이션 시각):
grep "Simulation Time" $ENG/Results/fire1_p10_v20_M5/*.slurm.*.log | tail -1
```

### 4.3 노드 / 병렬 관련 주의

- **`--exclude=cpu04`**: cpu04는 문제가 있어 항상 제외합니다. (노드 지정 시 cpu03/05/06 사용)
- **`-np` = 메쉬 수**: 32메쉬면 `--ntasks 32` & `mpirun -np 32`. 불일치 시 즉시 ERROR 115.
- **단일 노드**: 위 fabric 설정(shm/fork)은 1노드 전용입니다. batch 파티션 노드는 코어 64개.
- **`--time`**: M5 32랭크 360 s 런은 여유롭게 36:00:00으로 잡습니다 (48랭크가 6h에 280 s까지였음).

---

## 5. 후처리 / 시각화 — `Analysis/`

모든 스크립트는 miniconda 파이썬으로 실행합니다:
`/shared/home/wel1come1234/miniconda3/bin/python3`.
케이스 시리즈(예: `peak`, `fire1`)별로 하위 폴더에 결과를 저장합니다.

### 5.1 화염 metric + 엔진상부 온도 — `Analysis/flame/`

```bash
cd Analysis/flame
$PY plot_flame_compare.py peak      # → flame/peak/  (0.79 m² 시리즈)
$PY plot_flame_compare.py fire1     # → flame/fire1/ (1.0 m² 시리즈)
```
출력: `cmp_fig9_Ly.png`, `cmp_fig10_1_Hf.png`, `cmp_fig10_2_thetaz.png`,
`cmp_fig9_10_panel.png`(3-패널), `engine_temp_profile_compare.png`.
논문 기준 CSV(`Fig9.csv`, `Fig10_1.csv`, `Fig10_2.csv`, `engine_ref.csv`)는
`flame/` 최상단에서 읽습니다.

### 5.2 온도 슬라이스 (컨투어+유선) — `Analysis/visualize/`

```bash
cd Analysis/visualize
$PY plot_slices_series.py peak      # → vis/peak/<case>/slice_*.png
$PY plot_slices_series.py fire1     # → vis/fire1/<case>/slice_*.png
```
슬라이스: YZ(x=8.1, 8.4), XZ(y=1.45), XY(z=2.0). 시간평균 창은 스크립트 상단 `WIN`.

### 5.3 Δy 온도 프로파일 — `Analysis/convergence/`

```bash
cd Analysis/convergence
$PY plot_dy_profiles.py both        # → convergence/{peak,fire1}/*_dy_*.png
```
한 그림에 여러 Δy(0.0–1.4 m)의 T(z)를 겹쳐 그립니다. 논문 격자수렴 기준
(`ref_Mesh1.csv`, `ref_Mesh5.csv`)을 검은 선으로 오버레이. 노트북 버전도 있음
(`plot_dy_profiles.ipynb`).

> `$PY` = `/shared/home/wel1come1234/miniconda3/bin/python3`

### 5.4 참고

- 컨투어 플롯(`contourf`)에는 `contourpy`가 필요합니다. 깨져 있으면:
  `$PY -m pip install --force-reinstall --no-cache-dir contourpy`
- 3D 필드(SmokeView)는 `Results/<chid>/<chid>.smv`를 SmokeView로 직접 열면 됩니다.

---

## 6. 네이밍 규칙

케이스 ID(`--chid`)로 시나리오가 한눈에 보이도록 합니다. 예시:

| chid | 의미 |
|---|---|
| `peak10_M5` | 0.79 m² 화재, HRR 10 s peak, 환기 t=0, M5 그리드 |
| `peak10_fire1_M5` | **1.0 m²** 화재, HRR 10 s peak, 환기 t=0 |
| `fire1_p10_v20_M5` | 1.0 m² 화재, HRR 10 s peak, **환기 20 s 시작** |
| `warm_M5` / `warm_M5_v20` | 화재만 굽다 환기 60/20 s 시작 (48메쉬 6×4×2) |

`Inputs/<chid>.fds`, `sbatch/run_<chid>.sbatch`, `Results/<chid>/`가 같은 `<chid>`로
묶입니다.

---

## 7. 문제 해결 (Troubleshooting)

| 증상 | 원인 / 해결 |
|---|---|
| `ERROR(115): Number of meshes exceeds number of MPI processes` | `-np` ≠ 메쉬 수. `mesh-split` 곱과 `--ntasks`/`-np`를 일치시킬 것 |
| 잡이 곧바로 죽음 (`cd: No such file or directory`) | Results 디렉토리 없음 → 스크립트에 `mkdir -p` 포함되어 있는지 확인 |
| 노트북 `ModuleNotFoundError: numpy` | IDE가 다른 파이썬 커널 선택. **"Python 3"** 또는 **"Python (miniconda-fds)"** 커널로 변경 |
| `ModuleNotFoundError: contourpy` (슬라이스 플롯) | `$PY -m pip install --force-reinstall --no-cache-dir contourpy` |
| DEVC `gridconv_T_dy15 ... OMITTED` 경고 | 진단 온도 라인 하나가 벽 속으로 들어가 자동 생략됨. 시뮬레이션엔 영향 없음 |
| 결과가 `Results/`가 아닌 다른 곳에 생김 | sbatch가 `cd Results/<chid>` 후 실행하는지 확인 (FDS는 CWD에 출력) |

---

## 8. 현재 보유 케이스

- **peak-time 스터디**: `peak{05,10,15,20}_M5` (0.79 m²), `peak{05,10,15,20}_fire1_M5` (1.0 m²)
  — 환기 t=0, HRR peak 5/10/15/20 s 비교
- **vent-timing 스터디**: `warm_M5`(환기 60 s), `warm_M5_v20`(20 s), `warm_M5_v40`(40 s) — 48메쉬
- **신규**: `fire1_p10_v20_M5` — 1 m 화재, HRR 10 s peak, 환기 20 s 시작

모두 `sbatch/run_<chid>.sbatch`로 재실행 가능합니다.
