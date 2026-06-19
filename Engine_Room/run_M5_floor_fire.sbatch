#!/bin/bash
#SBATCH --job-name=M5_floor_fire
#SBATCH --partition=cpu
#SBATCH --nodelist=cpu05
#SBATCH --nodes=1
#SBATCH --ntasks=24
#SBATCH --cpus-per-task=1
#SBATCH --mem=192G
#SBATCH --time=08:00:00
#SBATCH --comment=etc
#SBATCH --output=/scratch/x3319a05/fds/Engine_Room/logs/%x.%j.out
#SBATCH --error=/scratch/x3319a05/fds/Engine_Room/logs/%x.%j.err
set -euo pipefail

source /scratch/x3319a05/fds/setup_docs/scripts/fds_env_kisti.sh
export OMP_NUM_THREADS=1

CASES=(
  M5_1p0_0p89
  M5_1p0_1p0
  M5_1p25_0p89
  M5_1p25_1p0
  M5_1p5_0p89
  M5_1p5_1p0
)

ROOT=/scratch/x3319a05/fds/Engine_Room

for CASE in "${CASES[@]}"; do
  echo "============================================================"
  echo "Starting $CASE at $(date)"
  echo "============================================================"
  mkdir -p "$ROOT/Results/$CASE"
  cd "$ROOT/Results/$CASE"
  mpiexec -n 24 "$FDS_BIN" "$ROOT/inputs/$CASE.fds"
  echo "Finished $CASE at $(date)"
done
