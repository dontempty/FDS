# 3. FDS 빌드

## 3.1 한 줄 빌드 (모든 게 자동)

```bash
source /opt/intel/oneapi/setvars.sh
export FIREMODELS=/shared/home/wel1come1234/workspace

cd $FIREMODELS/fds/Build/impi_intel_linux
./make_fds.sh
```

스크립트가 다음을 순차 실행:
1. `set_compilers.sh` → `mpiifx`/`mpiifort` 자동 선택
2. `build_thirdparty_libs.sh` → HYPRE, SUNDIALS 빌드 (없으면)
3. `make -j4 -f ../makefile impi_intel_linux` → FDS 본체 컴파일

성공 시 산출물:
```
$FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux
```

## 3.2 빌드 옵션

`make_fds.sh`에 그대로 전달된다 (`build_thirdparty_libs.sh`의 옵션 참조):

```bash
./make_fds.sh --clean-fds          # FDS .o/.mod 만 삭제 후 재빌드
./make_fds.sh --clean-hypre        # HYPRE 재빌드 + FDS clean
./make_fds.sh --clean-sundials     # SUNDIALS 재빌드 + FDS clean
./make_fds.sh --clean-all          # 전체 재빌드
./make_fds.sh --no-libs            # HYPRE/SUNDIALS 없이 FDS 빌드 (기능 일부 비활성)
```

## 3.3 다른 타깃으로 빌드

| 타깃 디렉터리 | 비고 |
|---|---|
| `impi_intel_linux_db` | -O0 -g 디버그 (gdb/Intel Debugger) |
| `impi_intel_linux_dv` | -O1 저최적화, 개발 검증용 |
| `impi_intel_linux_openmp` | MPI + OpenMP 하이브리드 |
| `ompi_gnu_linux` | gfortran + OpenMPI fallback |

각 디렉터리에 들어가 동일하게 `./make_fds.sh` 실행.

## 3.4 빌드 결과 확인

```bash
ls -lh $FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux
$FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux 2>&1 | head -5
# → "Consult FDS Users Guide..." 같은 사용법 메시지 출력
```

`ldd`로 의존성 확인:
```bash
ldd $FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux | head -20
```

대부분 MKL은 정적 링크(.a)되어 있어 `libmkl_*` 항목은 보이지 않는다. `libmpi.so`, `libiomp5.so`(OpenMP 빌드시), `libsundials_*.so` 등이 보일 수 있다.

## 3.5 PATH 등록 (선택)

자주 쓰면 `~/.bashrc`에:
```bash
export PATH=$FIREMODELS/fds/Build/impi_intel_linux:$PATH
alias fds=fds_impi_intel_linux
```
