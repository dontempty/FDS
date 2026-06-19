#!/bin/bash
#SBATCH --job-name=eng_gconv
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=12:00:00
# nodes / ntasks NOT pinned — SLURM picks any free CPUs.  Pass --ntasks=N via
# CLI (e.g. `sbatch --ntasks=4 ...`) to specify how many MPI ranks.
#SBATCH --comment=etc
#SBATCH --output=logs/%x.%j.out
#SBATCH --error=logs/%x.%j.err

# =============================================================================
# Engine_Room grid-convergence pipeline (Lan et al. 2023, §3.3 + Fig 5).
#
# Condition (paper-fixed):
#   Method 2, v = 1 m/s, fire = 863 kW diesel pool fire at OSR floor,
#   T_END = 300 s.  Vertical T(z) DEVC at (8.5, 2.5, z=0..3).
#
# Mesh selected via environment variable MESH (1..7):
#   1: 78×60×18   (84,240   cells)   single rank
#   2: 104×80×24  (199,680  cells)   single rank
#   3: 130×100×30 (390,000  cells)   single rank
#   4: 156×120×36 (673,920  cells)   4 ranks (2×2×1)
#   5: 182×140×42 (1,070,160 cells)  8 ranks (2×2×2)
#   6: 208×160×48 (1,597,440 cells)  16 ranks (4×2×2)
#   7: 234×180×54 (2,274,480 cells)  18 ranks (3×2×3)
#
# Submit via wrapper:   ./submit_grid_conv.sh <MESH>
# Output: Results/grid_mesh{N}_{JOBID}/{CHID}.{smv,out,devc.csv,...}
# =============================================================================

set -euo pipefail

# ---- USER PARAMETERS --------------------------------------------------------
MESH=${MESH:?"Set MESH=1..7 via --export=ALL,MESH=N"}
T_END=300
FIRE_XB="7.5 8.5 1.0 2.0"          # 1×1 m square pool, aligned with door2 (x=7.5-8.5)
DT_DEVC=1.0
DT_HRR=1.0
DT_SLCF=10.0
# ---- end USER PARAMETERS ----------------------------------------------------

case "$MESH" in
  1) IJK="78 60 18";   SPLIT="2 2 1"; NRANKS=4  ;;   # 78/2=39, 60/2=30, 18/1=18 (clean split)
  2) IJK="104 80 24";  SPLIT="1 1 1"; NRANKS=1  ;;
  3) IJK="130 100 30"; SPLIT="2 2 1"; NRANKS=4  ;;   # was 1 rank (~7h) → 4 ranks (~2h)
  4) IJK="156 120 36"; SPLIT="2 2 1"; NRANKS=4  ;;
  5) IJK="182 140 42"; SPLIT="2 7 2"; NRANKS=28 ;;   # was 8 ranks (TIMEOUT) → 28 ranks (4x4x2 fails: 182/4=45.5)
  6) IJK="208 160 48"; SPLIT="4 5 1"; NRANKS=20 ;;   # 208/4=52, 160/5=32, 48/1=48 (clean, fits 20 free CPUs)
  7) IJK="234 180 54"; SPLIT="3 2 3"; NRANKS=18 ;;
  *) echo "ERROR: invalid MESH=$MESH (must be 1..7)"; exit 2 ;;
esac

# ---- environment ------------------------------------------------------------
source /scratch/x3319a05/fds/setup_docs/scripts/fds_env_kisti.sh
export OMP_NUM_THREADS=1
unset PYTHONPATH PYTHONHOME
module load python/3.12.4 2>/dev/null || module load python/3.14.2 2>/dev/null || true

ROOT=/scratch/x3319a05/fds/Engine_Room
CHID_BASE="grid_mesh${MESH}"
CHID="${CHID_BASE}_${SLURM_JOB_ID}"
INPUT="$ROOT/inputs/${CHID}.fds"
OUT_DIR="$ROOT/Results/${CHID}"
mkdir -p "$OUT_DIR" "$ROOT/logs" "$ROOT/inputs"

echo "=================================================================="
echo "Job:    $SLURM_JOB_ID  ($SLURM_JOB_NAME)"
echo "Mesh:   ${MESH}   IJK=${IJK}   split=${SPLIT}   ranks=${NRANKS}"
echo "Node:   $SLURM_JOB_NODELIST"
echo "CHID:   $CHID"
echo "Out:    $OUT_DIR"
echo "Start:  $(date)"
echo "=================================================================="

# ---- step 1: generate input -------------------------------------------------
echo "--- step 1: generate input ---"
cd "$ROOT"
python3 gen_engine_room.py \
    --ijk $IJK \
    --mesh-split $SPLIT \
    --xb 0 13 0 10 0 3 \
    --fire-xb $FIRE_XB \
    --t-end "$T_END" \
    --dt-devc "$DT_DEVC" --dt-hrr "$DT_HRR" --dt-slcf "$DT_SLCF" \
    --ventilation-method 2 \
    --ventilation-velocity 1.0 \
    --chid "$CHID" \
    --out "$INPUT"

# ---- step 2: run FDS --------------------------------------------------------
echo "--- step 2: run FDS ---"
cd "$OUT_DIR"
mpiexec -n "$NRANKS" "$FDS_BIN" "$INPUT"

echo "=================================================================="
echo "End:    $(date)"
echo "Output: $OUT_DIR/${CHID}_devc.csv   (gridconv_T-* columns)"
echo "=================================================================="
