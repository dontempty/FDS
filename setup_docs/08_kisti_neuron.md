# 8. KISTI Neuron 빌드 가이드 (이 서버에서의 차이점)

본 문서는 `/scratch/x3319a05/fds`의 FDS를 **KISTI Neuron** (login: `glogin0X`, RHEL 9.4, Slurm + Environment Modules) 에서 빌드/실행하기 위한 절차이다. `00`–`07` 문서는 다른 클러스터(Ubuntu 20.04, oneAPI `setvars.sh` 방식) 기준이며, **Neuron에서는 아래 3가지가 다르다.**

## 8.1 한눈에 보는 차이점

| 항목 | setup_docs 기존 가이드 | KISTI Neuron |
|---|---|---|
| 툴체인 로드 | `source /opt/intel/oneapi/setvars.sh` | `module load …` (네 개) |
| `I_MPI_ROOT` | `setvars.sh`가 자동 설정 | **모듈이 설정하지 않음 → 직접 export 필요** ⚠️ |
| MKL 라이브러리 경로 | `$MKLROOT/lib/intel64` 실제 디렉터리 | `$MKLROOT/lib/intel64`는 `../lib/`로의 심볼릭링크 |
| MKL makefile 패치 (§6.4b) | **필요** | **불필요** (fallback 경로가 그대로 유효) |
| FIREMODELS 경로 | `/shared/home/wel1come1234/workspace/fds/deps` | `/scratch/x3319a05/fds/deps` |
| 환경 헬퍼 스크립트 | [`scripts/fds_env.sh`](scripts/fds_env.sh) | [`scripts/fds_env_kisti.sh`](scripts/fds_env_kisti.sh) |

## 8.2 빠른 시작

```bash
# 1. 환경 로드 (모듈 + I_MPI_ROOT + FIREMODELS 한 번에)
source /scratch/x3319a05/fds/setup_docs/scripts/fds_env_kisti.sh

# 2. 3rd-party 소스 준비 (한 번만)
mkdir -p $FIREMODELS && cd $FIREMODELS
[ -L fds ] || ln -s .. fds
git clone --branch master https://github.com/hypre-space/hypre.git hypre
mkdir -p hypre/build
git clone --branch main   https://github.com/LLNL/sundials.git sundials

# 3. 빌드 (HYPRE/SUNDIALS도 자동 빌드, 링크 단계까지 ~3분)
cd $FDS_ROOT/Build/impi_intel_linux && ./make_fds.sh

# 4. 동작 확인
$FDS_BIN 2>&1 | head -5     # "Fire Dynamics Simulator …" 배너
```

검증된 산출물 (2026-05-13):
```
/scratch/x3319a05/fds/Build/impi_intel_linux/fds_impi_intel_linux   (~113 MB)
Compiler: Intel(R) Fortran Compiler 2025.3.0 Build 20251010
```

## 8.3 모듈 셋업

```bash
module purge
module load intel/25.3.0  mpi/impi-21.17  mkl/2025.3  cmake/4.2.1
```

확인:
```bash
$ which mpiifx mpiicx ifx icx cmake
/apps/compiler/intel/25.3.0/mpi/2021.17/bin/mpiifx
/apps/compiler/intel/25.3.0/mpi/2021.17/bin/mpiicx
/apps/compiler/intel/25.3.0/compiler/2025.3/bin/ifx
/apps/compiler/intel/25.3.0/compiler/2025.3/bin/icx
/apps/applications/cmake/4.2.1/bin/cmake

$ echo $MKLROOT
/apps/libraries/mkl/2025.3
```

> ⚠️ Intel oneAPI 2025부터 `ifort`가 제거되었으므로 `ifx` (LLVM 기반)만 존재한다. FDS의 `set_compilers.sh`가 `mpiifx → mpiifort` 순으로 검색하므로 자동 선택된다.

## 8.4 ⚠️ 핵심 패치 — `I_MPI_ROOT` 수동 export (필수)

### 증상
3rd-party 빌드 단계에서 cmake가 C 컴파일러 테스트에 실패하고 build가 중단된다.

```
CMake Error at .../CMakeTestCCompiler.cmake:67 (message):
    /usr/bin/ld: cannot find -lmpifort
    /usr/bin/ld: cannot find -lmpi
    icx: error: linker command failed with exit code 1
```

### 원인
Neuron의 `mpi/impi-21.17` 모듈은 PATH, LD_LIBRARY_PATH는 설정하지만 **`I_MPI_ROOT` 환경변수를 export하지 않는다.** Intel MPI의 `mpiicx`/`mpiicc`/`mpiifx` 컴파일러 래퍼는 내부적으로 `I_MPI_ROOT` 값을 그대로 `-L`/`-rpath` 인자에 치환해 넣는데, 변수가 비어 있으면 다음과 같이 **리터럴 문자열을 그대로** 링커에 넘긴다:

```bash
$ mpiicx -show /tmp/x.c
icx '/tmp/x.c' -I"I_MPI_SUBSTITUTE_INSTALLDIR/include" \
    -L"I_MPI_SUBSTITUTE_INSTALLDIR/lib/release" \
    -L"I_MPI_SUBSTITUTE_INSTALLDIR/lib" ... -lmpifort -lmpi ...
```

`I_MPI_SUBSTITUTE_INSTALLDIR`라는 디렉터리는 존재하지 않으므로 `-lmpifort`, `-lmpi`를 찾지 못한다.

### 해결
모듈 로드 직후 다음 한 줄을 export 한다 ([scripts/fds_env_kisti.sh](scripts/fds_env_kisti.sh)에 포함되어 있음):

```bash
export I_MPI_ROOT=/apps/compiler/intel/25.3.0/mpi/2021.17
```

검증:
```bash
$ mpiicx -show /tmp/x.c | head -1
icx '/tmp/x.c' -I"/apps/compiler/intel/25.3.0/mpi/2021.17/include" -L"...lib/release" ...
$ echo 'int main(){}' > /tmp/x.c && mpiicx /tmp/x.c -o /tmp/x && echo OK
OK
```

> 📌 sbatch 잡 안에서도 동일하게 `I_MPI_ROOT`가 비어 있을 수 있으므로, sbatch 스크립트에서도 반드시 `source fds_env_kisti.sh` 또는 명시적 export.

## 8.5 MKL makefile 패치는 적용하지 말 것

`setup_docs/06_troubleshooting.md §6.4b`는 makefile 72–73줄의 큰따옴표를 제거하는 패치를 권장한다. **Neuron에서는 이 패치를 적용하지 않는다.**

- 원본 makefile은 `wildcard` 버그 때문에 항상 fallback 경로(`$MKLROOT/lib`)를 사용한다.
- Neuron의 MKL 2025.3 레이아웃에서는 `$MKLROOT/lib/intel64`가 `../lib/`로의 **심볼릭링크**이고 정적 라이브러리는 `$MKLROOT/lib/` 직하에 있다. 따라서 fallback 경로가 그대로 유효하다.

빌드 로그에서 다음을 확인할 수 있다:
```
MKLLIBDIR = /apps/libraries/mkl/2025.3/lib
```

패치를 적용하면 `MKLLIBDIR = $MKLROOT/lib/intel64`가 되는데, 이는 심볼릭링크를 통해 같은 디렉터리를 가리키므로 결과는 동일하다. 다만 *불필요*하므로 upstream makefile을 그대로 두는 편이 좋다.

## 8.6 디렉터리 레이아웃

```
/scratch/x3319a05/fds/                              ← FDS 루트 (FDS_ROOT)
├── Source/, Build/, Validation/, ...               FDS 본체
├── deps/                                           ← FIREMODELS
│   ├── fds -> ..                                   심볼릭링크 (필수)
│   ├── hypre/   ├── src/  └── build/
│   ├── sundials/
│   ├── libs/    ├── hypre/v3.0.0/{include,lib}
│   │            └── sundials/v7.5.0/{include,lib}
│   ├── build.log                                   make_fds.sh 전체 로그
│   └── fds_env_kisti.sh                            (= scripts/fds_env_kisti.sh)
└── setup_docs/                                     본 문서
```

## 8.7 Slurm 잡 (TODO — 파티션 확정 후 추가)

`scripts/run_fds.sbatch`는 다른 클러스터의 `batch` 파티션 기준이다. Neuron의 CPU 파티션 (예: `skl`, `cas_v100_4` 등) 중 무엇을 쓸지 결정한 뒤 다음을 수정해서 새로 만든다:

```bash
#SBATCH --partition=<neuron CPU 파티션>
#SBATCH --comment=<프로젝트 코멘트>            # Neuron 정책상 필요
source /scratch/x3319a05/fds/setup_docs/scripts/fds_env_kisti.sh
mpiexec -n "$SLURM_NTASKS" "$FDS_BIN" "$INPUT"
```

> Neuron의 GPU 파티션 (`amd_a100nv_8` 등)은 FDS에는 의미 없다 (FDS는 CPU MPI 전용). CPU 파티션 우선.

## 8.8 트러블슈팅 (Neuron 한정)

기존 `06_troubleshooting.md`의 항목들이 대부분 그대로 적용된다. Neuron에서 새로 본 문제는 §8.4의 `I_MPI_ROOT` 하나뿐. 그 외:

- **`module: command not found`** — 비대화 쉘에서 `module` 함수가 정의되지 않은 경우. sbatch 헤더 뒤에 `source /etc/profile.d/modules.sh` 한 줄을 먼저 넣는다. (대부분의 KISTI 쉘에는 이미 들어 있다.)
- **`ifort: command not found`** — Intel oneAPI 2025부터 classic `ifort`가 제거됐다. `ifx`로 대체된다 (FDS 빌드 스크립트는 이미 호환됨).
