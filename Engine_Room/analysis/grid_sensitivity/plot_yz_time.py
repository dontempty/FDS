#!/usr/bin/env python3
"""
YZ plane temperature evolution over time — slice at x=8.10 (paper Fig 6).

For each case, produces a 2x3 grid of YZ slice snapshots at
t = 50, 100, 150, 200, 250, 300 s.

Output: analysis/sensitivity/sensitivity/yz_time/<case>.png
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import re, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "sensitivity" / "sensitivity" / "yz_time"
OUT.mkdir(parents=True, exist_ok=True)

SLICE_X = 8.10
SNAPSHOTS = [50, 100, 150, 200, 250, 300]   # seconds
VMIN, VMAX = 20.0, 150.0   # match visualize_groups.py YZ range
N_LEVELS = 30
N_TICKS = 9


def parse_input(case_id):
    p = ROOT / "inputs" / f"{case_id}.fds"
    if not p.exists(): return [], []
    txt = p.read_text()
    obsts = []
    for m in re.finditer(r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID='([^']+)'", txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        obsts.append((xb, m.group(2)))
    holes = []
    for m in re.finditer(r"&HOLE\s+XB=\s*([\d.,\s\-+eE]+?)\s*/", txt):
        holes.append([float(v) for v in m.group(1).replace(",", " ").split()])
    return obsts, holes


def find_yz_slice(sim, target):
    cands = [(abs(sl.extent.x_start - target), sl)
             for sl in sim.slices
             if sl.orientation == 1 and sl.quantity.name == "TEMPERATURE"]
    if not cands: return None
    return min(cands, key=lambda t: t[0])[1]


def plot_case(case_id, label, out_path):
    case_res = RES / case_id
    if not (case_res / f"{case_id}.smv").exists():
        print(f"  skip {case_id} (no .smv)"); return
    try:
        sim = fdsreader.Simulation(str(case_res))
    except Exception as e:
        print(f"  fdsreader fail for {case_id}: {e}"); return
    sl = find_yz_slice(sim, SLICE_X)
    if sl is None:
        print(f"  no YZ slice in {case_id}"); return

    T_all = sl.to_global(masked=True, fill=np.nan)   # (n_times, n_y, n_z)
    t_arr = sl.times
    ext = sl.extent
    nA, nB = T_all.shape[1], T_all.shape[2]
    A = np.linspace(ext.y_start, ext.y_end, nA)
    B = np.linspace(ext.z_start, ext.z_end, nB)
    Ag, Bg = np.meshgrid(A, B, indexing="ij")
    dA, dB = A[1]-A[0], B[1]-B[0]

    obsts, holes = parse_input(case_id)
    levels = np.linspace(VMIN, VMAX, N_LEVELS)
    ticks  = np.linspace(VMIN, VMAX, N_TICKS).tolist()

    fig, axes = plt.subplots(2, 3, figsize=(18, 9), constrained_layout=False)
    fig.subplots_adjust(left=0.05, right=0.91, top=0.92, bottom=0.06,
                        wspace=0.18, hspace=0.25)

    for k, t_target in enumerate(SNAPSHOTS):
        ax = axes[k // 3][k % 3]
        it = int(np.argmin(np.abs(t_arr - t_target)))
        T_inst = T_all[it].copy()

        # HOLE fill (cosmetic — fill NaN inside HOLE cells crossing this YZ)
        for hxb in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = hxb
            if not (hx1 <= SLICE_X <= hx2): continue
            in_box = (Ag>=hy1-dA)&(Ag<=hy2+dA)&(Bg>=hz1-dB)&(Bg<=hz2+dB)
            nan_in = in_box & np.isnan(T_inst)
            valid_in = in_box & ~np.isnan(T_inst)
            if nan_in.any() and valid_in.any():
                T_inst[nan_in] = float(np.nanmean(T_inst[valid_in]))

        # NaN out OBST interior (avoid SLCF interpolation leakage)
        for xb, sid in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = xb
            if not (ox1 <= SLICE_X <= ox2): continue
            in_box = (Ag>=oy1)&(Ag<=oy2)&(Bg>=oz1)&(Bg<=oz2)
            for hxb in holes:
                hx1,hx2,hy1,hy2,hz1,hz2 = hxb
                if not (hx1 <= SLICE_X <= hx2): continue
                in_box &= ~((Ag>=hy1)&(Ag<=hy2)&(Bg>=hz1)&(Bg<=hz2))
            T_inst[in_box] = np.nan

        cf = ax.contourf(Ag, Bg, T_inst, levels=levels,
                         cmap="jet", extend="both")

        # OBST overlay
        for xb, sid in obsts:
            x1,x2,y1,y2,z1,z2 = xb
            if not (x1 <= SLICE_X <= x2): continue
            ax.add_patch(patches.Rectangle((y1, z1), y2-y1, z2-z1,
                                            lw=0.8, edgecolor="black",
                                            facecolor="none"))

        ax.set_xlim(0, 10); ax.set_ylim(0, 3)
        ax.set_aspect("equal")
        if k // 3 == 1: ax.set_xlabel("Y (m)")
        if k % 3 == 0:  ax.set_ylabel("Z (m)")
        ax.set_title(f"t = {t_arr[it]:.0f} s", fontsize=11)
        ax.tick_params(labelsize=8)

    # Shared colorbar on the right
    cbar_ax = fig.add_axes([0.925, 0.1, 0.014, 0.8])
    cbar = fig.colorbar(cf, cax=cbar_ax, ticks=ticks)
    cbar.set_label("Temperature (°C)")

    fig.suptitle(f"{label}  [{case_id}]\n"
                 f"YZ plane @ x = {SLICE_X:.2f} m  (PBX through fire flank)",
                 fontsize=11, y=0.98)
    fig.savefig(out_path, dpi=120)
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
