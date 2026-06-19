#!/bin/bash
#SBATCH --job-name=fire_M5
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=48
#SBATCH --cpus-per-task=1
#SBATCH --mem=128G
#SBATCH --time=04:00:00
#SBATCH --comment=etc
#SBATCH --output=/scratch/x3319a05/fds/Engine_Room/logs/%x.%j.out
#SBATCH --error=/scratch/x3319a05/fds/Engine_Room/logs/%x.%j.err
set -euo pipefail
source /scratch/x3319a05/fds/setup_docs/scripts/fds_env_kisti.sh
export OMP_NUM_THREADS=1
cd /scratch/x3319a05/fds/Engine_Room/Results/coldflow_M5
mpiexec -n 48 "$FDS_BIN" /scratch/x3319a05/fds/Engine_Room/inputs/fire_M5.fds
