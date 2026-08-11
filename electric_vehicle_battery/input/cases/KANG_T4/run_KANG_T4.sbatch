#!/bin/bash
#SBATCH -J KANG_T4
#SBATCH -p cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --comment=etc
#SBATCH -o /scratch/x3319a05/FDS/electric_vehicle_battery/results/KANG_T4/slurm-%j.out
#SBATCH -e /scratch/x3319a05/FDS/electric_vehicle_battery/results/KANG_T4/slurm-%j.err

source /scratch/x3319a05/FDS/setup_docs/scripts/fds_env_kisti.sh
export OMP_NUM_THREADS=1 I_MPI_FABRICS=shm:ofi I_MPI_PIN=1
RUNDIR=/scratch/x3319a05/FDS/electric_vehicle_battery/results/KANG_T4
mkdir -p "$RUNDIR"
cp /scratch/x3319a05/FDS/electric_vehicle_battery/input/cases/KANG_T4/KANG_T4.fds "$RUNDIR"/
cd "$RUNDIR"
echo "host $(hostname)  ranks $SLURM_NTASKS  cells 245760  start $(date)"
mpiexec -n "$SLURM_NTASKS" "$FDS_BIN" KANG_T4.fds
echo "end $(date)"; tail -n 5 KANG_T4.out
