#!/usr/bin/env python3
"""
Δy temperature-profile overlay — based on plot_e_convergence.py.

Instead of "one dy offset, many meshes", this plots for each case a SINGLE figure
holding MANY Δy offsets: T(z) sampled on the YZ temperature slice at x=8.1 (fire
flank), at y = fire_centre_y + Δy for Δy = 0.0 … 1.4 m (moving away from the fire
centreline toward the OSR/MER divider).  Curves are coloured by Δy (viridis + colorbar).

Two case series (kept separate, like Analysis/flame|visualize):
    peak : peak{05,10,15,20}_M5        (0.79 m^2 fire)
    fire1: peak{05,10,15,20}_fire1_M5  (1.0  m^2 fire)

Output: Analysis/convergence/<series>/<case>_dy_avg.png  (T averaged 300-360 s)
        Analysis/convergence/<series>/<series>_dy_panel.png  (2x2 overview)
Run:    /shared/home/wel1come1234/miniconda3/bin/python3 plot_dy_profiles.py [peak|fire1|both]
"""
from __future__ import annotations
import sys, warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
import fdsreader

plt.rcParams.update({"axes.labelsize": 15, "axes.titlesize": 15,
                     "xtick.labelsize": 12, "ytick.labelsize": 12,
                     "legend.fontsize": 9})

ROOT = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom")
RES  = ROOT / "Results"
CONV = ROOT / "Analysis" / "convergence"

REF_M1 = CONV / "ref_Mesh1.csv"    # paper grid-conv T(z), coarse mesh
REF_M5 = CONV / "ref_Mesh5.csv"    # paper grid-conv T(z), fine mesh

SLICE_X       = 8.1
FIRE_CENTER_Y = 1.45
DY_VALUES     = np.round(np.arange(15) * 0.1, 1)   # 0.0 … 1.4 m
Z_PLOT        = np.linspace(0.0, 3.0, 61)
# series -> dict(tag, win, cases=[(case_dir, subplot_label), ...])
SERIES = {
    "peak":  dict(tag="0.79 m^2 fire", win=(0.0, 360.0),
                  cases=[(f"peak{tp:02d}_M5", f"HRR peak @{tp} s") for tp in (5,10,15,20)]),
    "fire1": dict(tag="1.0 m^2 fire", win=(0.0, 360.0),
                  cases=[(f"peak{tp:02d}_fire1_M5", f"HRR peak @{tp} s") for tp in (5,10,15,20)]),
    "fire1_vent": dict(tag="1.0 m^2 fire, HRR peak 10 s", win=(0.0, 300.0),
                       cases=[(f"fire1_p10_v{v}_M5", f"vent @{v} s") for v in (20,30,40)]),
}
CMAP = plt.cm.viridis
NORM = Normalize(vmin=DY_VALUES.min(), vmax=DY_VALUES.max())


def load_ref(p):
    if not p.exists():
        return None, None
    z, T = [], []
    for ln in p.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def plot_refs(ax, refs, legend=True):
    (z1, T1), (z5, T5) = refs
    if z1 is not None:
        ax.plot(z1, T1, "k--s", lw=1.6, ms=4, mfc="none", label="Ref Mesh1 (paper)")
    if z5 is not None:
        ax.plot(z5, T5, "k-o", lw=1.6, ms=4, mfc="none", label="Ref Mesh5 (paper)")
    if legend and (z1 is not None or z5 is not None):
        ax.legend(loc="upper right", framealpha=0.95)


def load_sim(case):
    p = RES / case
    if not (p / f"{case}.smv").exists():
        print(f"  {case}: .smv missing — skip"); return None
    try:
        return fdsreader.Simulation(str(p))
    except Exception as e:
        print(f"  {case}: {e}"); return None


def find_yz_temp(sim):
    cands = [(abs(s.extent.x_start - SLICE_X), s) for s in sim.slices
             if s.orientation == 1 and "TEMP" in s.quantity.name.upper()]
    return min(cands, key=lambda t: t[0])[1] if cands else None


def T_avg_profiles(sim, win=(0.0, 360.0)):
    """Return dict Δy -> T(Z_PLOT) averaged over the window at y=centre+Δy."""
    sl = find_yz_temp(sim)
    if sl is None:
        return None
    t_arr = np.asarray(sl.times)
    t0, t1 = win[0], min(win[1], float(t_arr.max()))
    mask = (t_arr >= t0) & (t_arr <= t1)
    if not mask.any():
        mask = np.array([int(np.argmax(t_arr))])
    T_all = sl.to_global(masked=True, fill=np.nan)      # (t, y, z)
    ext   = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])
    out = {}
    for dy in DY_VALUES:
        iy   = int(np.argmin(np.abs(y_arr - (FIRE_CENTER_Y + dy))))
        Tavg = np.nanmean(T_all[mask, iy, :], axis=0)
        out[dy] = np.interp(Z_PLOT, z_arr, Tavg)
    return out


def style_ax(ax):
    ax.set_xlabel("Height z (m)"); ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(0, 3); ax.set_ylim(bottom=20); ax.grid(alpha=0.3)
    ax.axvline(1.0, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.axvline(2.0, color="lightgray", lw=1.0, ls=":", zorder=0)


def run_series(series):
    spec = SERIES[series]
    tag, win, cases = spec["tag"], spec["win"], spec["cases"]
    OUT = CONV / series; OUT.mkdir(parents=True, exist_ok=True)
    print(f"=== series '{series}' ({tag}) -> {OUT} ===")

    refs = (load_ref(REF_M1), load_ref(REF_M5))

    ncase = len(cases)
    ncol = 2; nrow = (ncase + ncol - 1) // ncol
    panel_fig, panel_axs = plt.subplots(nrow, ncol, figsize=(13, 5.5 * nrow))
    panel_axs = np.atleast_1d(panel_axs).ravel()

    for k, (case, sub_lbl) in enumerate(cases):
        sim = load_sim(case)
        if sim is None:
            continue
        profiles = T_avg_profiles(sim, win)
        if profiles is None:
            print(f"  {case}: no YZ temp slice"); continue

        # ---- individual per-case figure ----
        fig, ax = plt.subplots(figsize=(7.5, 6))
        for dy in DY_VALUES:
            ax.plot(Z_PLOT, profiles[dy], "-", lw=1.8, color=CMAP(NORM(dy)))
        plot_refs(ax, refs)
        style_ax(ax)
        ax.set_title(f"{case}  —  T(z) vs Δy\n"
                     f"x={SLICE_X} m, avg {win[0]:.0f}-{win[1]:.0f} s "
                     f"[{tag}]", fontsize=13)
        cb = fig.colorbar(ScalarMappable(norm=NORM, cmap=CMAP), ax=ax,
                          ticks=DY_VALUES[::2])
        cb.set_label("Δy from fire centreline (m)")
        fig.tight_layout()
        f_out = OUT / f"{case}_dy_avg.png"
        fig.savefig(f_out, dpi=150); plt.close(fig)
        print(f"  -> {f_out}")

        # ---- panel subplot ----
        pax = panel_axs[k]
        for dy in DY_VALUES:
            pax.plot(Z_PLOT, profiles[dy], "-", lw=1.6, color=CMAP(NORM(dy)))
        plot_refs(pax, refs, legend=(k == 0))
        style_ax(pax)
        pax.set_title(sub_lbl, fontsize=13)

    for j in range(ncase, len(panel_axs)):   # hide unused subplots
        panel_axs[j].axis("off")

    panel_fig.suptitle(
        f"Engine-room T(z) vs Δy offset  [{series}: {tag}]  "
        f"(x={SLICE_X} m, avg {win[0]:.0f}-{win[1]:.0f} s)", fontsize=15)
    panel_fig.tight_layout(rect=(0, 0, 0.92, 0.97))
    cax = panel_fig.add_axes([0.94, 0.12, 0.015, 0.76])
    cb = panel_fig.colorbar(ScalarMappable(norm=NORM, cmap=CMAP), cax=cax,
                            ticks=DY_VALUES[::2])
    cb.set_label("Δy from fire centreline (m)")
    p_out = OUT / f"{series}_dy_panel.png"
    panel_fig.savefig(p_out, dpi=150); plt.close(panel_fig)
    print(f"  -> {p_out}")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    todo = list(SERIES) if which == "both" else [which]
    for s in todo:
        if s not in SERIES:
            sys.exit(f"series must be peak|fire1|both")
        run_series(s)


if __name__ == "__main__":
    main()
