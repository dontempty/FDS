#!/bin/bash
#SBATCH --job-name=p05f1
#SBATCH --partition=batch
#SBATCH --exclude=cpu04
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --time=36:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/peak05_fire1_M5/peak05_fire1_M5.slurm.%j.log

# FDS engine-room fire (peak05_fire1_M5): 32 meshes (4x4x2), vents on from t=0,
# HRR t^2 peak at 5 s, fire footprint 1.0x1.0 m (HRRPUA=863 kW/m2), T_END=360 s.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm
export I_MPI_HYDRA_BOOTSTRAP=fork
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/peak05_fire1_M5
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/peak05_fire1_M5
echo "host=$(hostname)  ranks=32  hrr_tpeak=5s  fire=1.0m  start=$(date)"
stdbuf -oL -eL mpirun -np 32 /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/peak05_fire1_M5.fds
echo "done=$(date)"
