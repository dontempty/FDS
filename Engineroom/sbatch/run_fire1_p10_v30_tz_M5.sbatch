#!/bin/bash
#SBATCH --job-name=f1v30tz
#SBATCH --partition=batch
#SBATCH --exclude=cpu04,gpu01,gpu02
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --time=36:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v30_tz_M5/fire1_p10_v30_tz_M5.slurm.%j.log

# FDS engine-room fire (fire1_p10_v30_tz_M5): 32 meshes (4x4x2).
# 1 m fire, HRR t^2 peak 10 s, vent start 30 s, T_END=300 s.
# + engine-footprint x,y-averaged T(z) DEVC slabs (VOLUME MEAN, 13 z-cells).
# Reads Inputs/scenario/, writes output into Results/fire1_p10_v30_tz_M5/.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm
export I_MPI_HYDRA_BOOTSTRAP=fork
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v30_tz_M5
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v30_tz_M5
echo "host=$(hostname)  ranks=32  fire=1.0m  peak=10s  vent=30s  T_END=300  engine_tz  start=$(date)"
stdbuf -oL -eL mpirun -np 32 /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/scenario/fire1_p10_v30_tz_M5.fds
echo "done=$(date)"
