# FDS 환경 구축 가이드 (개요)

본 문서는 `/shared/home/wel1come1234/workspace/fds`에 있는 FDS (Fire Dynamics Simulator) 소스를 이 서버(login01, Ubuntu 20.04 + Slurm)에서 빌드/실행하기 위한 절차를 정리한 것이다.

## 서버 환경 요약

| 항목 | 값 |
|---|---|
| OS | Ubuntu 20.04.6 LTS |
| 호스트 | login01 (계산 노드: cpu01-06, gpu01-02) |
| 스케줄러 | Slurm (파티션: `batch`, 무제한 timelimit, 8 노드 idle) |
| Intel oneAPI | 2023.2 (`/opt/intel/oneapi/setvars.sh`) — icx, ifx/ifort, mpiifort, MKL, IMPI 모두 포함 |
| GNU 컴파일러 | gfortran (system), `mpifort` (OpenMPI) — fallback 빌드용 |
| CMake | 3.21.3 (miniconda) |
| 기타 | git, make 사용 가능, 인터넷 접속 가능 |

## FDS 빌드 구조 핵심

`fds/Build/<target>/make_fds.sh` 스크립트가:

1. `set_compilers.sh`로 타깃에 맞는 C/C++/Fortran 컴파일러 자동 선택
2. `build_thirdparty_libs.sh`가 **HYPRE v3.0.0**, **SUNDIALS v7.5.0**를 차례로 빌드 (필요시)
3. `make -j4 ... -f ../makefile <target>`로 FDS 본체 빌드

**중요**: 3rd-party 빌드 스크립트는 환경변수 `FIREMODELS` 경로를 기준으로 동작하며, **본 서버에서는 모든 의존 라이브러리를 `fds/deps/` 한 폴더 안에 통합**해 놓았다.

```
/shared/home/wel1come1234/workspace/fds/      ← FDS 루트
├── Source/, Build/, Validation/, ...         FDS 본체
├── deps/                                     ← 모든 외부 라이브러리 (통합됨)
│   ├── fds -> ..                             심볼릭링크: $FIREMODELS/fds/... 경로 해석용
│   ├── hypre/                                HYPRE 소스 저장소 (master + v3.0.0 태그)
│   │   ├── src/
│   │   └── build/                            빌드 디렉터리
│   ├── sundials/                             SUNDIALS 소스 저장소 (main + v7.5.0 태그)
│   └── libs/                                 빌드된 라이브러리 설치 위치
│       ├── hypre/v3.0.0/{include,lib}
│       └── sundials/v7.5.0/{include,lib}
└── setup_docs/                               본 문서
```

따라서 **`FIREMODELS=/shared/home/wel1come1234/workspace/fds/deps`** 로 설정한다 (`fds_env.sh`가 자동으로 처리). 빌드 스크립트가 참조하는 `$FIREMODELS/fds/Build/Scripts/...` 는 `deps/fds -> ..` 심볼릭링크를 통해 FDS 루트의 스크립트로 해석된다.

> ℹ️ 라이브러리는 모두 정적(.a) 링크이므로, FDS 바이너리는 `libs/` 위치를 바꿔도 그대로 동작한다 (재빌드 불필요).

스크립트가 `cd $FIREMODELS/hypre`, `git checkout v3.0.0` 등 git 명령을 직접 실행하므로 hypre/sundials 저장소는 **반드시 정식 clone (얕은 clone X)** 이어야 한다.

## 권장 빌드 타깃

| 타깃 | 컴파일러 | 추천 사유 |
|---|---|---|
| **`impi_intel_linux`** ✅ | Intel + Intel MPI + MKL (sequential) | 본 서버 기본 권장. Intel oneAPI 2023.2가 설치되어 있어 가장 안정적. -O2 -ipo 최적화. |
| `impi_intel_linux_openmp` | Intel + IMPI + MKL (intel_thread) | 하이브리드 MPI/OpenMP 필요시. Intel 컴파일러는 OpenMP 빌드 시 ~20% 오버헤드. |
| `ompi_gnu_linux` | GNU + OpenMPI + MKL (gnu_thread) | Intel 라이선스 문제 시 fallback. gfortran 빌드는 항상 OpenMP 포함. |
| `*_db`, `*_dv` | 디버그/저최적화 | 디버깅 시 사용. |

본 가이드는 **`impi_intel_linux` 기준**이다.

## 문서 순서

| 파일 | 내용 |
|---|---|
| [01_prerequisites.md](01_prerequisites.md) | 필수 모듈/패키지, 환경변수 |
| [02_third_party_libs.md](02_third_party_libs.md) | HYPRE / SUNDIALS 소스 준비 |
| [03_build_fds.md](03_build_fds.md) | FDS 빌드 절차 |
| [04_run_test.md](04_run_test.md) | 단일 노드 동작 검증 |
| [05_slurm_job.md](05_slurm_job.md) | Slurm 잡 스크립트 템플릿 |
| [06_troubleshooting.md](06_troubleshooting.md) | 자주 만나는 문제와 해결 |
