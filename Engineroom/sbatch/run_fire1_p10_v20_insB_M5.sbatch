#!/bin/bash
#SBATCH --job-name=f1insB
#SBATCH --partition=batch
#SBATCH --exclude=cpu04,gpu01,gpu02
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --time=36:00:00
#SBATCH --output=/shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_insB_M5/fire1_p10_v20_insB_M5.slurm.%j.log

# FDS engine-room (fire1_p10_v20_insB_M5): fire 1.0m, HRR peak 10 s, vent 20 s, T_END 300 s.
# CEILING = steel BACKING='INSULATED' (back face adiabatic). + engine-Tz DEVCs.
set -e
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1
export I_MPI_FABRICS=shm
export I_MPI_HYDRA_BOOTSTRAP=fork
mkdir -p /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_insB_M5
cd /shared/home/wel1come1234/workspace/FDS/Engineroom/Results/fire1_p10_v20_insB_M5
echo "host=$(hostname) ranks=32 fire=1.0m peak=10s vent=20s CEILING=INSULATED start=$(date)"
stdbuf -oL -eL mpirun -np 32 /shared/home/wel1come1234/workspace/FDS/Build/impi_intel_linux/fds_impi_intel_linux /shared/home/wel1come1234/workspace/FDS/Engineroom/Inputs/scenario/fire1_p10_v20_insB_M5.fds
echo "done=$(date)"
