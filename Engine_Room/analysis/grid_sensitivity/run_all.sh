#!/bin/bash
# Run full sensitivity analysis pipeline.
# Pre-requisite: all 27 sensitivity cases + new baseline (764189) completed.
#
# Usage:
#   ./analysis/sensitivity/run_all.sh

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd /scratch/x3319a05/fds/Engine_Room

echo "============================================"
echo " Sensitivity analysis pipeline"
echo "============================================"

echo ""
echo "[Phase 1+2.1] extract.py"
python3 "$HERE/extract.py"

echo ""
echo "[Phase 2.2] plot_bars.py"
python3 "$HERE/plot_bars.py"

echo ""
echo "[Phase 2.3] plot_sweeps.py"
python3 "$HERE/plot_sweeps.py"

echo ""
echo "[Phase 2.4] plot_groups.py"
python3 "$HERE/plot_groups.py"

echo ""
echo "[Phase 3.1+3.2] find_extremes.py"
python3 "$HERE/find_extremes.py"

echo ""
echo "============================================"
echo " Done. Outputs in $HERE/"
echo "============================================"
ls -la "$HERE"/*.png "$HERE"/*.csv "$HERE"/*.json 2>&1 | head -30
