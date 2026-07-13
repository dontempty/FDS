#!/usr/bin/env python3
"""
e_M1..e_M6 grid convergence — T(z) profiles.

Outputs two sets of 15 PNGs (per dy offset):
  M_123456_instant/ : instantaneous T(z) at t=300 s
  M_123456_average/ : T(z) averaged over t=[200, 300] s
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

plt.rcParams.update({
    "axes.labelsize": 16,   # x, y축 제목 크기
    "axes.titlesize": 18,   # plot title 크기
    "xtick.labelsize": 13,  # x축 tick 숫자 크기
    "ytick.labelsize": 13,  # y축 tick 숫자 크기
    "legend.fontsize": 11,  # legend 크기
})

ROOT   = Path("/scratch/x3319a05/fds/Engine_Room")
RES    = ROOT / "Results"
INPUTS = ROOT / "inputs"
GC     = ROOT / "analysis" / "grid_conv"
OUT_I = GC / "M_123456_instant"
OUT_A = GC / "M_123456_average"
OUT_I.mkdir(parents=True, exist_ok=True)
OUT_A.mkdir(parents=True, exist_ok=True)

REF_M1 = GC / "ref_Mesh1.csv"
REF_M5 = GC / "ref_Mesh5.csv"

SLICE_X       = 8.1
FIRE_CENTER_Y = 1.45
DY_VALUES     = np.round(np.arange(15) * 0.1, 1)
Z_PLOT        = np.linspace(0.0, 3.0, 61)

T_INSTANT = 300.0
WIN_AVG   = (250.0, 300.0)

MESHES = [
    ("e_M1", "#e74c3c", "M1", 1.2),
    ("e_M2", "#e67e22", "M2", 1.3),
    ("e_M3", "#f39c12", "M3", 1.4),
    ("e_M4", "#27ae60", "M4", 1.6),
    ("e_M5", "#2980b9", "M5", 1.8),
    ("e_M6", "#8e44ad", "M6", 2.0),
]


import re

def count_cells(case: str):
    """Total grid cells for a case = sum over &MESH of IJK product, each tiled
    by its &MULT (I/J/K_LOWER..UPPER copies). Parsed from inputs/<case>.fds."""
    f = INPUTS / f"{case}.fds"
    if not f.exists():
        return None
    txt = f.read_text()
    mult = {}
    for m in re.finditer(r"&MULT\b([^/]*)/", txt, re.I | re.S):
        body = m.group(1)
        idm = re.search(r"ID\s*=\s*'([^']*)'", body, re.I)
        if not idm:
            continue
        def span(key):
            lo = re.search(rf"{key}_LOWER\s*=\s*(-?\d+)", body, re.I)
            hi = re.search(rf"{key}_UPPER\s*=\s*(-?\d+)", body, re.I)
            return (int(hi.group(1)) if hi else 0) - (int(lo.group(1)) if lo else 0) + 1
        mult[idm.group(1)] = span("I") * span("J") * span("K")
    total = 0
    for m in re.finditer(r"&MESH\b([^/]*)/", txt, re.I | re.S):
        body = m.group(1)
        ijk = re.search(r"IJK\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", body, re.I)
        if not ijk:
            continue
        cells = int(ijk.group(1)) * int(ijk.group(2)) * int(ijk.group(3))
        idm = re.search(r"MULT_ID\s*=\s*'([^']*)'", body, re.I)
        total += cells * (mult.get(idm.group(1), 1) if idm else 1)
    return total or None

def fmt_cells(n):
    if n is None:
        return ""
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return str(n)

# Legend label with grid-cell count next to the mesh name, e.g. "M1 (39k)".
LABELS = {
    case: (f"{lbl} ({fmt_cells(n)})" if (n := count_cells(case)) else lbl)
    for case, _c, lbl, _lw in MESHES
}


def load_ref(p: Path):
    z, T = [], []
    for ln in p.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


_sim_cache: dict = {}
def load_sim(case: str):
    if case in _sim_cache:
        return _sim_cache[case]
    p = RES / case
    if not (p / f"{case}.smv").exists():
        _sim_cache[case] = None; return None
    try:
        sim = fdsreader.Simulation(str(p))
    except Exception as e:
        print(f"  {case}: {e}"); sim = None
    _sim_cache[case] = sim
    return sim


def find_yz_temp(sim):
    cands = [(abs(s.extent.x_start - SLICE_X), s)
             for s in sim.slices
             if s.orientation == 1 and "TEMP" in s.quantity.name.upper()]
    return min(cands, key=lambda t: t[0])[1] if cands else None


def get_T_instant(sim, y_target, t_target=300.0):
    sl = find_yz_temp(sim)
    if sl is None:
        return None, "no slice"
    t_arr = sl.times
    idx   = int(np.argmin(np.abs(t_arr - t_target)))
    t_hit = t_arr[idx]
    T_all = sl.to_global(masked=True, fill=np.nan)
    ext   = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])
    iy    = int(np.argmin(np.abs(y_arr - y_target)))
    T_z   = T_all[idx, iy, :]
    return np.interp(Z_PLOT, z_arr, T_z), f"t={t_hit:.1f}s"


def get_T_avg(sim, y_target, win=(200.0, 300.0)):
    sl = find_yz_temp(sim)
    if sl is None:
        return None, "no slice"
    t_arr = sl.times
    t_max = float(t_arr.max())
    t0, t1 = win[0], min(win[1], t_max)
    mask  = (t_arr >= t0) & (t_arr <= t1)
    if not mask.any():
        mask = np.array([np.argmax(t_arr)])
    T_all = sl.to_global(masked=True, fill=np.nan)
    ext   = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])
    iy    = int(np.argmin(np.abs(y_arr - y_target)))
    T_avg = np.nanmean(T_all[mask, iy, :], axis=0)
    return np.interp(Z_PLOT, z_arr, T_avg), f"avg {t0:.0f}–{t1:.0f}s"


def plot_dy(dy: float, idx: int, z1, T1, z5, T5):
    y_target = round(FIRE_CENTER_Y + dy, 3)
    tag      = f"dy{idx:02d}"

    fig_i, ax_i = plt.subplots(figsize=(7, 6))
    fig_a, ax_a = plt.subplots(figsize=(7, 6))

    for case, color, lbl, lw in MESHES:
        sim = load_sim(case)
        if sim is None:
            continue

        Ti, li = get_T_instant(sim, y_target, T_INSTANT)
        if Ti is not None:
            ax_i.plot(Z_PLOT, Ti, "-", color=color, lw=lw, label=LABELS[case])

        Ta, la = get_T_avg(sim, y_target, WIN_AVG)
        if Ta is not None:
            ax_a.plot(Z_PLOT, Ta, "-", color=color, lw=lw, label=LABELS[case])

    for ax, fig, out in [
        (ax_i, fig_i, OUT_I / f"{tag}.png"),
        (ax_a, fig_a, OUT_A / f"{tag}.png"),
    ]:
        ax.set_xlabel("Height z (m)")
        ax.set_ylabel("Temperature (°C)")
        ax.set_xlim(0, 3)
        ax.set_ylim(bottom=20)
        ax.grid(alpha=0.3)
        ax.axvline(1.0, color="lightgray", lw=1.0, ls=":", zorder=0)
        ax.axvline(2.0, color="lightgray", lw=1.0, ls=":", zorder=0)
        ax.legend(loc="upper left", framealpha=0.95)
        fig.tight_layout()
        fig.savefig(out, dpi=150)
        plt.close(fig)

    print(f"  [{idx:02d}] Δy={dy:.1f}  → {tag}.png (instant + average)")


def main():
    print("Loading simulations...")
    for case, *_ in MESHES:
        print(f"  {case} ...", end=" ", flush=True)
        s = load_sim(case)
        print("ok" if s else "SKIP")

    print("Loading paper references...")
    z1, T1 = load_ref(REF_M1)
    z5, T5 = load_ref(REF_M5)

    print(f"\nPlotting {len(DY_VALUES)} dy offsets ...")
    for idx, dy in enumerate(DY_VALUES):
        plot_dy(dy, idx, z1, T1, z5, T5)

    print(f"\nDone.")
    print(f"  instant → {OUT_I}")
    print(f"  average → {OUT_A}")


if __name__ == "__main__":
    main()
