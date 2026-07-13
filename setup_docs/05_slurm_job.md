# 5. Slurm 잡 실행

본 서버는 단일 파티션 `batch` (cpu01-06, gpu01-02, 무제한 timelimit)만 사용한다.

## 5.1 기본 잡 스크립트 (단일 노드 멀티 랭크)

`run_fds.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=fds
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8        # MPI 랭크 수 = MESH 개수
#SBATCH --cpus-per-task=1          # OpenMP 안 쓰면 1
#SBATCH --time=24:00:00            # 무제한이지만 보호 차원에서 명시
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err

set -e

# --- 환경 ---
source /opt/intel/oneapi/setvars.sh > /dev/null
export FIREMODELS=/shared/home/wel1come1234/workspace
FDS=$FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux

# --- 실행 ---
INPUT=${1:-input.fds}
echo "Host:   $(hostname)"
echo "Date:   $(date)"
echo "Ranks:  $SLURM_NTASKS"
echo "Input:  $INPUT"
echo

cd $SLURM_SUBMIT_DIR

# Intel MPI 권장 옵션 (본 서버 파일시스템이 NFS이므로 fabric=tcp가 안전)
export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1

mpiexec -n $SLURM_NTASKS $FDS $INPUT
```

제출:
```bash
sbatch run_fds.sbatch my_case.fds
squeue -u $USER
```

## 5.2 멀티 노드

```bash
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=8        # 총 16 랭크
```

> ⚠️ 노드를 늘릴 때는 인풋의 `MPI_PROCESS=` 인덱스 합이 `--ntasks` 총합과 일치해야 한다. 한 MESH당 한 랭크가 기본.

## 5.3 하이브리드 MPI + OpenMP

OpenMP 빌드(`impi_intel_linux_openmp`)를 사용한 경우:

```bash
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=4

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export I_MPI_PIN_DOMAIN=omp
mpiexec -n $SLURM_NTASKS $FDS $INPUT
```

## 5.4 인터랙티브 디버그

`salloc`로 노드 잡고 직접 실행:
```bash
salloc -p batch -N 1 -n 4 --time=01:00:00
# 노드 할당되면
source /opt/intel/oneapi/setvars.sh
export FIREMODELS=/shared/home/wel1come1234/workspace
mpiexec -n 4 $FIREMODELS/fds/Build/impi_intel_linux/fds_impi_intel_linux input.fds
exit
```

## 5.5 자주 쓰는 Slurm 명령

```bash
squeue -u $USER             # 내 잡
scontrol show job <jobid>   # 잡 상세
sacct -j <jobid>            # 종료된 잡 회계
scancel <jobid>             # 취소
sinfo                       # 노드/파티션 상태
```
