#!/bin/bash
# Submit 28-case sensitivity sweep.  Each case = baseline + ONE variable
# changed.  Baseline anchor = grid_mesh1_759273 setup (M1, T_END=300).
#
# Usage:
#   ./submit_sensitivity.sh            # submits all 28 cases
#   ./submit_sensitivity.sh --dry      # render inputs only, no sbatch

set -euo pipefail
DRY=${1:-}
ROOT=/scratch/x3319a05/fds/Engine_Room
mkdir -p "$ROOT/inputs" "$ROOT/logs"

# Per-case sbatch template (one-off, 4 ranks, 30 min)
SBATCH_TPL=$(cat <<'EOF'
#!/bin/bash
#SBATCH --job-name=__JOB_NAME__
#SBATCH --partition=cpu
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=00:45:00
#SBATCH --comment=etc
#SBATCH --output=/scratch/x3319a05/fds/Engine_Room/logs/%x.%j.out
#SBATCH --error=/scratch/x3319a05/fds/Engine_Room/logs/%x.%j.err
set -euo pipefail
source /scratch/x3319a05/fds/setup_docs/scripts/fds_env_kisti.sh
export OMP_NUM_THREADS=1
cd /scratch/x3319a05/fds/Engine_Room/Results/__JOB_NAME__
mpiexec -n 4 "$FDS_BIN" /scratch/x3319a05/fds/Engine_Room/inputs/__JOB_NAME__.fds
EOF
)

# Common: render baseline input, then override one parameter per case
# NEW BASELINE GEOMETRY: fire & door2 both centred at x=7.5-8.5
COMMON_ARGS=(
    --ijk 78 60 18 --mesh-split 2 2 1
    --fire-xb 7.5 8.5 1.0 2.0 --t-end 300
    --ventilation-method 2 --ventilation-velocity 1.0
)

# Case definitions: format "CASE_ID  extra_args..."
read -r -d '' CASES <<'EOF' || true
sens_A1a_kappa_0p5      --kappa0 0.5
sens_A1b_kappa_1p0      --kappa0 1.0
sens_A1c_kappa_2p5      --kappa0 2.5
sens_A1d_kappa_3p0      --kappa0 3.0
sens_A2a_radfrac_0p2    --radiative-fraction 0.2
sens_A2b_radfrac_0p4    --radiative-fraction 0.4
sens_A3a_soot_0p02      --soot-yield 0.02
sens_A3b_soot_0p10      --soot-yield 0.10
sens_A4a_hrr_700        --hrr-peak 700
sens_A4b_hrr_1100       --hrr-peak 1100
sens_B1a_floor_thick_0p005      --floor-thickness 0.005
sens_B1b_floor_thick_0p05       --floor-thickness 0.05
sens_B1c_floor_thick_0p2        --floor-thickness 0.2
sens_B2_floor_backing_exposed   --floor-backing EXPOSED
sens_B3_floor_coldsink20        --floor-tmp 20
sens_C1a_divider_thick_0p05     --divider-thickness 0.05
sens_C1b_divider_thick_0p5      --divider-thickness 0.5
sens_C2_divider_backing_insulated  --divider-backing INSULATED
sens_C3_divider_inert           --divider-inert
sens_D1_walls_insulated_steel   --cold-walls
sens_D2_walls_coldsink20        --walls-tmp 20
sens_D3_walls_exposed_steel     --walls-exposed-steel
sens_E1_engine_tmp20            --engine-tmp 20
sens_E2a_engine_thick_0p001     --engine-thickness 0.001
sens_E2b_engine_thick_0p05      --engine-thickness 0.05
sens_E2c_engine_thick_0p2       --engine-thickness 0.2
sens_E3_engine_backing_exposed  --engine-backing EXPOSED
EOF

n=0
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case_id=$(echo "$line" | awk '{print $1}')
    extra_args=$(echo "$line" | cut -d' ' -f2-)
    n=$((n+1))
    INPUT="$ROOT/inputs/${case_id}.fds"
    OUTDIR="$ROOT/Results/${case_id}"
    mkdir -p "$OUTDIR"
    echo "[$n] $case_id : $extra_args"
    python3 "$ROOT/gen_engine_room.py" "${COMMON_ARGS[@]}" $extra_args \
            --chid "$case_id" --out "$INPUT" >/dev/null
    if [[ "$DRY" != "--dry" ]]; then
        SCRIPT=$(mktemp)
        echo "$SBATCH_TPL" | sed "s|__JOB_NAME__|$case_id|g" > "$SCRIPT"
        # Retry until accepted (skip QOSMaxSubmitJobPerUserLimit)
        while true; do
            RESULT=$(sbatch "$SCRIPT" 2>&1)
            if echo "$RESULT" | grep -q "Submitted batch job"; then
                echo "$RESULT" | tee -a "$ROOT/logs/sensitivity_jobids.txt"
                break
            elif echo "$RESULT" | grep -q "QOSMaxSubmitJobPerUserLimit"; then
                echo "  (queue full, sleeping 30s)"
                sleep 30
            else
                echo "$RESULT"; break
            fi
        done
        rm "$SCRIPT"
    fi
done <<< "$CASES"

echo "Total: $n cases"
