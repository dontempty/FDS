# 1. 사전 준비 — 컴파일러/툴체인 로드

## 1.1 Intel oneAPI 환경 로드

본 서버는 Intel oneAPI 2023.2가 설치되어 있고 `module` 시스템도 사용 가능하다. 두 방법 중 하나를 사용한다.

### 방법 A — `setvars.sh` (권장, 한 줄로 모든 컴포넌트 로드)

```bash
source /opt/intel/oneapi/setvars.sh
```

이 한 줄로 다음이 PATH/환경에 들어온다:
- Intel Fortran/C 컴파일러 (`ifx`, `ifort`, `icx`)
- Intel MPI (`mpiifort`, `mpiifx`, `mpiexec`)
- Intel MKL (`MKLROOT` 환경변수 설정)

확인:
```bash
which mpiifort && mpiifort --version
echo "MKLROOT=$MKLROOT"
```

### 방법 B — 모듈 개별 로드

```bash
module load compiler/2023.2.1   # ifx/ifort/icx
module load mpi/2021.10.0        # mpiifort, mpiexec
module load mkl/2023.2.0         # MKL
```

## 1.2 CMake / Git / Make

이미 시스템에 존재하므로 별도 설치 불필요:

```bash
which cmake   # /shared/home/wel1come1234/miniconda3/bin/cmake (3.21.3)
which git make
```

CMake 3.21.3 ≥ HYPRE/SUNDIALS 최소 요구사항.

## 1.3 `FIREMODELS` 환경변수

3rd-party 빌드 스크립트가 자동으로 `FIREMODELS=fds 부모 디렉터리`로 설정하지만, 명시적으로 export해 두면 안전하다.

```bash
export FIREMODELS=/shared/home/wel1come1234/workspace
```

## 1.4 셸 초기화 스크립트(권장)

매번 손으로 입력하지 않도록 `~/.bashrc` 끝 또는 별도 파일(예: `$HOME/fds_env.sh`)에 다음을 저장하고 필요할 때 `source`한다:

```bash
# ---- FDS build/run environment ----
export FIREMODELS=/shared/home/wel1come1234/workspace
source /opt/intel/oneapi/setvars.sh > /dev/null
# miniconda cmake 경로가 이미 PATH에 있는지만 확인
command -v cmake >/dev/null || export PATH=/shared/home/wel1come1234/miniconda3/bin:$PATH
```

> ⚠️ `setvars.sh`는 인자 없이 호출하면 **모든** oneAPI 컴포넌트를 로드하며, 두 번 source 시 "already initialized" 경고를 출력한다. 무해하지만 신경 쓰이면 `--force`를 붙인다.
