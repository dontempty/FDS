#!/usr/bin/env python3
"""
Phase 3.1 + 3.2: Find top-3 / worst-3 cases vs paper, run slice visualizations.

Sorts cases by p1m_mean_full and p05m_mean_full (combined avg).
Generates XZ / YZ / XY slices for each via /tmp/plot_all_slices.py.

Outputs:
    analysis/sensitivity/best_3/<case_id>/<case_id>_{xz,yz,xy}_*.png
    analysis/sensitivity/worst_3/<case_id>/<case_id>_{xz,yz,xy}_*.png
"""
from __future__ import annotations
import json, math, os, subprocess, sys
from pathlib import Path

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
OUT = ROOT / "analysis" / "sensitivity"
JSON_PATH = OUT / "cases.json"
PLOT_SCRIPT = "/tmp/plot_all_slices.py"


def combined_score(row):
    """Combined paper-error score across both offsets."""
    p1 = row.get("p1m_mean_full")
    p05 = row.get("p05m_mean_full")
    if any(v is None or (isinstance(v, float) and math.isnan(v))
           for v in [p1, p05]):
        return float("inf")
    return (p1 + p05) / 2


def run_slices(case_id, target_dir):
    """Render 3 slice plots for one case into target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    if not Path(PLOT_SCRIPT).exists():
        print(f"  plot script {PLOT_SCRIPT} missing"); return False
    # The script outputs to analysis/flow_vent/<short>/  by default.
    # We just symlink the produced files into our target dir.
    short = case_id.split("_")[-1]
    src_dir = ROOT / "analysis" / "flow_vent" / short
    try:
        subprocess.run(["python3", PLOT_SCRIPT, case_id],
                       check=True, capture_output=True, text=True, timeout=300)
    except subprocess.CalledProcessError as e:
        print(f"  plot failed for {case_id}: {e.stderr[:200]}"); return False
    except subprocess.TimeoutExpired:
        print(f"  plot timeout for {case_id}"); return False
    # Copy produced PNGs to our target dir
    if src_dir.exists():
        for png in src_dir.glob("*.png"):
            tgt = target_dir / png.name
            tgt.write_bytes(png.read_bytes())
        print(f"  → {target_dir}/  ({len(list(target_dir.glob('*.png')))} pngs)")
        return True
    return False


def main():
    if not JSON_PATH.exists():
        raise SystemExit(f"missing {JSON_PATH} — run extract.py first")
    rows = json.loads(JSON_PATH.read_text())
    # exclude baseline & failed cases
    valid = [r for r in rows
             if r["group"] != "baseline"
             and r["status"] in ("OK", "WARN_HRR")]
    valid.sort(key=combined_score)

    if not valid:
        raise SystemExit("no valid cases to rank")

    best_3  = valid[:3]
    worst_3 = list(reversed(valid[-3:]))

    print(f"\n=== Top-3 (closest to paper) ===")
    for r in best_3:
        print(f"  {r['case_id']:<40} score={combined_score(r):.2f} °C  "
              f"(p1m_full={r['p1m_mean_full']:.2f}, "
              f"p05m_full={r['p05m_mean_full']:.2f})")

    print(f"\n=== Worst-3 (farthest from paper) ===")
    for r in worst_3:
        print(f"  {r['case_id']:<40} score={combined_score(r):.2f} °C  "
              f"(p1m_full={r['p1m_mean_full']:.2f}, "
              f"p05m_full={r['p05m_mean_full']:.2f})")

    print("\n--- generating slice plots ---")
    best_dir  = OUT / "best_3"
    worst_dir = OUT / "worst_3"
    for r in best_3:
        run_slices(r["case_id"], best_dir / r["case_id"])
    for r in worst_3:
        run_slices(r["case_id"], worst_dir / r["case_id"])


if __name__ == "__main__":
    main()
