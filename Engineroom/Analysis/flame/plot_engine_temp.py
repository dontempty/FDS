#!/usr/bin/env python3
"""
Temperature profile above main engine (x=6.75, y≈7.08, z=[2.0, 3.0]).

Uses XZ SLCF at y=7.08  (ori=2) — slices through main engine centre in y.
Extracts T(z) at x closest to 6.75 (main engine centre x).
Average over t=[250, 300] s.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging;  logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES  = ROOT / "Results"
OUT  = ROOT / "analysis" / "flame"

CASE     = "e_M5"
X_ENG    = 6.75    # main engine centre x
Y_TARGET = 7.1     # main engine centre y
Z_LO     = 2.0     # engine top
Z_HI     = 3.0     # ceiling
WIN      = (250.0, 300.0)

plt.rcParams.update({
    "axes.labelsize": 16,   # x, y축 제목 크기
    "axes.titlesize": 18,   # plot title 크기
    "xtick.labelsize": 13,  # x축 tick 숫자 크기
    "ytick.labelsize": 13,  # y축 tick 숫자 크기
    "legend.fontsize": 16,  # legend 크기
})



def main():
    sim = fdsreader.Simulation(str(RES / CASE))

    # PBY=7.08 XZ slice (ori=2)
    xz_slices = [s for s in sim.slices
                 if s.orientation == 2 and "TEMP" in s.quantity.name.upper()]
    if not xz_slices:
        raise RuntimeError("No XZ temperature slice found")

    sl  = min(xz_slices, key=lambda s: abs(s.extent.y_start - Y_TARGET))
    ext = sl.extent
    print(f"Using XZ slice at y={ext.y_start:.3f} m  (target y={Y_TARGET})")

    T_all = sl.to_global(masked=True, fill=np.nan)   # (t, x, z)
    t_arr = sl.times
    x_arr = np.linspace(ext.x_start, ext.x_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])

    # x index closest to engine centre
    ix = int(np.argmin(np.abs(x_arr - X_ENG)))
    print(f"  x=6.75 closest: x_arr[{ix}]={x_arr[ix]:.3f} m")

    # z indices above engine top
    iz_lo = int(np.searchsorted(z_arr, Z_LO))
    iz_hi = int(np.searchsorted(z_arr, Z_HI, side="right")) - 1
    z_sel = z_arr[iz_lo:iz_hi + 1]

    # time average
    t0   = WIN[0]
    t1   = min(WIN[1], float(t_arr.max()))
    mask = (t_arr >= t0) & (t_arr <= t1)
    if not mask.any():
        mask = np.array([np.argmax(t_arr)])

    T_win = T_all[np.ix_(mask, [ix], np.arange(iz_lo, iz_hi + 1))]
    T_avg = np.nanmean(T_win, axis=0)[0]
    T_std = np.nanstd( T_win, axis=0)[0]

    print(f"  z range: [{z_sel[0]:.2f}, {z_sel[-1]:.2f}] m  ({len(z_sel)} points)")
    print(f"  T range: {np.nanmin(T_avg):.1f} – {np.nanmax(T_avg):.1f} °C  "
          f"(avg {t0:.0f}–{t1:.0f}s,  std_max={np.nanmax(T_std):.2f})")

    # reference
    ref_path = OUT / "engine_ref.csv"
    ref_data = np.loadtxt(ref_path, delimiter=",") if ref_path.exists() else None

    # plot
    fig, ax = plt.subplots(figsize=(6, 5))

    ax.errorbar(z_sel, T_avg, yerr=T_std,
                fmt="-o", color="#2980b9", lw=1.8, ms=5,
                elinewidth=0.8, capsize=3, capthick=0.8,
                label="M5",
                zorder=3)

    if ref_data is not None:
        ax.plot(ref_data[:, 1], ref_data[:, 0], "k-s", lw=1.5, ms=5,
                mfc="none", label="Reference", zorder=5)

    ax.set_xlabel("z  (m)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(Z_LO, Z_HI)
    ax.set_ylim(40, 130)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", framealpha=0.95)

    fig.tight_layout()
    out = OUT / "engine_temp_profile.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
