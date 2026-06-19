#!/usr/bin/env python3
"""
Phase 2.4: T(z) overlay per group (with z-band guides).

For each group (A, B, C, D, E) and each offset (+1.0m, +0.5m), plot
all variant T(z) curves with baseline + paper reference, plus dashed
vertical lines at z=1.0 and z=2.0 marking the band boundaries.

Output: analysis/sensitivity/sensitivity/<group>/T_z_<offset>.png
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path("/scratch/x3319a05/fds/Engine_Room/analysis/sensitivity")
REF_CSV = Path("/scratch/x3319a05/fds/Engine_Room/analysis/grid_conv/ref_Mesh5.csv")
Z_PLOT = np.linspace(0.0, 3.0, 16)


def load_ref():
    z, T = [], []
    for ln in REF_CSV.read_text().splitlines():
        if not ln.strip(): continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def label_for(row):
    var = row.get("variable", "")
    val = row.get("value", "")
    return f"{var}={val}"


def plot_group(rows, group, offset, base_row, ref_z, ref_T, out_path):
    Tz_key = "_T_z_p1m" if offset == "p1m" else "_T_z_p05m"
    base_Tz = base_row.get(Tz_key)
    case_rows = [r for r in rows if r.get("group") == group
                 and r.get(Tz_key) is not None]
    if not case_rows:
        print(f"  skip {group} @ {offset}: no data"); return

    fig, ax = plt.subplots(figsize=(10, 7))
    # vertical guides at z=1.0, 2.0 (band boundaries)
    for zg in (1.0, 2.0):
        ax.axvline(zg, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.plot(ref_z, ref_T, "k--x", lw=2.5, ms=7,
            label="Paper (ref_Mesh5)", zorder=10)
    if base_Tz is not None:
        ax.plot(Z_PLOT, base_Tz, color="gray", lw=2.5,
                marker="s", ms=5, mfc="none",
                label="baseline (764327)", zorder=9)

    case_rows.sort(key=lambda r: (str(r["variable"]), str(r["value"])))
    cmap = plt.cm.tab10
    for i, r in enumerate(case_rows):
        Tz = r[Tz_key]
        if Tz is None: continue
        d_full = r.get(f"{offset}_delta_base_full", 0)
        ax.plot(Z_PLOT, Tz, marker="o", ms=4, mfc="none", lw=1.4,
                color=cmap(i % 10),
                label=f"{label_for(r)}  (Δ_full={d_full:.1f}°C)")

    ax.set_xlabel("Height z (m)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(0, 3); ax.set_ylim(20, 300)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper left", framealpha=0.95)
    GROUP_NAME = {"A": "A — Fire chemistry/radiation",
                  "B": "B — Floor/ceiling",
                  "C": "C — Divider (osr_north_wall)",
                  "D": "D — Interior partition walls",
                  "E": "E — Engine + equipment"}.get(group, group)
    offset_lbl = "+1.0m" if offset == "p1m" else "+0.5m"
    ax.set_title(f"Group {GROUP_NAME} — T(z) @ {offset_lbl}\n"
                 f"vertical dotted = band boundaries (low | mid | high)")
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
    out_base  = Path(args.out_base)
    if not json_path.exists():
        raise SystemExit(f"missing {json_path} — run extract.py first")
    rows = json.loads(json_path.read_text())
    base_row = next((r for r in rows if r["group"] == "baseline"), None)
    if base_row is None:
        raise SystemExit("no baseline row")
    ref_z, ref_T = load_ref()

    for group in ["A", "B", "C", "D", "E"]:
        group_dir = out_base / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for offset in ["p1m", "p05m"]:
            offset_tag = "p1p0m" if offset == "p1m" else "p0p5m"
            out_path = group_dir / f"T_z_{offset_tag}.png"
            plot_group(rows, group, offset, base_row, ref_z, ref_T, out_path)


if __name__ == "__main__":
    main()
