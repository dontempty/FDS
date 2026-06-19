#!/usr/bin/env python3
"""
Grid convergence T(z) at y+0.5 and y+1.0 from fire center (new geometry).

New geometry  : fire = [7.5, 8.5] × [1.0, 2.0] → center (8.0, 1.5)
SLCF          : PBX = 8.1  (YZ slice nearest to fire center)
y offsets     : +0.5 → y = 2.0,  +1.0 → y = 2.5
Time window   : 700 – 800 s  (quasi-steady fire phase)
Compares      : M1 (84k), M3 (390k), M5 (674k)

Output: analysis/grid_conv/grid_conv_fire800.png
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT    = Path("/scratch/x3319a05/fds/Engine_Room")
RES     = ROOT / "Results"
OUT     = ROOT / "analysis" / "grid_conv"
OUT.mkdir(parents=True, exist_ok=True)
REF_M1  = OUT / "ref_Mesh1.csv"
REF_M5  = OUT / "ref_Mesh5.csv"

SLICE_X = 8.1          # PBX – YZ slice (closest available: x=8.13)
OFFSETS = [
    (1.95, "+0.5 m  (y = 1.95)"),   # fire centre y=1.45 + 0.5
    (2.45, "+1.0 m  (y = 2.45)"),   # fire centre y=1.45 + 1.0
]
WIN     = (550.0, 600.0)            # quasi-steady fire phase (fire starts t=300)
Z_PLOT  = np.linspace(0.0, 3.0, 31)

MESHES = [
    ("w_M1", "M1  (130×100×30 = 390 k)",  "#e74c3c"),
    ("w_M3", "M3  (130×100×30 = 390 k)",  "#2980b9"),
    ("w_M5", "M5  (156×120×36 = 674 k)",  "#27ae60"),
]


def load_T_z(case_dir: str, y_target: float):
    """
    Load YZ TEMPERATURE slice nearest to SLICE_X,
    time-average over WIN, return T interpolated onto Z_PLOT.
    Returns None if data doesn't reach WIN[0].
    """
    p = RES / case_dir
    sim = fdsreader.Simulation(str(p))

    # find best YZ TEMPERATURE slice
    cands = [
        (abs(s.extent.x_start - SLICE_X), s)
        for s in sim.slices
        if s.orientation == 1 and "TEMP" in s.quantity.name.upper()
    ]
    if not cands:
        print(f"  {case_dir}: no YZ TEMPERATURE slice found")
        return None
    sl = min(cands, key=lambda t: t[0])[1]

    t_arr = sl.times
    t_max = t_arr.max()
    if t_max < WIN[0]:
        print(f"  {case_dir}: t_max={t_max:.1f} s < {WIN[0]:.0f} s  (not yet ready)")
        return None

    t_end = min(t_max, WIN[1])
    win   = (t_arr >= WIN[0]) & (t_arr <= t_end)
    if not win.any():
        print(f"  {case_dir}: no timesteps in window {WIN[0]}-{t_end:.1f} s")
        return None
    print(f"  {case_dir}: t_max={t_max:.1f} s,  avg {WIN[0]:.0f}–{t_end:.1f} s  ({win.sum()} frames)")

    T = sl.to_global(masked=True, fill=np.nan)   # shape (t, y, z)
    ext   = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T.shape[2])

    iy    = int(np.argmin(np.abs(y_arr - y_target)))
    T_avg = np.nanmean(T[win, iy, :], axis=0)
    return np.interp(Z_PLOT, z_arr, T_avg)


def load_ref(p: Path):
    z, T = [], []
    for ln in p.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def main():
    # ── reference data ────────────────────────────────────────────────────
    z_ref1, T_ref1 = load_ref(REF_M1)
    z_ref5, T_ref5 = load_ref(REF_M5)

    # ── collect simulation data ───────────────────────────────────────────
    data: dict[str, dict] = {}   # label → {color, T_by_offset}
    for case_dir, label, color in MESHES:
        data[label] = {"color": color, "T": {}}
        for y_target, off_lbl in OFFSETS:
            T = load_T_z(case_dir, y_target)
            data[label]["T"][off_lbl] = T

    # ── plot ──────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), sharex=True)
    fig.suptitle(
        "Grid convergence — T(z) at fire centerline\n"
        f"Current geometry (fire 7.955–8.845, center y=1.45),  "
        f"YZ SLCF @ x={SLICE_X:.1f} m,  "
        f"averaged t = {WIN[0]:.0f}–{WIN[1]:.0f} s",
        fontsize=10,
    )

    for ax, (_, off_lbl) in zip(axes, OFFSETS):
        ax.axvline(1.0, color="lightgray", lw=1.0, ls=":", zorder=0)
        ax.axvline(2.0, color="lightgray", lw=1.0, ls=":", zorder=0)

        # reference lines
        ax.plot(z_ref1, T_ref1, "k:o",  lw=1.8, ms=5, mfc="none",
                label="Paper ref_Mesh1", zorder=9)
        ax.plot(z_ref5, T_ref5, "k--x", lw=2.0, ms=6,
                label="Paper ref_Mesh5", zorder=10)

        # simulation results
        for label, d in data.items():
            T = d["T"].get(off_lbl)
            if T is None:
                continue
            ax.plot(Z_PLOT, T, "o-", color=d["color"], label=label,
                    lw=1.8, ms=4, mfc="none")

        ax.set_xlabel("Height z (m)", fontsize=10)
        ax.set_ylabel("Temperature (°C)", fontsize=10)
        ax.set_xlim(0, 3.2)
        ax.set_ylim(bottom=20)
        ax.grid(alpha=0.35)
        ax.legend(fontsize=9, loc="upper left", framealpha=0.95)
        ax.set_title(off_lbl, fontsize=10)

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out_path = OUT / "grid_conv_fire800.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\nwrote → {out_path}")

    # ── console summary ────────────────────────────────────────────────────
    ref_label = list(data.keys())[-1]   # finest mesh as reference
    ref_data  = data[ref_label]

    print(f"\n{'Mesh':<35} {'Offset':<24} {'T_floor':>8} {'T_mid':>8} {'T_ceil':>8} {'|Δ|_M5':>8}")
    print("-" * 95)
    for label, d in data.items():
        for _, off_lbl in OFFSETS:
            T = d["T"].get(off_lbl)
            T_ref = ref_data["T"].get(off_lbl)
            if T is None:
                print(f"  {label:<33} {off_lbl:<24}  (no data)")
                continue
            err = float(np.nanmean(np.abs(T - T_ref))) if T_ref is not None else float("nan")
            iz_mid  = len(Z_PLOT) // 2
            print(f"  {label:<33} {off_lbl:<24} "
                  f"{T[0]:>8.1f} {T[iz_mid]:>8.1f} {T[-1]:>8.1f} {err:>8.2f}")


if __name__ == "__main__":
    main()
