#!/bin/bash
#SBATCH --job-name=p20_M5
#SBATCH --partition=batch
#SBATCH --nodelist=cpu06
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --time=36:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/peak20_M5/peak20_M5.slurm.%j.log

# FDS engine-room fire (peak20_M5): 32 meshes (4x4x2), vents on from t=0,
# HRR t^2 growth peaking at 20 s, T_END=360 s.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm
export I_MPI_HYDRA_BOOTSTRAP=fork
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/peak20_M5
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/peak20_M5
echo "host=$(hostname)  ranks=32  hrr_tpeak=20s  vent_start=0s  start=$(date)"
stdbuf -oL -eL mpirun -np 32 /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/peak_time/peak20_M5.fds
echo "done=$(date)"
