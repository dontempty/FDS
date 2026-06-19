#!/usr/bin/env python3
"""
T(z, t) — z-profile evolution over time.

Source: _devc.csv  pt_temperature_z* columns at (cx=8.0, cy=1.45, various z)
  → 10 z-points: 0.05, 0.38, 0.71, 1.03, 1.36, 1.69, 2.02, 2.34, 2.67, 3.00 m
  → time series at the FIRE-CENTER column

For each case, produces a 2-panel figure:
  Left  : T(z) snapshots at t = 50, 100, 150, 200, 250, 300 s
  Right : T(z, t) heatmap (full evolution)

Output: analysis/sensitivity/sensitivity/time_evolution/<case>.png
"""
from __future__ import annotations
import csv, re, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "sensitivity" / "sensitivity" / "time_evolution"
OUT.mkdir(parents=True, exist_ok=True)

SNAPSHOTS = [50, 100, 150, 200, 250, 300]   # seconds
Z_TAG_RE = re.compile(r"pt_temperature_z(\d+p\d+)$")


def load_devc_tz(case_id):
    """Return (times, z_arr, T) where T has shape (n_times, n_z)."""
    f = RES / case_id / f"{case_id}_devc.csv"
    if not f.exists():
        return None, None, None
    rows = list(csv.reader(open(f)))
    if len(rows) < 3: return None, None, None
    hdr = [c.strip() for c in rows[1]]
    # Find pt_temperature_z* columns and their z values
    z_cols = []
    for j, h in enumerate(hdr):
        m = Z_TAG_RE.match(h)
        if m:
            z = float(m.group(1).replace("p", "."))
            z_cols.append((z, j))
    if not z_cols:
        return None, None, None
    z_cols.sort()
    z_arr = np.array([z for z, _ in z_cols])
    jcols = [j for _, j in z_cols]
    jt = hdr.index("Time")
    times, T_rows = [], []
    for r in rows[2:]:
        try:
            t = float(r[jt])
            tcol = [float(r[j]) for j in jcols]
        except (ValueError, IndexError):
            continue
        times.append(t); T_rows.append(tcol)
    return np.asarray(times), z_arr, np.asarray(T_rows)


def plot_case(case_id, label, out_path, vmax=None):
    times, z_arr, T = load_devc_tz(case_id)
    if T is None:
        print(f"  skip {case_id}: no data"); return None
    if vmax is None:
        vmax = float(np.nanmax(T)) * 1.05

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6),
                                   gridspec_kw={"width_ratios":[1, 1.2]})

    # Left: snapshots at fixed times
    cmap = plt.cm.viridis
    for k, t_target in enumerate(SNAPSHOTS):
        it = int(np.argmin(np.abs(times - t_target)))
        Tz = T[it]
        ax1.plot(Tz, z_arr, marker="o", ms=5, lw=1.5,
                 color=cmap(k / (len(SNAPSHOTS) - 1)),
                 label=f"t = {times[it]:.0f} s")
    ax1.set_xlabel("Temperature (°C)")
    ax1.set_ylabel("Height z (m)")
    ax1.set_ylim(0, 3); ax1.set_xlim(20, vmax)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=9, loc="lower right")
    ax1.set_title("T(z) snapshots")

    # Right: heatmap T(z, t)
    # T shape: (n_times, n_z); we want (n_z, n_times) for imshow
    extent = [times[0], times[-1], z_arr[0], z_arr[-1]]
    im = ax2.imshow(T.T, aspect="auto", origin="lower",
                    extent=extent, cmap="jet",
                    vmin=20, vmax=vmax, interpolation="bilinear")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Height z (m)")
    ax2.set_ylim(0, 3)
    ax2.set_title("T(z, t) heatmap")
    cbar = plt.colorbar(im, ax=ax2)
    cbar.set_label("Temperature (°C)")

    fig.suptitle(f"{label}  [{case_id}]\n"
                 f"fire-center column (x=8.0, y=1.45),  "
                 f"DEVC pt_temperature_z*  (10 z-points)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"  wrote {out_path}")
    return vmax


CASES = [
    ("grid_mesh1_764327",         "Baseline (M1)"),
    ("sens_OPT1_combined",        "OPT1: engine_thick=0.2 + cold-walls + KAPPA0=1.0 + SOOT=0.10 + floor EXPOSED"),
    ("sens_OPT2_engine_walls",    "OPT2: engine_thick=0.2 + cold-walls"),
    ("sens_OPT3c_no_soot_no_floor","OPT3c: engine_thick=0.2 + cold-walls + KAPPA0=1.0  (OPT1 minus SOOT & floor)"),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    # First pass: find global vmax for consistent colors
    vmax_global = 0
    for cid, _ in CASES:
        if only and cid != only and not cid.startswith(only): continue
        _, _, T = load_devc_tz(cid)
        if T is not None:
            vmax_global = max(vmax_global, float(np.nanmax(T)))
    vmax_global *= 1.05
    print(f"global vmax = {vmax_global:.1f}°C")

    for cid, lab in CASES:
        if only and cid != only and not cid.startswith(only): continue
        out_path = OUT / f"{cid}.png"
        plot_case(cid, lab, out_path, vmax=vmax_global)


if __name__ == "__main__":
    main()
