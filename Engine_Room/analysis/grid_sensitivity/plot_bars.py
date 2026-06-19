#!/usr/bin/env python3
"""
Phase 2.2: Sensitivity ranking bar charts — 4 z-bands × 2 offsets × 2 modes = 16 charts.

z-bands:
    low    z ∈ [0.0, 1.0]
    mid    z ∈ [1.0, 2.0]
    high   z ∈ [2.0, 3.0]
    full   z ∈ [0.0, 3.0]

Modes:
    magnitude  — |Δ vs baseline| (sorted by absolute change, "how sensitive")
    signed     — mean(T_case − T_baseline) (sorted by signed value, "which direction")

Signed mode shows DIRECTION:
    + (red bars)   → variable INCREASES T in that band
    − (blue bars)  → variable DECREASES T in that band

Output: analysis/sensitivity/sensitivity/bars/
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path("/scratch/x3319a05/fds/Engine_Room/analysis/sensitivity")

BANDS = ["low", "mid", "high", "full"]
BAND_LABEL = {
    "low":  "z ∈ [0.0, 1.0]",
    "mid":  "z ∈ [1.0, 2.0]",
    "high": "z ∈ [2.0, 3.0]",
    "full": "z ∈ [0.0, 3.0]",
}

GROUP_COLOR = {"A": "tab:red",    "B": "tab:orange",
               "C": "tab:green",  "D": "tab:blue",
               "E": "tab:purple", "baseline": "k"}
GROUP_LABEL = {"A": "A: Fire chem/rad", "B": "B: Floor/ceiling",
               "C": "C: Divider",       "D": "D: Walls (partition)",
               "E": "E: Engine"}


def label_for(row):
    if row["group"] == "baseline":
        return "baseline (new)"
    var = row.get("variable", "")
    val = row.get("value", "")
    return f"{var}={val}"


def plot_magnitude(rows, offset, band, out_path):
    """|Δ vs baseline| — sorted by magnitude."""
    key = f"{offset}_delta_base_{band}"
    bars = [(label_for(r), r["group"], r[key])
            for r in rows
            if r["group"] != "baseline"
            and r.get(key) is not None
            and not (isinstance(r[key], float) and math.isnan(r[key]))]
    bars.sort(key=lambda t: t[2], reverse=True)
    if not bars: return

    fig, ax = plt.subplots(figsize=(11, max(7, 0.32 * len(bars))))
    labels = [b[0] for b in bars]
    vals = [b[2] for b in bars]
    colors = [GROUP_COLOR[b[1]] for b in bars]
    y_pos = np.arange(len(vals))
    ax.barh(y_pos, vals, color=colors, edgecolor="black", linewidth=0.5)
    vmax = max(vals)
    for i, v in enumerate(vals):
        ax.text(v + vmax * 0.01, i, f"{v:.1f}", va="center", fontsize=8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    offset_label = "+1.0m" if offset == "p1m" else "+0.5m"
    ax.set_xlabel(f"|Δ| = mean |T_case − T_baseline| at {offset_label}, "
                  f"{BAND_LABEL[band]} (°C)")
    ax.set_title(f"Magnitude of sensitivity @ {offset_label} — {BAND_LABEL[band]}\n"
                 f"(baseline=grid_mesh1_764327)")
    ax.grid(axis="x", alpha=0.3)
    handles = [Patch(facecolor=GROUP_COLOR[g], label=lab)
               for g, lab in GROUP_LABEL.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"  wrote {out_path}")


def plot_signed(rows, offset, band, out_path):
    """Signed Δ vs baseline — sorted by signed value, colored by direction."""
    key = f"{offset}_signed_delta_base_{band}"
    bars = [(label_for(r), r["group"], r[key])
            for r in rows
            if r["group"] != "baseline"
            and r.get(key) is not None
            and not (isinstance(r[key], float) and math.isnan(r[key]))]
    bars.sort(key=lambda t: t[2])  # ascending (most negative first)
    if not bars: return

    fig, ax = plt.subplots(figsize=(11, max(7, 0.32 * len(bars))))
    labels = [b[0] for b in bars]
    vals = [b[2] for b in bars]
    # Color by direction: + (heats up) = red shades, − (cools) = blue shades
    colors = ["tab:red" if v > 0 else "tab:blue" for v in vals]
    edge_color_by_group = [GROUP_COLOR[b[1]] for b in bars]
    y_pos = np.arange(len(vals))
    ax.barh(y_pos, vals, color=colors, edgecolor=edge_color_by_group, linewidth=2.0)
    vmax = max(abs(v) for v in vals)
    for i, v in enumerate(vals):
        ha = "left" if v >= 0 else "right"
        offset_text = vmax * 0.01 if v >= 0 else -vmax * 0.01
        ax.text(v + offset_text, i, f"{v:+.1f}", va="center", ha=ha, fontsize=8)
    ax.axvline(0, color="black", lw=1.0)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    offset_label = "+1.0m" if offset == "p1m" else "+0.5m"
    ax.set_xlabel(f"Signed Δ = mean (T_case − T_baseline) at {offset_label}, "
                  f"{BAND_LABEL[band]} (°C)")
    ax.set_title(f"Direction of sensitivity @ {offset_label} — {BAND_LABEL[band]}\n"
                 f"(RED = heats up,  BLUE = cools down,  border color = group)")
    ax.grid(axis="x", alpha=0.3)
    handles = [
        Patch(facecolor="tab:red", label="+ heats up"),
        Patch(facecolor="tab:blue", label="− cools down"),
    ] + [
        Patch(facecolor="white", edgecolor=GROUP_COLOR[g], label=lab, linewidth=2)
        for g, lab in GROUP_LABEL.items()
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=7)
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
    out_dir = Path(args.out_base) / "bars"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not json_path.exists():
        raise SystemExit(f"missing {json_path} — run extract.py first")
    rows = json.loads(json_path.read_text())
    for offset in ["p1m", "p05m"]:
        offset_tag = "p1p0m" if offset == "p1m" else "p0p5m"
        for band in BANDS:
            plot_magnitude(rows, offset, band,
                           out_dir / f"bars_magnitude_{offset_tag}_{band}.png")
            plot_signed(rows, offset, band,
                        out_dir / f"bars_signed_{offset_tag}_{band}.png")


if __name__ == "__main__":
    main()
