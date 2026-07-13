# 6. 트러블슈팅

## 6.1 `Your HYPRE repository is not up to date with the required tag: v3.0.0`

원인: HYPRE 저장소 clone이 불완전하거나 얕은(`--depth 1`) clone이라서 v3.0.0 태그를 못 찾음.

해결:
```bash
cd $FIREMODELS
rm -rf hypre        # NFS lock 파일 .nfs* 가 남아 있으면 잠시 후 재시도
git clone --branch master https://github.com/hypre-space/hypre.git hypre
mkdir -p hypre/build
cd hypre && git tag -l v3.0.0   # 결과: v3.0.0 가 출력되어야 함
```

SUNDIALS 같은 증상이면 동일하게 `--branch main`으로 재clone.

## 6.2 NFS `.nfs000...` 파일 때문에 `rm -rf` 실패

`/shared/...` 가 NFS이므로 다른 프로세스가 파일을 열고 있을 때 삭제하면 `.nfs*` 임시 파일이 남는다. 모든 관련 프로세스(빌드, 셸 백그라운드 잡)가 종료될 때까지 기다린 뒤 다시 `rm -rf` 실행.

```bash
lsof +D $FIREMODELS/hypre 2>/dev/null   # 누가 잡고 있는지 확인
sleep 30 && rm -rf $FIREMODELS/hypre
```

## 6.3 `mpiifort: command not found`

`setvars.sh`를 source하지 않은 상태. 다음을 매 셸 시작 시 또는 sbatch 헤더에 추가:
```bash
source /opt/intel/oneapi/setvars.sh
```

## 6.3b ⚠️ `cannot find -lmpifort` / `-lmpi` (KISTI Neuron 한정)

3rd-party 빌드(HYPRE/SUNDIALS) cmake 단계에서 C 컴파일러 테스트가 다음과 같이 실패:
```
/usr/bin/ld: cannot find -lmpifort
/usr/bin/ld: cannot find -lmpi
icx: error: linker command failed with exit code 1
```

원인: Neuron의 `mpi/impi-21.17` 모듈이 `I_MPI_ROOT`를 설정하지 않아 `mpiicx` 래퍼가 리터럴 문자열 `-L"I_MPI_SUBSTITUTE_INSTALLDIR/lib"`를 그대로 넘긴다.

해결:
```bash
export I_MPI_ROOT=/apps/compiler/intel/25.3.0/mpi/2021.17
```

자세한 설명·검증 방법: [08_kisti_neuron.md §8.4](08_kisti_neuron.md#84--핵심-패치--i_mpi_root-수동-export-필수).

## 6.4 `MKLROOT` 미설정 → MKL 링크 실패

`setvars.sh`가 이를 자동 설정한다. 만약 모듈을 개별 로드한다면 `module load mkl/2023.2.0` 필수.

## 6.4b ⚠️ `ifx: error #10236: File not found: '/opt/intel/oneapi/mkl/2023.2.0/lib/libmkl_*.a'` (이 서버에서 실제로 발생함)

> 🇰🇷 **KISTI Neuron에서는 이 패치를 적용하지 말 것.** Neuron의 MKL 2025.3은 `$MKLROOT/lib/intel64`가 `../lib/`로의 심볼릭링크라 fallback 경로가 그대로 유효하다. 자세한 내용은 [08_kisti_neuron.md §8.5](08_kisti_neuron.md#85-mkl-makefile-패치는-적용하지-말-것).


**증상**: HYPRE/SUNDIALS/FDS 컴파일은 모두 성공하는데, **마지막 링크 단계에서** MKL 정적 라이브러리를 못 찾는다.

**원인**: `fds/Build/makefile` 67–78줄의 `MKLLIBDIR` 자동 탐지 로직에 버그가 있다.

```makefile
MKL_BLA_PATH_A := "$(MKL_DIR_INTEL)/lib$(MKL_BLA_LIB).a"   # ← 큰따옴표가 변수 값에 포함됨
MKL_BLA_PATH_LIB := "$(MKL_DIR_INTEL)/$(MKL_BLA_LIB).lib"
ifneq (,$(wildcard $(MKL_BLA_PATH_A) $(MKL_BLA_PATH_LIB)))
    MKLLIBDIR := $(MKL_DIR_INTEL)        # = $MKLROOT/lib/intel64  (oneAPI 2023+)
else
    MKLLIBDIR := $(MKL_DIR_BASE)         # = $MKLROOT/lib          (구버전 MKL)
endif
```

`make`의 `wildcard` 함수는 인자에 들어 있는 큰따옴표를 글로브 패턴의 일부로 취급하므로 매칭이 항상 실패하고, 결과적으로 `MKLLIBDIR`이 항상 fallback 값(`$MKLROOT/lib`)으로 설정된다. **oneAPI 2023.2은 정적 라이브러리가 `$MKLROOT/lib/intel64/`에 있으므로 링크가 실패한다.**

**해결**: makefile 72–73줄의 큰따옴표 제거.

```diff
- MKL_BLA_PATH_A := "$(MKL_DIR_INTEL)/lib$(MKL_BLA_LIB).a"
- MKL_BLA_PATH_LIB := "$(MKL_DIR_INTEL)/$(MKL_BLA_LIB).lib"
+ MKL_BLA_PATH_A := $(MKL_DIR_INTEL)/lib$(MKL_BLA_LIB).a
+ MKL_BLA_PATH_LIB := $(MKL_DIR_INTEL)/$(MKL_BLA_LIB).lib
```

수정 후 `./make_fds.sh`를 다시 실행하면 빌드가 출력에 다음을 표시한다:
```
MKLLIBDIR = /opt/intel/oneapi/mkl/2023.2.0/lib/intel64
```

본 서버 인스턴스에는 이미 패치가 적용되어 있다.

> 대안: makefile을 건드리지 않고 `make MKLLIBDIR=$MKLROOT/lib/intel64 ...`로 명령행 override를 줘도 되지만, 그러면 `make_fds.sh`가 set_compilers.sh / build_thirdparty_libs.sh의 환경 export를 우회하므로 link line의 다른 변수까지 비게 되어 별도로 환경 세팅 후 `make` 직접 실행 필요. makefile 수정이 가장 깔끔하다.

## 6.5 OpenMP 라이브러리 (`libiomp5.so`) 못 찾음

런타임에 OpenMP 빌드를 실행할 때 발생. `setvars.sh` 또는 `module load compiler/2023.2.1`이 `LD_LIBRARY_PATH`에 oneAPI 컴파일러 lib를 포함시킨다. 런타임 환경에서도 같은 source가 필요.

## 6.6 Slurm 잡이 즉시 죽음 — `bash: source: setvars.sh: No such file or directory`

기본 sbatch는 로그인 셸 환경을 상속하지 않을 수 있다. sbatch 스크립트 안에서 직접 source.

## 6.7 MPI 통신 hang / `OFI`, `psm2` 에러

본 서버는 InfiniBand가 아닌 일반 네트워크일 수 있다. Intel MPI를 강제로 TCP로:
```bash
export I_MPI_FABRICS=shm:ofi
# 그래도 hang이면
export I_MPI_FABRICS=shm:tcp
```

## 6.8 빌드는 됐는데 실행 시 `Forrtl: severe (24): end-of-file during read`

인풋 인코딩(UTF-8 BOM 또는 Windows CRLF) 문제. `dos2unix input.fds` 한 번 실행.

## 6.9 `Verification/` 케이스 일부가 OOM/시간 초과

대형 케이스가 섞여 있다. `mesh ijk` / `t_end`를 확인해 작은 케이스부터 돌릴 것. `Verification/Pressure_Solver/dancing_eddies_default.fds`가 검증용으로 가볍다.

## 6.10 다시 처음부터 빌드하고 싶을 때

```bash
cd $FIREMODELS/fds/Build/impi_intel_linux
./make_fds.sh --clean-all
```

라이브러리(`libs/`)와 FDS 오브젝트가 모두 재빌드된다.
