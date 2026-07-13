# 2. 3rd-party 라이브러리 (HYPRE, SUNDIALS) 준비

FDS는 **HYPRE v3.0.0**(Pressure Solver의 PFMG/AMG 옵션)과 **SUNDIALS v7.5.0**(Stiff chemistry CVODE 등)을 사용한다. `make_fds.sh`가 자동 빌드해 주지만, 그러기 위해서는 두 저장소가 `$FIREMODELS` 아래에 미리 clone되어 있어야 한다.

## 2.1 디렉터리 구조 (통합 레이아웃)

본 서버에서는 모든 의존 라이브러리를 **`fds/deps/`** 한 폴더에 통합했다:

```bash
$ export FIREMODELS=/shared/home/wel1come1234/workspace/fds/deps
$ ls $FIREMODELS
fds  hypre  libs  sundials      # 'fds'는 ../ 로의 심볼릭링크
```

`fds/deps/fds -> ..` 심볼릭링크가 있어서 빌드 스크립트의 `$FIREMODELS/fds/Build/Scripts/...` 경로가 정상적으로 해석된다.

> 📌 **새 머신에서 처음 셋업하는 경우**: 위와 같이 `fds/deps/` 안에 hypre/sundials를 clone하고 `ln -s .. fds/deps/fds` 심볼릭링크를 만든 뒤 `FIREMODELS=fds/deps`로 export하면 된다.

## 2.2 HYPRE clone

```bash
mkdir -p $FIREMODELS                                # = /shared/.../fds/deps
cd $FIREMODELS
git clone --branch master https://github.com/hypre-space/hypre.git hypre
mkdir -p hypre/build           # 빌드 스크립트가 사용
[ -L fds ] || ln -s .. fds      # FIREMODELS/fds → FDS 루트 (한 번만)
```

> ⚠️ `--depth 1` 같은 얕은 clone은 사용하지 말 것. `build_hypre.sh`가 `git checkout master` → `git checkout v3.0.0` (detached HEAD) 후 다시 `git checkout master`로 돌아가는 동작을 하므로 master 브랜치 추적과 v3.0.0 태그가 모두 필요하다.

태그 확인:
```bash
cd $FIREMODELS/hypre && git tag -l v3.0.0   # → v3.0.0 출력되어야 함
```

## 2.3 SUNDIALS clone

```bash
cd $FIREMODELS
git clone --branch main https://github.com/LLNL/sundials.git sundials
```

빌드 디렉터리는 `build_sundials.sh`가 `BUILDDIR`라는 이름으로 자동 생성한다.

태그 확인:
```bash
cd $FIREMODELS/sundials && git tag -l v7.5.0   # → v7.5.0
```

## 2.4 자동 빌드 (FDS 빌드와 동시)

`make_fds.sh`를 실행하면 다음을 자동으로 수행한다:

1. `$FIREMODELS/libs/hypre/v3.0.0`가 이미 있으면 → skip
2. 없으면 → `hypre` 저장소를 v3.0.0으로 checkout → `build/`에서 cmake → `libs/hypre/v3.0.0/`에 install
3. SUNDIALS도 동일 (`libs/sundials/v7.5.0/`)

## 2.5 수동/단독 빌드 (선택)

3rd-party만 따로 빌드하고 싶다면:

```bash
cd $FIREMODELS/fds/Build/impi_intel_linux
source ../Scripts/build_thirdparty_libs.sh
```

빌드 옵션:
- `--clean-hypre`     HYPRE 재빌드
- `--clean-sundials`  SUNDIALS 재빌드
- `--clean-all`       전체 재빌드
- `--no-libs`         3rd-party 빌드 건너뛰기 (HYPRE/SUNDIALS 미사용)

## 2.6 빌드 산출물 위치

| 라이브러리 | 설치 경로 |
|---|---|
| HYPRE | `$FIREMODELS/libs/hypre/v3.0.0/{include,lib}` |
| SUNDIALS | `$FIREMODELS/libs/sundials/v7.5.0/{include,lib,examples}` |

이 경로는 makefile이 `HYPRE_HOME`, `SUNDIALS_HOME` 환경변수를 통해 자동 인식한다.
