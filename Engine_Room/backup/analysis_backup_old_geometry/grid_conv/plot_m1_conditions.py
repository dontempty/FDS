#!/usr/bin/env python3
"""
Compare all M1 (Mesh 1) runs under different sensitivity conditions against
the paper Fig 5 reference.  Each curve is the centre +1 m vertical T(z),
time-averaged 100→300 s.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT    = Path("/scratch/x3319a05/fds/Engine_Room")
RESULTS = ROOT / "Results"
OUT_DIR = Path(__file__).parent
REF_CSV = OUT_DIR / "ref.csv"

# Manual catalogue: (label, color, dirname).  Keep in insertion order for legend.
CASES = [
    ("baseline (orig fire 0.886², door −0.3m, κ=1.7)", "tab:blue",   "grid_mesh1_757429"),
    ("κ=1.0",                                          "tab:cyan",   "grid_mesh1_k1p0_757501"),
    ("κ=2.5",                                          "tab:purple", "grid_mesh1_k2p5_757500"),
    ("only OSR-MER wall steel",                        "tab:orange", "grid_mesh1_757980"),
    ("vent VEL signs flipped",                         "tab:red",    "grid_mesh1_758091"),
    ("+ fire 1×1, door 7.7-8.7, HRR=863",              "tab:olive",  "grid_mesh1_758145"),
    ("+ fire 1×1, door 7.7-8.7, HRR=1099",             "tab:brown",  "grid_mesh1_758147"),
    ("+ floor/ceiling EXPOSED steel",                  "tab:pink",   "grid_mesh1_758725"),
    ("+ floor/ceiling ADIABATIC",                      "tab:gray",   "grid_mesh1_758804"),
    ("+ ADIABATIC + HRR=863 (paper exact)",            "black",      "grid_mesh1_759073"),
    ("+ ADIABATIC + HRR=863 + orig vent signs",        "tab:green",  "grid_mesh1_759176"),
    ("sign-flip + INSULATED steel 0.01m (1×1 fire)",   "magenta",    "grid_mesh1_759273"),
    ("sign-flip + ADIABATIC + orig fire 0.886²",       "navy",       "grid_mesh1_759278"),
]
N_PTS = 30
Z_SIM = np.linspace(0.05, 2.95, N_PTS)


def load_ref():
    z, T = [], []
    for line in REF_CSV.read_text().splitlines():
        if not line.strip(): continue
        a, b = line.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def load_avg(d, col="gridconv_T_center_avg"):
    f = RESULTS / d / f"{d}_line.csv"
    rows = list(csv.reader(open(f)))
    hdr = [c.strip() for c in rows[1]]
    if col not in hdr: return None
    j = hdr.index(col)
    return np.array([float(rows[2+i][j]) for i in range(N_PTS)])


def main():
    ref_z, ref_T = load_ref()
    ref_at = np.interp(Z_SIM, ref_z, ref_T)

    loaded = []
    for label, color, dirname in CASES:
        vals = load_avg(dirname)
        if vals is None:
            print(f"skip {dirname}: column missing"); continue
        if np.max(vals) == 0 and np.min(vals) == 0:
            print(f"skip {dirname}: all zero"); continue
        loaded.append((label, color, vals))
        print(f"loaded {dirname}: {label}")

    if not loaded: sys.exit("no usable cases")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.5),
                                    gridspec_kw=dict(width_ratios=[3, 2]))

    # ---- left: absolute T(z)
    ax1.plot(ref_z, ref_T, "k--x", lw=2.0, ms=7,
             label="Reference (Lan 2023, Fig 5)", zorder=10)
    for label, color, vals in loaded:
        ax1.plot(Z_SIM, vals, color=color, marker="o", ms=4, mfc="none",
                 lw=1.4, label=label)
    ax1.set_xlabel("Height z (m)")
    ax1.set_ylabel("Temperature (°C, time-avg 100→300 s)")
    ax1.set_xlim(0, 3.0); ax1.set_ylim(20, 280)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8, loc="upper left", framealpha=0.95)
    ax1.set_title("M1 sensitivity — T(z) at fire centre +1 m (x=8.25, y=2.45)")

    # ---- right: deviation
    ax2.axvline(0, color="k", lw=0.8)
    for label, color, vals in loaded:
        dev = vals - ref_at
        ax2.plot(dev, Z_SIM, color=color, marker="o", ms=4, mfc="none",
                 lw=1.4, label=label.split(" (")[0])
    ax2.set_xlabel("ΔT vs paper (°C)")
    ax2.set_ylabel("Height z (m)")
    ax2.set_ylim(0, 3.0); ax2.set_xlim(-80, 30)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8, loc="lower left")
    ax2.set_title("Pointwise deviation: sim − paper")

    fig.suptitle("Mesh 1 sensitivity sweep — Method 2, v = 1 m/s, T_END = 300 s",
                 fontsize=11, y=1.00)
    out = OUT_DIR / "M1_sensitivity_sweep.png"
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)
    print(f"\nwrote {out}")

    # text summary
    print("\nMean |ΔT|:")
    mid = (Z_SIM >= 0.95) & (Z_SIM <= 2.45)
    print(f"  {'case':<48} {'overall':>9} {'mid (0.95-2.45)':>18} {'floor':>7} {'ceil':>7}")
    for label, _, vals in loaded:
        dev = vals - ref_at
        print(f"  {label[:48]:<48} {np.mean(np.abs(dev)):>9.1f} "
              f"{np.mean(np.abs(dev[mid])):>18.1f} {vals[0]:>7.1f} {vals[-1]:>7.1f}")
    print(f"  {'paper Fig 5 ref':<48} {'-':>9} {'-':>18} {ref_at[0]:>7.1f} {ref_at[-1]:>7.1f}")


if __name__ == "__main__":
    main()
