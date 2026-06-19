#!/usr/bin/env python3
"""
Grid convergence T(z) — one PNG per y-offset (dy00..dy14).
Style matches grid_conv_fire800.png.

Fire centre : x=8.4, y=1.45
dy range    : 0.0, 0.1, ..., 1.4 m  → y_target = 1.45 + dy
SLCF used   : YZ plane nearest to x=8.13 (ori=1)
Time window : 550–600 s  (quasi-steady fire, uses available range if < 550 s)
Output      : analysis/grid_conv/dy/dy00.png .. dy14.png
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT   = Path("/scratch/x3319a05/fds/Engine_Room")
RES    = ROOT / "Results"
OUT    = ROOT / "analysis" / "grid_conv" / "dy"
OUT.mkdir(parents=True, exist_ok=True)
REF_M1 = ROOT / "analysis" / "grid_conv" / "ref_Mesh1.csv"
REF_M5 = ROOT / "analysis" / "grid_conv" / "ref_Mesh5.csv"

SLICE_X    = 8.1          # closest available YZ slice (x=8.13)
WIN        = (500.0, 600.0)
Z_PLOT     = np.linspace(0.0, 3.0, 61)

FIRE_CENTER_Y = 1.45
DY_VALUES     = np.round(np.arange(0, 15) * 0.1, 1)   # 0.0 .. 1.4

MESHES = [
    ("w_M1", "M1  (130×100×30 = 390 k)", "#e74c3c"),
    ("w_M3", "M3  (130×100×30 = 390 k)", "#2980b9"),
    ("w_M5", "M5  (156×120×36 = 674 k)", "#27ae60"),
]


def load_ref(p: Path):
    z, T = [], []
    for ln in p.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def load_sim(case_dir: str):
    """Load fdsreader Simulation; cache per case_dir."""
    p = RES / case_dir
    if not (p / f"{case_dir}.smv").exists():
        return None
    try:
        return fdsreader.Simulation(str(p))
    except Exception as e:
        print(f"  {case_dir}: load error {e}")
        return None


def get_T_z(sim, y_target: float):
    """
    From the YZ TEMPERATURE slice nearest SLICE_X, time-average over WIN
    (or available range if sim hasn't reached WIN[0]), return T on Z_PLOT.
    Returns (T_array, t_label_str) or (None, reason_str).
    """
    cands = [
        (abs(s.extent.x_start - SLICE_X), s)
        for s in sim.slices
        if s.orientation == 1 and "TEMP" in s.quantity.name.upper()
    ]
    if not cands:
        return None, "no YZ TEMP slice"

    sl    = min(cands, key=lambda t: t[0])[1]
    t_arr = sl.times
    t_max = float(t_arr.max())

    # use what's available: at minimum the last 50 s of the run
    t0 = min(WIN[0], max(t_max - 50.0, t_max * 0.8))
    t1 = t_max
    win = (t_arr >= t0) & (t_arr <= t1)
    if not win.any():
        win = np.array([t_arr.argmax()])   # fallback: last frame

    T_all = sl.to_global(masked=True, fill=np.nan)
    ext   = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])

    iy    = int(np.argmin(np.abs(y_arr - y_target)))
    T_avg = np.nanmean(T_all[win, iy, :], axis=0)
    T_interp = np.interp(Z_PLOT, z_arr, T_avg)

    if t_max >= WIN[0]:
        lbl = f"avg {t0:.0f}–{t1:.0f} s"
    else:
        lbl = f"t={t_max:.0f} s (running)"

    return T_interp, lbl


def plot_one_dy(dy: float, idx: int,
                z_ref1, T_ref1, z_ref5, T_ref5,
                sims: dict):
    y_target = round(FIRE_CENTER_Y + dy, 3)
    tag      = f"dy{idx:02d}"
    out_path = OUT / f"{tag}.png"

    fig, ax = plt.subplots(figsize=(6, 6))

    # paper references (shown only for dy00/dy05/dy10 where offsets roughly match)
    ax.plot(z_ref1, T_ref1, "k:o",  lw=1.6, ms=5, mfc="none",
            label="Paper ref_Mesh1", zorder=9)
    ax.plot(z_ref5, T_ref5, "k--x", lw=1.8, ms=6,
            label="Paper ref_Mesh5", zorder=10)

    for case_dir, label, color in MESHES:
        sim = sims.get(case_dir)
        if sim is None:
            continue
        T, t_lbl = get_T_z(sim, y_target)
        if T is None:
            continue
        ax.plot(Z_PLOT, T, "o-", color=color,
                label=f"{label}  [{t_lbl}]",
                lw=1.8, ms=3, mfc="none")

    ax.set_xlabel("Height z (m)", fontsize=11)
    ax.set_ylabel("Temperature (°C)", fontsize=11)
    ax.set_xlim(0, 3.2)
    ax.set_ylim(bottom=20)
    ax.grid(alpha=0.35)
    ax.axvline(1.0, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.axvline(2.0, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.legend(fontsize=8, loc="upper left", framealpha=0.95)
    ax.set_title(
        f"Grid convergence — T(z)\n"
        f"Δy = {dy:.1f} m  (y = {y_target:.2f} m from fire centre y={FIRE_CENTER_Y})\n"
        f"YZ SLCF @ x≈{SLICE_X:.1f} m",
        fontsize=10,
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  [{idx:02d}] Δy={dy:.1f}  y={y_target:.2f}  → {out_path.name}")


def main():
    print("Loading simulations...")
    sims = {}
    for case_dir, label, _ in MESHES:
        print(f"  {case_dir} ...", end=" ", flush=True)
        sims[case_dir] = load_sim(case_dir)
        print("ok" if sims[case_dir] else "SKIP")

    print("Loading paper references...")
    z_ref1, T_ref1 = load_ref(REF_M1)
    z_ref5, T_ref5 = load_ref(REF_M5)

    print(f"\nPlotting {len(DY_VALUES)} y-offsets → {OUT}")
    for idx, dy in enumerate(DY_VALUES):
        plot_one_dy(dy, idx, z_ref1, T_ref1, z_ref5, T_ref5, sims)

    print(f"\nDone. {len(DY_VALUES)} PNGs in {OUT}")


if __name__ == "__main__":
    main()
