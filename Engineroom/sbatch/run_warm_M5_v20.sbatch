#!/bin/bash
#SBATCH --job-name=wM5_v20
#SBATCH --partition=batch
#SBATCH --nodelist=cpu05
#SBATCH --nodes=1
#SBATCH --ntasks=48
#SBATCH --ntasks-per-node=48
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/warm_M5_v20/warm_M5_v20.slurm.%j.log

# FDS engine-room fire (warm_M5_v20): 48 meshes, ventilation starts at 20 s.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm
export I_MPI_HYDRA_BOOTSTRAP=fork
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/warm_M5_v20
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/warm_M5_v20
echo "host=$(hostname)  ranks=48  vent_start=20s  start=$(date)"
stdbuf -oL -eL mpirun -np 48 /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/vent_timing/warm_M5_v20.fds
echo "done=$(date)"
