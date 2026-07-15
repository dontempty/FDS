#!/usr/bin/env python3
"""
Engine-footprint x,y-AREA-averaged vertical temperature profile T̄(z,t)
from the `engTz_*` VOLUME MEAN DEVCs (fire1_p10_v{20,30,40}_tz_M5).

Unlike plot_engine_temp.ipynb (which averages along a single slice line), each
engTz_kk device is the true x,y area-average of TEMPERATURE over the whole main-
engine footprint at one z-cell (SPATIAL_STATISTIC='VOLUME MEAN' on the 3D field).
Reads the DEVC .csv directly (cheap scalars, no 3D dump).  Works on partial CSV.
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ENG = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom")
INP = ENG / "Inputs" / "scenario"
RES = ENG / "Results"
OUT = ENG / "Analysis" / "flame" / "engine_tz_slice"
OUT.mkdir(parents=True, exist_ok=True)

CASES = {
    "fire1_p10_v20_tz_M5": ("vent @20 s", "#2980b9", 20),
    "fire1_p10_v30_tz_M5": ("vent @30 s", "#27ae60", 30),
    "fire1_p10_v40_tz_M5": ("vent @40 s", "#e67e22", 40),
}
WIN = (240.0, 300.0)


def zmap_from_input(chid):
    """engTz_kk -> z (m), parsed from the DEVC comments in the input .fds."""
    txt = (INP / f"{chid}.fds").read_text()
    zmap = {}
    for m in re.finditer(r"ID='(engTz_\d+)'.*?x,y-avg T at z=([\d.]+)", txt):
        zmap[m.group(1)] = float(m.group(2))
    return zmap


def read_devc(chid):
    """Return (t, z_sorted, T[z,t]) from the engTz columns of the DEVC csv."""
    csv = RES / chid / f"{chid}_devc.csv"
    if not csv.exists():
        return None
    names = csv.read_text().splitlines()[1].replace('"', '').split(",")  # row 2 = IDs
    names = [n.strip() for n in names]
    data = np.genfromtxt(csv, delimiter=",", skip_header=2)
    if data.ndim == 1:
        data = data[None, :]
    t = data[:, 0]
    zmap = zmap_from_input(chid)
    cols = [(zmap[n], i) for i, n in enumerate(names) if n in zmap]
    cols.sort()                                   # sort by z
    z = np.array([c[0] for c in cols])
    T = np.array([data[:, i] for _, i in cols])   # (z, t)
    return t, z, T


def main():
    loaded = {}
    for chid, (lbl, col, v) in CASES.items():
        r = read_devc(chid)
        if r is None:
            print(f"{chid}: no devc csv yet"); continue
        t, z, T = r
        loaded[chid] = (lbl, col, v, t, z, T)
        print(f"{chid}: {len(z)} z-levels ({z[0]:.2f}-{z[-1]:.2f} m), "
              f"t=[{t[0]:.0f},{t[-1]:.0f}] s ({len(t)} rows)")
    if not loaded:
        print("no data yet"); return

    # ---- heatmap T(z,t) per case ----
    n = len(loaded)
    fig, axs = plt.subplots(1, n, figsize=(6*n, 4.6), squeeze=False)
    vmax = max(np.nanmax(T) for *_, T in (v[3:] for v in loaded.values()))
    for ax, (chid, (lbl, col, v, t, z, T)) in zip(axs[0], loaded.items()):
        pc = ax.pcolormesh(t, z, T, shading="auto", cmap="jet", vmin=20, vmax=vmax)
        ax.axvline(v, color="w", ls=":", lw=1)          # vent start
        ax.set_xlabel("Time (s)"); ax.set_ylabel("z (m)")
        ax.set_title(f"{lbl}  (engine x,y-area avg)")
        fig.colorbar(pc, ax=ax, label="T (deg C)")
    fig.suptitle("Engine-footprint x,y-area-averaged T(z,t)  [VOLUME MEAN DEVC]",
                 fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT / "engine_Tz_AREAavg_heatmap.png", dpi=150)
    print("->", OUT / "engine_Tz_AREAavg_heatmap.png")

    # ---- steady-state profile (if WIN reached) + reference ----
    ref_p = ENG / "Analysis" / "flame" / "engine_ref.csv"
    ref = np.loadtxt(ref_p, delimiter=",") if ref_p.exists() else None
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for chid, (lbl, col, v, t, z, T) in loaded.items():
        w = (t >= WIN[0]) & (t <= WIN[1])
        if not w.any():                                  # not steady yet → last frame
            w = np.array([len(t)-1])
            note = f" (t={t[-1]:.0f}s)"
        else:
            note = ""
        ax.plot(z, np.nanmean(T[:, w], axis=1), "-o", color=col, ms=5,
                label=lbl + note)
    if ref is not None:
        ax.plot(ref[:, 1], ref[:, 0], "k-s", lw=1.5, ms=4, mfc="none",
                label="Reference")
    ax.set_xlabel("z (m)"); ax.set_ylabel("Temperature (deg C)")
    ax.grid(alpha=0.3); ax.legend(title="vent start")
    ax.set_title("Engine-footprint x,y-area-averaged steady T(z)")
    fig.tight_layout()
    fig.savefig(OUT / "engine_Tz_AREAavg_profile.png", dpi=150)
    print("->", OUT / "engine_Tz_AREAavg_profile.png")


if __name__ == "__main__":
    main()
