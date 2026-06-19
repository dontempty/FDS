#!/usr/bin/env python3
"""
Cold vs Warm start — grid convergence comparison.

Cold (d_M*): fire from t=0, averaged t=250–300 s  (fire age ~250–300 s)
Warm (w_M*): fire from t=300, averaged t=550–600 s (fire age ~250–300 s)

For each dy-offset: one PNG with both cold and warm curves per mesh.
Colour = mesh resolution,  linestyle = solid(warm) / dashed(cold).

Output: analysis/grid_conv/cw/dy00.png .. dy14.png
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
OUT    = ROOT / "analysis" / "grid_conv" / "cw"
OUT.mkdir(parents=True, exist_ok=True)
REF_M1 = ROOT / "analysis" / "grid_conv" / "ref_Mesh1.csv"
REF_M5 = ROOT / "analysis" / "grid_conv" / "ref_Mesh5.csv"

SLICE_X = 8.1
Z_PLOT  = np.linspace(0.0, 3.0, 61)

FIRE_CENTER_Y = 1.45
DY_VALUES     = np.round(np.arange(15) * 0.1, 1)

WIN_COLD = (250.0, 300.0)   # d_M* : fire age 250–300 s
WIN_WARM = (550.0, 600.0)   # w_M* : fire age 250–300 s (fire started t=300)

MESHES = [
    ("M1", "#e74c3c"),
    ("M3", "#2980b9"),
    ("M5", "#27ae60"),
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


_sim_cache = {}
def load_sim(case_dir: str):
    if case_dir in _sim_cache:
        return _sim_cache[case_dir]
    p = RES / case_dir
    if not (p / f"{case_dir}.smv").exists():
        _sim_cache[case_dir] = None
        return None
    try:
        sim = fdsreader.Simulation(str(p))
    except Exception as e:
        print(f"  {case_dir}: {e}")
        sim = None
    _sim_cache[case_dir] = sim
    return sim


def get_T_z(sim, y_target: float, win: tuple):
    cands = [
        (abs(s.extent.x_start - SLICE_X), s)
        for s in sim.slices
        if s.orientation == 1 and "TEMP" in s.quantity.name.upper()
    ]
    if not cands:
        return None, "no slice"
    sl    = min(cands, key=lambda t: t[0])[1]
    t_arr = sl.times
    t_max = float(t_arr.max())

    t0 = win[0] if t_max >= win[0] else max(t_max - 50.0, t_max * 0.8)
    t1 = min(win[1], t_max)
    mask = (t_arr >= t0) & (t_arr <= t1)
    if not mask.any():
        mask = np.array([t_arr.argmax()])

    T_all = sl.to_global(masked=True, fill=np.nan)
    ext   = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])
    iy    = int(np.argmin(np.abs(y_arr - y_target)))
    T_avg = np.nanmean(T_all[mask, iy, :], axis=0)

    lbl = f"avg {t0:.0f}–{t1:.0f}s" if t_max >= win[0] else f"t={t_max:.0f}s*"
    return np.interp(Z_PLOT, z_arr, T_avg), lbl


def plot_one_dy(dy: float, idx: int, z_ref1, T_ref1, z_ref5, T_ref5):
    y_target = round(FIRE_CENTER_Y + dy, 3)
    tag      = f"dy{idx:02d}"
    out_path = OUT / f"{tag}.png"

    fig, ax = plt.subplots(figsize=(7, 6))

    # paper references
    ax.plot(z_ref1, T_ref1, "k:o",  lw=1.4, ms=4, mfc="none",
            label="Paper ref_Mesh1", zorder=9)
    ax.plot(z_ref5, T_ref5, "k--x", lw=1.6, ms=5,
            label="Paper ref_Mesh5", zorder=10)

    for name, color in MESHES:
        # warm (solid)
        sim_w = load_sim(f"w_{name}")
        if sim_w:
            T, lbl = get_T_z(sim_w, y_target, WIN_WARM)
            if T is not None:
                ax.plot(Z_PLOT, T, "-",  color=color, lw=2.0,
                        label=f"{name} warm [{lbl}]")

        # cold (dashed)
        sim_d = load_sim(f"d_{name}")
        if sim_d:
            T, lbl = get_T_z(sim_d, y_target, WIN_COLD)
            if T is not None:
                ax.plot(Z_PLOT, T, "--", color=color, lw=1.6,
                        label=f"{name} cold [{lbl}]")

    ax.set_xlabel("Height z (m)", fontsize=11)
    ax.set_ylabel("Temperature (°C)", fontsize=11)
    ax.set_xlim(0, 3.2)
    ax.set_ylim(bottom=20)
    ax.grid(alpha=0.3)
    ax.axvline(1.0, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.axvline(2.0, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.legend(fontsize=8, loc="upper left", framealpha=0.95)
    ax.set_title(
        f"Cold vs Warm start — T(z)   Δy={dy:.1f} m  (y={y_target:.2f} m)\n"
        f"solid=warm(w_M*, 550–600s)   dashed=cold(d_M*, 250–300s)\n"
        f"YZ SLCF @ x≈{SLICE_X:.1f} m",
        fontsize=9,
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  [{idx:02d}] Δy={dy:.1f}  → {tag}.png")


def main():
    print("Loading simulations...")
    for name, _ in MESHES:
        for prefix in ("w_", "d_"):
            cid = f"{prefix}{name}"
            print(f"  {cid} ...", end=" ", flush=True)
            print("ok" if load_sim(cid) else "SKIP")

    print("Loading paper references...")
    z_ref1, T_ref1 = load_ref(REF_M1)
    z_ref5, T_ref5 = load_ref(REF_M5)

    print(f"\nPlotting {len(DY_VALUES)} y-offsets → {OUT}")
    for idx, dy in enumerate(DY_VALUES):
        plot_one_dy(dy, idx, z_ref1, T_ref1, z_ref5, T_ref5)

    print(f"\nDone. {len(DY_VALUES)} PNGs in {OUT}")


if __name__ == "__main__":
    main()
