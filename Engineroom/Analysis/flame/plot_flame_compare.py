#!/usr/bin/env python3
"""
Flame-metric + engine-top temperature comparison for one case series.

Reuses the logic of plot_fig9_10_compare.ipynb and plot_engine_temp_compare.ipynb
but parametrised by SERIES so the two fire-size studies stay separated:

    python3 plot_flame_compare.py peak     # 0.79 m2 fire  -> Analysis/flame/peak/
    python3 plot_flame_compare.py fire1    # 1.0  m2 fire  -> Analysis/flame/fire1/

Both series share the same HRR peak-time sweep (5/10/15/20 s), vents on from t=0.
Outputs (per series subdir): cmp_fig9_Ly.png, cmp_fig10_1_Hf.png,
cmp_fig10_2_thetaz.png, cmp_fig9_10_panel.png, engine_temp_profile_compare.png.
Reference CSVs (Fig9/Fig10_1/Fig10_2/engine_ref) are read from the flame/ top level.
"""
from __future__ import annotations
import sys, warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import fdsreader

plt.rcParams.update({"axes.labelsize": 14, "axes.titlesize": 15,
                     "xtick.labelsize": 11, "ytick.labelsize": 11,
                     "legend.fontsize": 11})

RES = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom/Results")
FLAME = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom/Analysis/flame")

# series -> (dir suffix template, human tag)
SERIES = {
    "peak":  ("peak{tp:02d}_M5",       "0.79 m^2 fire"),
    "fire1": ("peak{tp:02d}_fire1_M5", "1.0 m^2 fire"),
}
PEAK_TIMES = [5, 10, 15, 20]
COLORS = {5: "#2980b9", 10: "#27ae60", 15: "#e67e22", 20: "#8e44ad"}

TMAX    = 360.0
WIN     = (300.0, 360.0)
THRESH  = 150.0
FIRE_X  = (7.955, 8.845)   # burner-x reference for L_x centring (offset only)
FIRE_Y  = (1.005, 1.895)   # mesh y-band that always contains the fire
HF_FRAC = 0.99
BLOCK   = 30
REF_FILES = {"Ly": "Fig9.csv", "Hf": "Fig10_1.csv", "theta": "Fig10_2.csv"}

# engine-top profile
X_ENG, Y_TARGET, Z_LO, Z_HI = 6.75, 7.1, 2.0, 3.0
REF_CSV = "engine_ref.csv"


def block_mean(t, arr, n):
    t = np.asarray(t, float); arr = np.asarray(arr, float)
    nb = len(arr) // n
    if nb == 0:
        return np.array([np.nanmean(t)]), np.array([np.nanmean(arr)])
    tt = t[:nb*n].reshape(nb, n); aa = arr[:nb*n].reshape(nb, n)
    return np.nanmean(tt, axis=1), np.nanmean(aa, axis=1)


def flame_metrics(sim):
    s3 = [s for s in sim.smoke_3d if "HRRPUV" in s.quantity.name.upper()][0]
    t  = np.array(s3.times)
    sel = [m for m in sim.meshes
           if m.coordinates["y"][0] < FIRE_Y[1] and m.coordinates["y"][-1] > FIRE_Y[0]]
    x_arr = np.unique(np.concatenate([m.coordinates["x"] for m in sel]))
    y_arr = np.unique(np.concatenate([m.coordinates["y"] for m in sel]))
    z_arr = np.unique(np.concatenate([m.coordinates["z"] for m in sel]))
    dz    = float(np.diff(z_arr).mean())
    P = np.zeros((len(t), len(x_arr), len(y_arr)))
    B = np.zeros((len(t), len(x_arr), len(z_arr)))
    for m in sel:
        d  = s3[m].data
        dy = float(np.diff(m.coordinates["y"]).mean())
        pm = d.max(axis=3); qy = d.sum(axis=2) * dy
        ixg = np.clip(np.searchsorted(x_arr, m.coordinates["x"]), 0, len(x_arr)-1)
        iyg = np.clip(np.searchsorted(y_arr, m.coordinates["y"]), 0, len(y_arr)-1)
        izg = np.clip(np.searchsorted(z_arr, m.coordinates["z"]), 0, len(z_arr)-1)
        for a, xg in enumerate(ixg):
            P[:, xg, iyg]  = np.maximum(P[:, xg, iyg], pm[:, a, :])
            B[:, xg, izg] += qy[:, a, :]
    XX, _   = np.meshgrid(x_arr, y_arr, indexing="ij")
    xc_burn = 0.5 * (FIRE_X[0] + FIRE_X[1])
    L_x = np.zeros(len(t)); L_y = np.zeros(len(t))
    for i in range(len(t)):
        mask = P[i] > THRESH
        if not mask.any():
            continue
        iy = np.where(mask.any(axis=0))[0]
        if len(iy) > 1:
            L_y[i] = y_arr[iy[-1]] - y_arr[iy[0]]
        w = P[i][mask]
        L_x[i] = abs((XX[mask]*w).sum()/w.sum() - xc_burn)
    A = B.sum(axis=2) * dz
    H = np.zeros(len(t))
    for i in range(len(t)):
        a = A[i]
        if a.sum() <= 0:
            continue
        xcen = (x_arr*a).sum()/a.sum()
        ix = int(np.argmin(np.abs(x_arr - xcen)))
        cum = np.cumsum(B[i, ix]) * dz; total = cum[-1]
        if total > 0:
            iz = int(np.searchsorted(cum, HF_FRAC*total))
            H[i] = z_arr[min(iz, len(z_arr)-1)]
    return t, L_x, L_y, H


def engine_temp_profile(sim):
    xz = [s for s in sim.slices
          if s.orientation == 2 and "TEMP" in s.quantity.name.upper()]
    sl = min(xz, key=lambda s: abs(s.extent.y_start - Y_TARGET))
    ext = sl.extent
    T_all = sl.to_global(masked=True, fill=np.nan)
    t_arr = np.asarray(sl.times)
    x_arr = np.linspace(ext.x_start, ext.x_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])
    ix    = int(np.argmin(np.abs(x_arr - X_ENG)))
    iz_lo = int(np.searchsorted(z_arr, Z_LO))
    iz_hi = int(np.searchsorted(z_arr, Z_HI, side="right")) - 1
    z_sel = z_arr[iz_lo:iz_hi+1]
    t1 = min(WIN[1], float(t_arr.max()))
    mask = (t_arr >= WIN[0]) & (t_arr <= t1)
    if not mask.any():
        mask = np.array([int(np.argmax(t_arr))])
    T_win = T_all[np.ix_(mask, [ix], np.arange(iz_lo, iz_hi+1))]
    return z_sel, np.nanmean(T_win, axis=0)[0], np.nanstd(T_win, axis=0)[0], float(ext.y_start)


def load_ref(name):
    p = FLAME / name
    return np.loadtxt(p, delimiter=",") if p.exists() else None


def main():
    series = sys.argv[1] if len(sys.argv) > 1 else "fire1"
    if series not in SERIES:
        sys.exit(f"series must be one of {list(SERIES)}")
    tmpl, tag = SERIES[series]
    OUT = FLAME / series; OUT.mkdir(parents=True, exist_ok=True)
    print(f"=== series '{series}' ({tag}) -> {OUT} ===")

    results = {}
    for tp in PEAK_TIMES:
        case = tmpl.format(tp=tp)
        print(f"loading {case} ...", flush=True)
        sim = fdsreader.Simulation(str(RES / case))
        t, Lx, Ly, Hf = flame_metrics(sim)
        Lxy = np.sqrt(Lx**2 + Ly**2)
        theta = np.full(len(t), np.nan)
        gz = Hf > 0.05
        theta[gz] = np.degrees(np.arctan2(Lxy[gz], Hf[gz]))
        z, T, Tstd, ysl = engine_temp_profile(sim)
        results[tp] = dict(label=f"peak @{tp} s", color=COLORS[tp], peak=tp,
                           t=t, Ly=Ly, Hf=Hf, theta=theta,
                           z=z, T=T, Tstd=Tstd, y=ysl)
        print(f"  -> {len(t)} frames t=[{t.min():.0f},{t.max():.0f}]s ; "
              f"engine T {np.nanmin(T):.1f}-{np.nanmax(T):.1f} C")

    # steady-state table
    print(f"\nSteady-state {WIN[0]:.0f}-{WIN[1]:.0f} s:")
    print(f"{'case':10s} {'L_y':>7s} {'H_f':>7s} {'theta_z':>8s} "
          f"{'T@2.0':>7s} {'T@2.5':>7s} {'T@3.0':>7s}")
    for tp, r in results.items():
        w = (r["t"] >= WIN[0]) & (r["t"] <= WIN[1])
        at = lambda zt: r["T"][int(np.argmin(np.abs(r["z"]-zt)))]
        print(f"{r['label']:10s} {np.nanmean(r['Ly'][w]):7.3f} "
              f"{np.nanmean(r['Hf'][w]):7.3f} {np.nanmean(r['theta'][w]):8.1f} "
              f"{at(2.0):7.1f} {at(2.5):7.1f} {at(3.0):7.1f}")

    refs = {k: load_ref(v) for k, v in REF_FILES.items()}

    # ---- individual metric overlays ----
    def overlay(key, refkey, ylabel, fname):
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ref = refs.get(refkey)
        if ref is not None:
            ax.plot(ref[:, 0], ref[:, 1], "k-s", lw=1.5, ms=4, mfc="none",
                    label="Reference (Lan 2023)")
        for tp, r in results.items():
            m = r["t"] <= TMAX
            tb, vb = block_mean(r["t"][m], r[key][m], BLOCK)
            ax.plot(tb, vb, "-o", color=r["color"], lw=2.0, ms=4, label=r["label"])
            ax.axvline(r["peak"], color=r["color"], ls=":", lw=1.0, alpha=0.6)
        ax.set_xlabel("Time (s)"); ax.set_ylabel(ylabel)
        ax.set_xlim(0, TMAX); ax.grid(alpha=0.3)
        ax.legend(loc="best", framealpha=0.95)
        fig.tight_layout(); fig.savefig(OUT / fname, dpi=150); plt.close(fig)
        print("->", OUT / fname)

    overlay("Ly", "Ly", r"$L_y$ (m)", "cmp_fig9_Ly.png")
    overlay("Hf", "Hf", r"$H_f$ (m)", "cmp_fig10_1_Hf.png")
    overlay("theta", "theta", r"$\theta_z$ (deg)", "cmp_fig10_2_thetaz.png")

    # ---- combined 1x3 panel ----
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.6))
    for ax, (key, refkey, yl) in zip(
            axs, [("Ly", "Ly", r"$L_y$ (m)"), ("Hf", "Hf", r"$H_f$ (m)"),
                  ("theta", "theta", r"$\theta_z$ (deg)")]):
        ref = refs.get(refkey)
        if ref is not None:
            ax.plot(ref[:, 0], ref[:, 1], "k-s", lw=1.5, ms=4, mfc="none",
                    label="Reference (Lan 2023)")
        for tp, r in results.items():
            m = r["t"] <= TMAX
            tb, vb = block_mean(r["t"][m], r[key][m], BLOCK)
            ax.plot(tb, vb, "-o", color=r["color"], lw=2.0, ms=4, label=r["label"])
            ax.axvline(r["peak"], color=r["color"], ls=":", lw=1.0, alpha=0.6)
        ax.set_xlabel("Time (s)"); ax.set_ylabel(yl); ax.set_xlim(0, TMAX); ax.grid(alpha=0.3)
    axs[0].legend(loc="best")
    fig.suptitle(f"HRR peak-time comparison [{series}: {tag}]  "
                 f"(vents on t=0, 30-step block avg)", fontsize=15)
    fig.tight_layout(); fig.savefig(OUT / "cmp_fig9_10_panel.png", dpi=150); plt.close(fig)
    print("->", OUT / "cmp_fig9_10_panel.png")

    # ---- engine-top temperature profile ----
    ref = None
    p = FLAME / REF_CSV
    if p.exists():
        ref = np.loadtxt(p, delimiter=",")
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for tp, r in results.items():
        ax.plot(r["z"], r["T"], "-o", color=r["color"], lw=1.9, ms=5,
                label=r["label"], zorder=3)
        ax.fill_between(r["z"], r["T"]-r["Tstd"], r["T"]+r["Tstd"],
                        color=r["color"], alpha=0.15, zorder=1)
    if ref is not None:
        ax.plot(ref[:, 1], ref[:, 0], "k-s", lw=1.5, ms=5, mfc="none",
                label="Reference", zorder=5)
    ax.set_xlabel("z  (m)"); ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(Z_LO, Z_HI)
    lo = min(np.nanmin(r["T"]-r["Tstd"]) for r in results.values())
    hi = max(np.nanmax(r["T"]+r["Tstd"]) for r in results.values())
    if ref is not None:
        lo = min(lo, float(ref[:, 0].min())); hi = max(hi, float(ref[:, 0].max()))
    ax.set_ylim(max(0, lo-5), hi+8); ax.grid(alpha=0.3)
    ax.legend(loc="upper left", framealpha=0.95, title="HRR peak time")
    ax.set_title(f"Engine-top T(z), {WIN[0]:.0f}-{WIN[1]:.0f} s  [{series}: {tag}]",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "engine_temp_profile_compare.png", dpi=150); plt.close(fig)
    print("->", OUT / "engine_temp_profile_compare.png")


if __name__ == "__main__":
    main()
