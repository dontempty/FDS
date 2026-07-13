# 4. 동작 검증 (단일 노드 / 인터랙티브)

## 4.1 빌드 결과 점검

```bash
source /opt/intel/oneapi/setvars.sh
export FIREMODELS=/shared/home/wel1come1234/workspace
FDS=$FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux

ls -lh $FDS
$FDS 2>&1 | head -3
# 정상 출력 예: "Consult FDS Users Guide Chapter, Running FDS, for further instructions."
```

## 4.2 간단한 인풋 — 5×5×5 셀, 1 mesh

```bash
mkdir -p $HOME/fds_smoke && cd $HOME/fds_smoke
cat > smoke_test.fds <<'EOF'
&HEAD CHID='smoke_test', TITLE='single-mesh smoke test' /
&MESH IJK=10,10,10, XB=0.0,1.0, 0.0,1.0, 0.0,1.0 /
&TIME T_END=1.0 /
&MISC TMPA=20. /
&SURF ID='HOT', TMP_FRONT=200., COLOR='RED' /
&VENT XB=0.4,0.6, 0.4,0.6, 0.0,0.0, SURF_ID='HOT' /
&VENT MB='ZMAX', SURF_ID='OPEN' /
&SLCF PBY=0.5, QUANTITY='TEMPERATURE' /
&TAIL /
EOF

mpiexec -n 1 $FDS smoke_test.fds 2>&1 | tail -20
```

성공 시:
- `smoke_test.out` 마지막에 `STOP: FDS completed successfully` 류 메시지
- `smoke_test_devc.csv`, `smoke_test_*.sf`, `smoke_test.smv` 등 생성
- `*.sf`/`*.smv`는 Smokeview에서 시각화 가능

## 4.3 멀티 mesh (멀티 MPI 랭크) 검증

```bash
cat > smoke_mpi.fds <<'EOF'
&HEAD CHID='smoke_mpi', TITLE='4-mesh MPI test' /
&MESH IJK=10,10,10, XB=0.0,0.5, 0.0,0.5, 0.0,1.0, MPI_PROCESS=0 /
&MESH IJK=10,10,10, XB=0.5,1.0, 0.0,0.5, 0.0,1.0, MPI_PROCESS=1 /
&MESH IJK=10,10,10, XB=0.0,0.5, 0.5,1.0, 0.0,1.0, MPI_PROCESS=2 /
&MESH IJK=10,10,10, XB=0.5,1.0, 0.5,1.0, 0.0,1.0, MPI_PROCESS=3 /
&TIME T_END=1.0 /
&SURF ID='HOT', TMP_FRONT=200. /
&VENT XB=0.4,0.6, 0.4,0.6, 0.0,0.0, SURF_ID='HOT' /
&VENT MB='ZMAX', SURF_ID='OPEN' /
&TAIL /
EOF

mpiexec -n 4 $FDS smoke_mpi.fds 2>&1 | tail -10
```

`-n` 값과 `MPI_PROCESS` 인덱스 개수가 일치해야 한다.

## 4.4 Verification / Validation 케이스

FDS 본체에 풍부한 검증 인풋이 함께 들어 있다:

| 디렉터리 | 내용 |
|---|---|
| `fds/Verification/` | 단위 검증 케이스(수십 개 카테고리) |
| `fds/Validation/` | 실제 실험과 비교하는 대형 케이스 |

가벼운 예시 실행:
```bash
cd $FIREMODELS/fds/Verification/Pressure_Solver
mpiexec -n 1 $FDS dancing_eddies_default.fds
```

> ℹ️ `Verification/`/`Validation/` 의 인풋은 대부분 `MPI_PROCESS` 값을 명시적으로 갖고 있어 정확한 랭크 수가 필요하다. 인풋의 `&MESH ... MPI_PROCESS=N` 줄을 grep하면 필요한 랭크 수를 확인할 수 있다.
