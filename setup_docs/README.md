# FDS 환경 구축 문서

본 디렉터리는 `/shared/home/wel1come1234/workspace/fds`의 FDS (Fire Dynamics Simulator)를 본 서버(login01, Ubuntu 20.04 + Slurm + Intel oneAPI 2023.2)에 빌드/실행하기 위한 단계별 한국어 가이드이다.

> 🇰🇷 **KISTI Neuron에서 빌드하는 경우 → [08_kisti_neuron.md](08_kisti_neuron.md)를 먼저 보라.** 모듈 셋업, `I_MPI_ROOT` 수동 export(필수), MKL 패치 적용 여부가 본 문서들과 다르다. 검증된 환경 스크립트는 [`scripts/fds_env_kisti.sh`](scripts/fds_env_kisti.sh).

## 빠른 시작 (TL;DR)

```bash
# 1. 환경 로드 (모든 경로/환경변수가 한 번에 잡힘)
source /shared/home/wel1come1234/workspace/fds/setup_docs/scripts/fds_env.sh

# 2. 3rd-party 소스 준비 (이미 본 서버에는 fds/deps/ 안에 다 있음 — 새 머신에서만)
mkdir -p $FIREMODELS                  # FIREMODELS = $FDS_ROOT/deps
cd $FIREMODELS
git clone --branch master https://github.com/hypre-space/hypre.git hypre
mkdir -p hypre/build
git clone --branch main   https://github.com/LLNL/sundials.git sundials
[ -L fds ] || ln -s .. fds            # FIREMODELS/fds → FDS 루트

# 3. FDS 빌드 (HYPRE/SUNDIALS도 자동 빌드됨)
cd $FIREMODELS/fds/Build/impi_intel_linux
./make_fds.sh

# 4. 동작 확인
./fds_impi_intel_linux 2>&1 | head -3
```

성공하면 실행파일은:
```
/shared/home/wel1come1234/workspace/fds/Build/impi_intel_linux/fds_impi_intel_linux
```

> ⚠️ 본 서버에서는 makefile의 MKL 경로 자동 탐지에 버그가 있어 한 줄 패치가 필요했다 ([06_troubleshooting.md §6.4b](06_troubleshooting.md#64b-) 참조). 이미 적용되어 있다.

## 검증된 헬퍼 스크립트

| 파일 | 용도 |
|---|---|
| [scripts/fds_env.sh](scripts/fds_env.sh) | 환경 로드 (`source`해서 사용) — 기존 서버용 |
| [scripts/fds_env_kisti.sh](scripts/fds_env_kisti.sh) | 환경 로드 — **KISTI Neuron 전용** (모듈 + `I_MPI_ROOT`) |
| [scripts/run_fds.sbatch](scripts/run_fds.sbatch) | Slurm 잡 템플릿 (`sbatch run_fds.sbatch input.fds`) |

## 문서 목록

| # | 파일 | 내용 |
|---|---|---|
| 0 | [00_overview.md](00_overview.md) | 서버 환경, FDS 빌드 구조, 디렉터리 레이아웃 |
| 1 | [01_prerequisites.md](01_prerequisites.md) | 컴파일러/MPI/MKL/CMake 로드 |
| 2 | [02_third_party_libs.md](02_third_party_libs.md) | HYPRE / SUNDIALS 소스 준비 |
| 3 | [03_build_fds.md](03_build_fds.md) | FDS 빌드 절차 |
| 4 | [04_run_test.md](04_run_test.md) | 동작 검증 (smoke test, MPI 케이스) |
| 5 | [05_slurm_job.md](05_slurm_job.md) | Slurm 잡 스크립트 (`run_fds.sbatch`) |
| 6 | [06_troubleshooting.md](06_troubleshooting.md) | 자주 만나는 문제와 해결 |
| 7 | [07_mccaffrey_validation.md](07_mccaffrey_validation.md) | McCaffrey_Plume 20-case 검증 + 결과 자동 분류 |
| 8 | [08_kisti_neuron.md](08_kisti_neuron.md) | **KISTI Neuron 서버에서의 차이점 + 검증된 빌드 절차** (2026-05-13 검증) |

## 핵심 경로 한눈에 보기

```
FIREMODELS = /shared/home/wel1come1234/workspace
├── fds/                                                    # FDS 소스
│   └── Build/impi_intel_linux/fds_impi_intel_linux         # 실행파일 (빌드 후)
├── hypre/                                                  # HYPRE 소스 + 빌드
├── sundials/                                               # SUNDIALS 소스 + 빌드
└── libs/                                                   # 빌드된 라이브러리 (자동)
    ├── hypre/v3.0.0/{include,lib}
    └── sundials/v7.5.0/{include,lib}
```

## 참고

- FDS 공식 저장소: https://github.com/firemodels/fds
- HYPRE: https://github.com/hypre-space/hypre
- SUNDIALS: https://github.com/LLNL/sundials
- FDS 사용자/검증/검증 매뉴얼: `fds/Manuals/` 또는 https://pages.nist.gov/fds-smv/
