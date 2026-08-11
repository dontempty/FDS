#!/bin/bash
# FDS build/run environment for KISTI Neuron (glogin0X).
# Usage: source /scratch/x3319a05/FDS/setup_docs/scripts/fds_env_kisti.sh

export FDS_ROOT=/scratch/x3319a05/FDS
export FIREMODELS=$FDS_ROOT/deps
export FDS_BIN=$FDS_ROOT/Build/impi_intel_linux/fds_impi_intel_linux

module purge
module load intel/25.3.0 mpi/impi-21.17 mkl/2025.3 cmake/4.2.1

# Neuron's mpi/impi-21.17 module does NOT set I_MPI_ROOT, but the mpiicx/mpiicc
# compiler wrappers need it — otherwise -L/-rpath emit literal
# "I_MPI_SUBSTITUTE_INSTALLDIR/..." and the linker fails with -lmpi / -lmpifort
# not found. Set it explicitly.
export I_MPI_ROOT=/apps/compiler/intel/25.3.0/mpi/2021.17

# Runtime fix: the mpi/impi-21.17 module also does NOT add Intel MPI's bundled
# libfabric (libfabric.so.1 and provider .so's at $I_MPI_ROOT/opt/mpi/libfabric)
# to LD_LIBRARY_PATH.  Without this, mpiexec'd programs die on MPI_Init_thread
# with "MPIDI_OFI_mpi_init_hook: Other MPI error" because libfabric.so.1 cannot
# be dlopen()ed.  Source IMPI's own vars.sh (silent) which fixes all of this
# plus FI_PROVIDER_PATH, I_MPI_*, etc.
[ -f "$I_MPI_ROOT/env/vars.sh" ] && . "$I_MPI_ROOT/env/vars.sh" >/dev/null 2>&1
