#!/bin/bash
#SBATCH -J EV_EV_dx100
#SBATCH -p cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=20:00:00
#SBATCH --comment=etc
#SBATCH -o /scratch/x3319a05/FDS/electric_vehicle_battery/results/EV_dx100/slurm-%j.out
#SBATCH -e /scratch/x3319a05/FDS/electric_vehicle_battery/results/EV_dx100/slurm-%j.err

# 로그인 환경은 상속되지 않으므로 반드시 다시 source 한다.
source /scratch/x3319a05/FDS/setup_docs/scripts/fds_env_kisti.sh

export OMP_NUM_THREADS=1
export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1

RUNDIR=/scratch/x3319a05/FDS/electric_vehicle_battery/results/EV_dx100
mkdir -p "$RUNDIR"
cp /scratch/x3319a05/FDS/electric_vehicle_battery/input/cases/EV_dx100/EV_dx100.fds "$RUNDIR"/
cd "$RUNDIR"

echo "host      : $(hostname)"
echo "ranks     : $SLURM_NTASKS  (MESH (2, 1, 2) = 4)"
echo "cells     : 300000"
echo "start     : $(date)"

mpiexec -n "$SLURM_NTASKS" "$FDS_BIN" EV_dx100.fds

echo "end       : $(date)"
tail -n 5 EV_dx100.out
