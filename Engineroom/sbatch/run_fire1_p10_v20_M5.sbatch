#!/bin/bash
#SBATCH --job-name=f1p10v20
#SBATCH --partition=batch
#SBATCH --exclude=cpu04
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --time=36:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_M5/fire1_p10_v20_M5.slurm.%j.log

# FDS engine-room fire (fire1_p10_v20_M5): 32 meshes (4x4x2).
# 1 m fire (1.0x1.0 m, HRRPUA=863 kW/m2), HRR t^2 peak at 10 s,
# mechanical ventilation (Method 2) starts at 20 s. T_END=300 s.
# Reads canonical input from Inputs/scenario/, writes output into Results/fire1_p10_v20_M5/.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm
export I_MPI_HYDRA_BOOTSTRAP=fork
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_M5
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_M5
echo "host=$(hostname)  ranks=32  fire=1.0m  hrr_tpeak=10s  vent_start=20s  T_END=300  start=$(date)"
stdbuf -oL -eL mpirun -np 32 /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/scenario/fire1_p10_v20_M5.fds
echo "done=$(date)"
