#!/bin/bash
#SBATCH --job-name=fds
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err

set -e
source /shared/home/wel1come1234/workspace/fds/setup_docs/scripts/fds_env.sh

INPUT=${1:-input.fds}
echo "Host:   $(hostname)"
echo "Date:   $(date)"
echo "Ranks:  $SLURM_NTASKS"
echo "Input:  $INPUT"
echo

cd "$SLURM_SUBMIT_DIR"

export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1

mpiexec -n "$SLURM_NTASKS" "$FDS_BIN" "$INPUT"
