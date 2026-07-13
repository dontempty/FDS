#!/usr/bin/env python3
"""
Lan et al. 2023  Fig 9, 10_1, 10_2  —  flame shape metrics (case e_M5).

All metrics are computed from the 3D HRRPUV field (smoke3d), one load, in
flame_metrics().  See flame_metrics_report.md for the full method/rationale.

  L_y  : flame y-projection span — y bbox of {max_z HRRPUV > THRESH}   [Fig 9]
  L_x  : flame x-drift — |x-centroid − burner x-centre| of that projection
  H_f  : flame tip height — YZ plane through the flame centre (HRR x-centroid),
         cumulative-HRR ∫: lowest z where ∫_0^z(∫HRRPUV dy) ≥ HF_FRAC·total   [Fig 10_1]
  θ_z  : arctan(√(L_x²+L_y²) / H_f)  (deg) ;  with L_x≈0 → ≈ arctan(L_y/H_f)   [Fig 10_2]
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging;  logging.disable(logging.CRITICAL)
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

# ===== plot font setting =====
plt.rcParams.update({
    "axes.labelsize": 18,
    "axes.titlesize": 20,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 12,
})

ROOT  = Path("/scratch/x3319a05/fds/Engine_Room")
RES   = ROOT / "Results"
OUT   = ROOT / "analysis" / "flame"

CASE   = "e_M5"
THRESH = 150.0   # kW/m³  — HRRPUV flame-surface threshold for L_x, L_y projection
                 #          (L_y≈1.17 m at steady state; H_f uses HF_FRAC, not this)
SMOOTH = 30      # rolling-mean half-window steps

WIN           = (250.0, 300.0)
FIRE_X        = (7.955, 8.845)  # fire footprint x-extent (input deck) — burner x-axis
FIRE_Y        = (1.005, 1.895)  # fire footprint y-extent (input deck) — flame mesh band
HF_FRAC       = 0.99    # H_f = lowest z where cumulative HRR ≥ this fraction of total


# ── helpers ──────────────────────────────────────────────────────────────────

def rolling_mean(arr: np.ndarray, half: int) -> np.ndarray:
    out = np.full_like(arr, np.nan, dtype=float)
    for i in range(len(arr)):
        lo = max(0, i - half)
        hi = min(len(arr), i + half + 1)
        chunk = arr[lo:hi]
        chunk = chunk[~np.isnan(chunk)]
        if len(chunk):
            out[i] = chunk.mean()
    return out


def flame_metrics(sim):
    """
    All flame metrics from the 3D HRRPUV field (one load), over the fire y-band.

    L_x, L_y — from the XY projection  P(t,x,y) = max_z HRRPUV  of {P > THRESH}:
               L_y = y-projection span (bounding box) — the flame tilts in y, so its
                     along-tilt elongation in y is the projection length (paper Fig 9).
               L_x = |x-centroid − burner x-centre| — the flame does NOT tilt in x,
                     so the cross-tilt term is just the small x-drift (≈0.1 m), not
                     the footprint width.  This keeps θ_z = arctan(√(Lx²+Ly²)/H_f)
                     ≈ arctan(L_y/H_f), matching the paper (Lx≈0 in their data).

    H_f      — YZ plane through the FLAME CENTRE (HRR x-centroid).
               B(t,x,z) = ∫HRRPUV dy ;  x_c(t) = ∫x·a dx / ∫a dx , a=∫B dz ;
               q'(z) = B(t,x_c,z) ;  H_f = lowest z where ∫_0^z q' ≥ HF_FRAC·∫q'.

    Returns (t, L_x, L_y, H_f, mean flame-centre x over WIN).
    """
    s3 = [s for s in sim.smoke_3d if "HRRPUV" in s.quantity.name.upper()][0]
    t  = np.array(s3.times)

    # meshes whose y-range overlaps the fire footprint (flame stays in this band)
    sel = [m for m in sim.meshes
           if m.coordinates["y"][0] < FIRE_Y[1] and m.coordinates["y"][-1] > FIRE_Y[0]]
    x_arr = np.unique(np.concatenate([m.coordinates["x"] for m in sel]))
    y_arr = np.unique(np.concatenate([m.coordinates["y"] for m in sel]))
    z_arr = np.unique(np.concatenate([m.coordinates["z"] for m in sel]))
    dz    = float(np.diff(z_arr).mean())

    P = np.zeros((len(t), len(x_arr), len(y_arr)))   # max_z HRRPUV  → L_x, L_y
    B = np.zeros((len(t), len(x_arr), len(z_arr)))   # ∫HRRPUV dy    → H_f, centre
    for m in sel:
        d   = s3[m].data                             # (t, nx, ny, nz)
        dy  = float(np.diff(m.coordinates["y"]).mean())
        pm  = d.max(axis=3)                          # (t, nx, ny)
        qy  = d.sum(axis=2) * dy                     # (t, nx, nz)
        ixg = np.clip(np.searchsorted(x_arr, m.coordinates["x"]), 0, len(x_arr) - 1)
        iyg = np.clip(np.searchsorted(y_arr, m.coordinates["y"]), 0, len(y_arr) - 1)
        izg = np.clip(np.searchsorted(z_arr, m.coordinates["z"]), 0, len(z_arr) - 1)
        for a, xg in enumerate(ixg):
            P[:, xg, iyg]  = np.maximum(P[:, xg, iyg], pm[:, a, :])
            B[:, xg, izg] += qy[:, a, :]

    # ── L_y : y-projection span ;  L_x : x-drift of flame from burner centre ───
    XX, _   = np.meshgrid(x_arr, y_arr, indexing="ij")
    xc_burn = 0.5 * (FIRE_X[0] + FIRE_X[1])
    L_x = np.zeros(len(t))
    L_y = np.zeros(len(t))
    for i in range(len(t)):
        mask = P[i] > THRESH
        if not mask.any():
            continue
        iy = np.where(mask.any(axis=0))[0]
        if len(iy) > 1:
            L_y[i] = y_arr[iy[-1]] - y_arr[iy[0]]            # along-tilt span
        w = P[i][mask]
        L_x[i] = abs((XX[mask] * w).sum() / w.sum() - xc_burn)  # cross-tilt x-drift

    # ── H_f : YZ plane through flame centre ────────────────────────────────────
    A    = B.sum(axis=2) * dz                        # (t, x)  HRR per x
    H    = np.zeros(len(t))
    xcen = np.full(len(t), np.nan)
    for i in range(len(t)):
        a = A[i]
        if a.sum() <= 0:
            continue
        xcen[i] = (x_arr * a).sum() / a.sum()        # flame-centre x
        ix      = int(np.argmin(np.abs(x_arr - xcen[i])))
        cum     = np.cumsum(B[i, ix]) * dz
        total   = cum[-1]
        if total > 0:
            iz   = int(np.searchsorted(cum, HF_FRAC * total))
            H[i] = z_arr[min(iz, len(z_arr) - 1)]

    win = (t >= WIN[0]) & (t <= WIN[1])
    xc_mean = float(np.nanmean(xcen[win]))
    print(f"Flame-centre x: avg {xc_mean:.3f} m over {WIN[0]:.0f}-{WIN[1]:.0f}s "
          f"(range {np.nanmin(xcen):.2f}-{np.nanmax(xcen):.2f} m)")
    return t, L_x, L_y, H, xc_mean


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    sim = fdsreader.Simulation(str(RES / CASE))

    print("L_x, L_y: 3D HRRPUV projected onto XY plane (max over all z)")
    t, L_x, L_y, H_f, xc_fire = flame_metrics(sim)

    # tilt angles
    L_xy   = np.sqrt(L_x**2 + L_y**2)
    theta_z = np.full(len(t), np.nan)
    good_z  = H_f > 0.05
    theta_z[good_z] = np.degrees(np.arctan2(L_xy[good_z], H_f[good_z]))

    # smoothed
    L_y_sm    = rolling_mean(L_y,    SMOOTH)
    H_f_sm    = rolling_mean(H_f,    SMOOTH)
    theta_sm  = rolling_mean(theta_z, SMOOTH)

    # steady-state averages
    mask_win = (t >= WIN[0]) & (t <= WIN[1])
    print(f"\nAvg {WIN[0]:.0f}–{WIN[1]:.0f} s:")
    print(f"  L_x  = {np.nanmean(L_x[mask_win]):.3f} m")
    print(f"  L_y  = {np.nanmean(L_y[mask_win]):.3f} m")
    print(f"  H_f  = {np.nanmean(H_f[mask_win]):.3f} m")
    print(f"  θ_z  = {np.nanmean(theta_z[mask_win]):.1f}°")

    # load refs
    def load_ref(name):
        p = OUT / name
        return np.loadtxt(p, delimiter=",") if p.exists() else None

    ref9   = load_ref("Fig9.csv")
    ref101 = load_ref("Fig10_1.csv")
    ref102 = load_ref("Fig10_2.csv")

    COLOR  = "#8e44ad"
    SUFFIX = CASE.split("_")[-1]

    # ── plot: three separate figures, no titles ────────────────────────────────
    def plot_metric(y_present, ref, ylabel, outname):
        fig, ax = plt.subplots(figsize=(6, 4.5))
        if ref is not None:
            ax.plot(ref[:, 0], ref[:, 1], "k-s", lw=1.5, ms=4, mfc="none",
                    label="Reference")
        ax.plot(t, y_present, color=COLOR, lw=2.0, label="Present")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.3)
        ax.legend(loc="lower right", framealpha=0.95)
        ax.set_xlim(0, float(t[-1]) + 2)
        fig.tight_layout()
        out = OUT / outname
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"→ {out}")

    plot_metric(L_y_sm,   ref9,   r"$L_y$ (m)",       f"fig9_Ly_{SUFFIX}.png")
    plot_metric(H_f_sm,   ref101, r"$H_f$ (m)",       f"fig10_1_Hf_{SUFFIX}.png")
    plot_metric(theta_sm, ref102, r"$\theta_z$ (°)",  f"fig10_2_thetaz_{SUFFIX}.png")


if __name__ == "__main__":
    main()
