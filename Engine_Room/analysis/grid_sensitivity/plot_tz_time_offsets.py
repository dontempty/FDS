#!/usr/bin/env python3
"""
T(z, t) at offset columns from fire center — uses YZ SLCF at x=8.10.

Two sample columns:
    +0.5m :  (x=8.10, y=1.95)    # cy + 0.5
    +1.0m :  (x=8.10, y=2.45)    # cy + 1.0
  (cy = 1.45 = fire y-center)

For each case, 4-panel figure (2 rows = offsets, 2 cols = views):
    Left  col : T(z) snapshots at t = 50, 100, 150, 200, 250, 300 s
    Right col : T(z, t) heatmap

Output: analysis/sensitivity/sensitivity/tz_time_offsets/<case>.png
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "sensitivity" / "sensitivity" / "tz_time_offsets"
OUT.mkdir(parents=True, exist_ok=True)
REF_CSV = ROOT / "analysis" / "grid_conv" / "ref_Mesh5.csv"

SLICE_X   = 8.10
OFFSETS   = [(1.95, "+0.5 m  (y=1.95)"),
             (2.45, "+1.0 m  (y=2.45)")]
SNAPSHOTS = [50, 100, 150, 200, 250, 300]
VMIN, VMAX = 20.0, 350.0    # full T span for offset columns


def load_ref():
    z, T = [], []
    for ln in REF_CSV.read_text().splitlines():
        if not ln.strip(): continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def find_yz_slice(sim, target):
    cands = [(abs(sl.extent.x_start - target), sl)
             for sl in sim.slices
             if sl.orientation == 1 and sl.quantity.name == "TEMPERATURE"]
    if not cands: return None
    return min(cands, key=lambda t: t[0])[1]


def extract_tz_at_y(sl, y_target):
    """Return (times, z_arr, T) with T shape (n_times, n_z) sampled at y=y_target."""
    T_all = sl.to_global(masked=True, fill=np.nan)   # (n_t, n_y, n_z)
    t_arr = sl.times
    ext = sl.extent
    n_t, n_y, n_z = T_all.shape
    y_arr = np.linspace(ext.y_start, ext.y_end, n_y)
    z_arr = np.linspace(ext.z_start, ext.z_end, n_z)
    iy = int(np.argmin(np.abs(y_arr - y_target)))
    return t_arr, z_arr, T_all[:, iy, :]


def plot_case(case_id, label, out_path, vmax=VMAX):
    case_res = RES / case_id
    if not (case_res / f"{case_id}.smv").exists():
        print(f"  skip {case_id} (no .smv)"); return
    try:
        sim = fdsreader.Simulation(str(case_res))
    except Exception as e:
        print(f"  fdsreader fail: {e}"); return
    sl = find_yz_slice(sim, SLICE_X)
    if sl is None:
        print(f"  no YZ slice in {case_id}"); return

    ref_z, ref_T = load_ref()

    fig, axes = plt.subplots(2, 2, figsize=(14, 9),
                             gridspec_kw={"width_ratios": [1, 1.2]})

    cmap_snap = plt.cm.viridis
    for ir, (y_target, off_lbl) in enumerate(OFFSETS):
        t_arr, z_arr, T = extract_tz_at_y(sl, y_target)

        # Left: snapshots
        ax1 = axes[ir][0]
        for k, t_target in enumerate(SNAPSHOTS):
            it = int(np.argmin(np.abs(t_arr - t_target)))
            ax1.plot(T[it], z_arr, marker="o", ms=4, lw=1.4,
                     color=cmap_snap(k / (len(SNAPSHOTS) - 1)),
                     label=f"t = {t_arr[it]:.0f} s")
        # Paper reference (Lan 2023 ref_Mesh5) — Fig 5 = "centre +1 m" column
        ref_lbl = "Paper (ref_Mesh5)"
        if y_target == 2.45:
            ref_lbl += "  ← matched"
        else:
            ref_lbl += "  (at +1m)"
        ax1.plot(ref_T, ref_z, "k--x", lw=2.4, ms=7, label=ref_lbl, zorder=10)

        ax1.set_xlim(20, vmax); ax1.set_ylim(0, 3)
        ax1.set_xlabel("Temperature (°C)")
        ax1.set_ylabel("Height z (m)")
        ax1.grid(alpha=0.3)
        ax1.legend(fontsize=8, loc="lower right")
        ax1.set_title(f"T(z) snapshots @ {off_lbl}")

        # Right: heatmap
        ax2 = axes[ir][1]
        extent = [t_arr[0], t_arr[-1], z_arr[0], z_arr[-1]]
        im = ax2.imshow(T.T, aspect="auto", origin="lower",
                        extent=extent, cmap="jet",
                        vmin=20, vmax=vmax, interpolation="bilinear")
        ax2.set_xlabel("Time (s)"); ax2.set_ylabel("Height z (m)")
        ax2.set_ylim(0, 3)
        ax2.set_title(f"T(z, t) heatmap @ {off_lbl}")
        cbar = plt.colorbar(im, ax=ax2)
        cbar.set_label("Temperature (°C)")

    fig.suptitle(f"{label}  [{case_id}]\n"
                 f"Offset columns from fire center,  YZ SLCF @ x={SLICE_X:.2f} m",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"  wrote {out_path}")


CASES = [
    ("grid_mesh1_764327",          "Baseline (M1)"),
    ("sens_OPT1_combined",         "OPT1: engine_thick=0.2 + cold-walls + KAPPA0=1.0 + SOOT=0.10 + floor EXPOSED"),
    ("sens_OPT2_engine_walls",     "OPT2: engine_thick=0.2 + cold-walls"),
    ("sens_OPT3c_no_soot_no_floor","OPT3c: engine_thick=0.2 + cold-walls + KAPPA0=1.0  (OPT1 - SOOT - floor)"),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for cid, lab in CASES:
        if only and not (cid == only or cid.startswith(only)): continue
        out_path = OUT / f"{cid}.png"
        plot_case(cid, lab, out_path)


if __name__ == "__main__":
    main()
