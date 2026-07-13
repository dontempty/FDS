#!/bin/bash
# FDS build/run environment.
# Source this in your shell or sbatch script:
#   source /shared/home/wel1come1234/workspace/fds/setup_docs/scripts/fds_env.sh
#
# All FDS-related files are now consolidated under /shared/home/wel1come1234/workspace/fds:
#   fds/Source, fds/Build      — FDS source + build trees
#   fds/deps/hypre              — HYPRE source repo
#   fds/deps/sundials           — SUNDIALS source repo
#   fds/deps/libs/{hypre,sundials}/<ver>  — installed libraries
#   fds/deps/fds -> ..          — symlink so build scripts can resolve $FIREMODELS/fds/...

export FDS_ROOT=/shared/home/wel1come1234/workspace/fds
export FIREMODELS=$FDS_ROOT/deps                    # build_thirdparty_libs.sh root
export FDS_BIN=$FDS_ROOT/Build/impi_intel_linux/fds_impi_intel_linux

# Intel oneAPI 2023.2 (compiler + IMPI + MKL).
# Some oneAPI vars.sh scripts touch unset variables, so disable -u while sourcing.
if [ -z "${ONEAPI_ROOT:-}" ]; then
    _had_u=0
    case $- in *u*) _had_u=1;; esac
    set +u
    source /opt/intel/oneapi/setvars.sh > /dev/null
    [ $_had_u -eq 1 ] && set -u
    unset _had_u
fi

# CMake from miniconda if not on PATH.
command -v cmake >/dev/null || export PATH=/shared/home/wel1come1234/miniconda3/bin:$PATH
