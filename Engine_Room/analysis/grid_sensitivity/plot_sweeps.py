#!/usr/bin/env python3
"""
Phase 2.3: Continuous-variable sweep curves with 4 z-bands per plot.

For each variable, shows:
    Left panel  — mean|ΔT| vs paper, 4 z-bands as separate lines
    Right panel — Δ vs baseline, 4 z-bands as separate lines
Each sweep plot has 2 offsets (+1m, +0.5m), total 2*7 = 14 plots.

Output: analysis/sensitivity/sensitivity/<group>/sweep_<var>_<offset>.png
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path("/scratch/x3319a05/fds/Engine_Room/analysis/sensitivity")

BAND_COLORS = {"low":  "tab:blue",
               "mid":  "tab:green",
               "high": "tab:red",
               "full": "black"}
BAND_LS     = {"low": "-",  "mid": "-",  "high": "-",  "full": "--"}
BAND_LABEL  = {"low":  "low z∈[0,1]",
               "mid":  "mid z∈[1,2]",
               "high": "high z∈[2,3]",
               "full": "full z∈[0,3]"}

# (group, sweep_name, variable, [sweep_values incl baseline], baseline_value)
SWEEPS = [
    ("A", "kappa0",        "KAPPA0",        [0.5, 1.0, 1.7, 2.5, 3.0],            1.7),
    ("A", "radfrac",       "RAD_FRAC",      [0.2, 0.3, 0.4],                      0.3),
    ("A", "soot",          "SOOT",          [0.02, 0.05, 0.10],                   0.05),
    ("A", "hrr",           "HRR",           [700, 863, 1100],                     863),
    ("B", "floor_thick",   "floor_thick",   [0.005, 0.01, 0.05, 0.2],             0.01),
    ("C", "divider_thick", "divider_thick", [0.05, 0.2, 0.5],                     0.2),
    ("E", "engine_thick",  "engine_thick",  [0.001, 0.01, 0.05, 0.2],             0.01),
]


def get_value(rows, variable, value):
    for r in rows:
        if r.get("variable") == variable and r.get("value") == value:
            return r
        try:
            if (r.get("variable") == variable and
                isinstance(value, (int, float)) and
                abs(float(r.get("value", 0)) - value) < 1e-6):
                return r
        except (TypeError, ValueError):
            continue
    return None


def plot_one_sweep(rows, group, sweep_name, variable, values, base_val,
                   offset, base_row, out_path):
    x = []
    by_band_paper = {b: [] for b in ["low","mid","high","full"]}
    by_band_base  = {b: [] for b in ["low","mid","high","full"]}
    for v in values:
        r = base_row if v == base_val else get_value(rows, variable, v)
        if r is None: continue
        ok = True
        for b in ["low","mid","high","full"]:
            mp = r.get(f"{offset}_{b}_mean")
            if mp is None or (isinstance(mp, float) and math.isnan(mp)):
                ok = False; break
        if not ok: continue
        x.append(v)
        for b in ["low","mid","high","full"]:
            by_band_paper[b].append(r[f"{offset}_{b}_mean"])
            db = r.get(f"{offset}_delta_base_{b}", 0)
            by_band_base[b].append(db if db is not None and not math.isnan(db) else 0)
    if len(x) < 2:
        print(f"  skip {sweep_name} @ {offset}: <2 points"); return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    offset_label = "+1.0m" if offset == "p1m" else "+0.5m"

    for b in ["low","mid","high","full"]:
        ax1.plot(x, by_band_paper[b], marker="o", lw=1.8, ms=7,
                 color=BAND_COLORS[b], linestyle=BAND_LS[b],
                 label=BAND_LABEL[b])
        ax2.plot(x, by_band_base[b], marker="s", lw=1.8, ms=7,
                 color=BAND_COLORS[b], linestyle=BAND_LS[b],
                 label=BAND_LABEL[b])
    for ax in (ax1, ax2):
        ax.axvline(base_val, color="gray", lw=1.0, ls=":", label=f"baseline ({base_val})")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="best")
        ax.set_xlabel(sweep_name)
    ax1.set_ylabel("mean |ΔT| vs paper (°C)")
    ax1.set_title(f"vs Paper (ref_Mesh5) @ {offset_label}")
    ax2.set_ylabel("Δ vs baseline (°C)")
    ax2.set_title(f"Sensitivity @ {offset_label}")
    ax2.axhline(0, color="black", lw=0.5)
    fig.suptitle(f"Group {group} — {sweep_name} sweep @ {offset_label}",
                 fontsize=12, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"  wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "cases.json"))
    ap.add_argument("--out-base", default=str(ROOT / "sensitivity"))
    args = ap.parse_args()
    json_path = Path(args.json)
    out_base = Path(args.out_base)
    if not json_path.exists():
        raise SystemExit(f"missing {json_path} — run extract.py first")
    rows = json.loads(json_path.read_text())
    base_row = next((r for r in rows if r["group"] == "baseline"), None)
    if base_row is None:
        raise SystemExit("no baseline row")

    for group, sweep_name, variable, values, base_val in SWEEPS:
        group_dir = out_base / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for offset in ["p1m", "p05m"]:
            offset_tag = "p1p0m" if offset == "p1m" else "p0p5m"
            out_path = group_dir / f"sweep_{sweep_name}_{offset_tag}.png"
            plot_one_sweep(rows, group, sweep_name, variable, values, base_val,
                           offset, base_row, out_path)


if __name__ == "__main__":
    main()
