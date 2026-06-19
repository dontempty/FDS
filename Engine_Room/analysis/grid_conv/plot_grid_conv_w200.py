#!/usr/bin/env python3
"""
Grid convergence T(z) at +1m and +0.5m offset, OLD geometry (fire center 8.4, 1.5),
averaged over t = 200 ~ 300 s (via SLCF YZ at x=8.40).

Compares 4 meshes (M1, M3, M5, M6) against paper references (ref_Mesh1, ref_Mesh5).

Output: analysis/grid_conv/grid_conv_w200.png
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "backup" / "Results_backup_old_geometry"
OUT = ROOT / "analysis" / "grid_conv"
REF_M1 = OUT / "ref_Mesh1.csv"
REF_M5 = OUT / "ref_Mesh5.csv"

# Old geometry: fire = [7.9, 8.9] × [1.0, 2.0]   →  center (8.4, 1.5)
SLICE_X = 8.40         # YZ slice at fire center x
OFFSETS = [(2.5, "+1.0 m  (y=2.5)"),
           (2.0, "+0.5 m  (y=2.0)")]
WIN = (200.0, 300.0)
Z_PLOT = np.linspace(0.0, 3.0, 16)

MESHES = [
    ("grid_mesh1_759273", "M1  (78×60×18 = 84k)",    "tab:blue"),
    ("grid_mesh3_759807", "M3  (156×120×36 = 670k)", "tab:green"),
    ("grid_mesh5_759808", "M5  (208×160×48 = 1.6M)", "tab:orange"),
    ("grid_mesh6_760359", "M6  (260×200×60 = 3.1M)", "tab:red"),
]


def load_ref(p):
    z, T = [], []
    for ln in p.read_text().splitlines():
        if not ln.strip(): continue
        a, b = ln.split(","); z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def load_T_z(case_id, y_target):
    p = RES / case_id
    sim = fdsreader.Simulation(str(p))
    cands = [(abs(s.extent.x_start - SLICE_X), s)
             for s in sim.slices
             if s.orientation == 1 and s.quantity.name == "TEMPERATURE"]
    if not cands: return None
    sl = min(cands, key=lambda t: t[0])[1]
    T = sl.to_global(masked=True, fill=np.nan)
    t_arr = sl.times
    ext = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T.shape[2])
    iy = int(np.argmin(np.abs(y_arr - y_target)))
    win = (t_arr >= WIN[0]) & (t_arr <= WIN[1])
    if not win.any(): return None
    T_avg = np.nanmean(T[win, iy, :], axis=0)
    return np.interp(Z_PLOT, z_arr, T_avg)


def main():
    z_ref1, T_ref1 = load_ref(REF_M1)
    z_ref5, T_ref5 = load_ref(REF_M5)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    for ax_idx, (y_target, off_lbl) in enumerate(OFFSETS):
        ax = axes[ax_idx]
        ax.axvline(0, color="none")  # placeholder
        for zg in (1.0, 2.0):
            ax.axhline(zg, color="lightgray", lw=1.0, ls=":", zorder=0)

        ax.plot(T_ref1, z_ref1, "k:o", lw=2.0, ms=6, mfc="none",
                label="Paper M1 (ref_Mesh1)", zorder=9)
        ax.plot(T_ref5, z_ref5, "k--x", lw=2.4, ms=7,
                label="Paper M5 (ref_Mesh5)", zorder=10)

        for cid, lab, color in MESHES:
            T = load_T_z(cid, y_target)
            if T is None:
                print(f"  skip {cid}: no data"); continue
            err5 = float(np.nanmean(np.abs(T - np.interp(Z_PLOT, z_ref5, T_ref5))))
            ax.plot(T, Z_PLOT, marker="o", ms=5, lw=1.8, mfc="none", color=color,
                    label=f"{lab}  (|Δ|_M5={err5:.1f}°C)")

        ax.set_xlabel("Temperature (°C)")
        ax.set_ylabel("Height z (m)")
        ax.set_ylim(0, 3); ax.set_xlim(20, 280)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower right", framealpha=0.95)
        ax.set_title(f"T(z) @ {off_lbl}")

    fig.suptitle("Grid convergence — old geometry  (fire 7.9–8.9, center 8.4)\n"
                 f"YZ SLCF @ x={SLICE_X:.2f} m,  averaged over t = {WIN[0]:.0f}–{WIN[1]:.0f} s",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out_path = OUT / "grid_conv_w200.png"
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"wrote {out_path}")

    # Console summary
    print(f"\n{'Mesh':<35} {'Offset':<6} "
          f"{'|Δ|_M1':>7} {'|Δ|_M5':>7} {'T_floor':>7} {'T_mid':>7} {'T_ceil':>7}")
    print("-" * 90)
    for cid, lab, _ in MESHES:
        for y_target, off_lbl in OFFSETS:
            T = load_T_z(cid, y_target)
            if T is None: continue
            errM1 = float(np.nanmean(np.abs(T - np.interp(Z_PLOT, z_ref1, T_ref1))))
            errM5 = float(np.nanmean(np.abs(T - np.interp(Z_PLOT, z_ref5, T_ref5))))
            print(f"{cid:<35} {off_lbl[:5]:<6} "
                  f"{errM1:>7.2f} {errM5:>7.2f} "
                  f"{T[0]:>7.1f} {T[len(T)//2]:>7.1f} {T[-1]:>7.1f}")


if __name__ == "__main__":
    main()
