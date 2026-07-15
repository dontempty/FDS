#!/bin/bash
#SBATCH --job-name=warm_M5
#SBATCH --partition=batch
#SBATCH --nodelist=cpu06
#SBATCH --nodes=1
#SBATCH --ntasks=48
#SBATCH --ntasks-per-node=48
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/warm_M5/warm_M5.slurm.%j.log

# FDS marine engine-room fire (warm_M5): 48 meshes (6x4x2) → 48 MPI ranks.
# Fire-only 0-60 s, mechanical ventilation (Method 2) on 60-360 s.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm                 # single node → shared-memory fabric
export I_MPI_HYDRA_BOOTSTRAP=fork        # single node → fork ranks locally

FDS=/shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/warm_M5
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/warm_M5

echo "host=$(hostname)  ranks=48  start=$(date)"
stdbuf -oL -eL mpirun -np 48 $FDS /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/vent_timing/warm_M5.fds
echo "done=$(date)"
