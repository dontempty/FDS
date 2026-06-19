#!/usr/bin/env python3
"""
Extract flame envelope quantities from sim data.

Paper Lan 2023 Fig 9/10/12 quantities (no paper reference here — sim-only):
    H_f   : Heskestad 99% flame height
            From DEVC Hf_int_00..29  (cumulative HRR over 30 z-slabs).
            H_f = z where cumsum(HRR_slab) = 0.99 * total.
    L_y   : flame y-extent at fire-center x-plane
            From SLCF HRRPUV YZ @ PBX=8.40, threshold HRRPUV > 200 kW/m³,
            L_y = y_max(flame cells) − y_min(flame cells).
    L_x   : flame x-extent at fire-center y-plane
            From SLCF HRRPUV XZ @ PBY=1.45, same threshold.
    θ     : tilt angle = atan(L_y / H_f), degrees from vertical.

Note: gen_engine_room.py's flame_xmin/xmax/ymin/ymax DEVCs are broken
      (no QUANTITY_RANGE → return locations of zero-HRRPUV cells).
      We compute L_x/L_y post-hoc from SLCF instead.

Applied to: grid_mesh1, 3, 5, 6  (old geometry, backup/)

Output: analysis/flame/flame_envelope.png   (3 panels: L_y, H_f, θ vs time)
        analysis/flame/flame_envelope.csv   (steady-state averages t=200-300)
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import csv, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "backup" / "Results_backup_old_geometry"
OUT = ROOT / "analysis" / "flame"
REF_FIG9   = OUT / "Fig9.csv"     # L_y(t)  m
REF_FIG10_1 = OUT / "Fig10_1.csv"  # H_f(t)  m
REF_FIG10_2 = OUT / "Fig10_2.csv"  # θ(t)   deg

N_HF = 30
Z_MAX = 3.0
DZ_HF = Z_MAX / N_HF
Z_EDGES = np.arange(N_HF + 1) * DZ_HF       # 0.0, 0.1, ..., 3.0
WIN = (200.0, 300.0)
HRRPUV_THRESH = 200.0   # kW/m³ — Heskestad-style flame envelope cutoff

# Old geometry: fire at x=[7.9,8.9], y=[1.0,2.0]  →  center (8.4, 1.5)
SLICE_X_CENTER = 8.40   # YZ slice at fire center  → L_y
SLICE_Y_CENTER = 1.45   # XZ slice at fire center y → L_x

MESHES = [
    ("grid_mesh1_759273", "M1  (84k)",  "tab:blue"),
    ("grid_mesh3_759807", "M3  (670k)", "tab:green"),
    ("grid_mesh5_759808", "M5  (1.6M)", "tab:orange"),
    ("grid_mesh6_760359", "M6  (3.1M)", "tab:red"),
]


def load_devc(case_id):
    f = RES / case_id / f"{case_id}_devc.csv"
    if not f.exists(): return None
    rows = list(csv.reader(open(f)))
    if len(rows) < 3: return None
    hdr = [c.strip() for c in rows[1]]
    data = {h: [] for h in hdr}
    for r in rows[2:]:
        if len(r) != len(hdr): continue
        for h, v in zip(hdr, r):
            try: data[h].append(float(v))
            except ValueError: data[h].append(np.nan)
    return {h: np.asarray(v) for h, v in data.items()}


def heskestad_hf(d, pct=0.99):
    """Return H_f(t) = z where cumulative HRR reaches `pct` of total."""
    hf_cols = [f"Hf_int_{k:02d}" for k in range(N_HF)]
    if not all(c in d for c in hf_cols): return None
    H = np.stack([d[c] for c in hf_cols], axis=1)    # (n_t, n_slabs)
    H = np.maximum(H, 0.0)
    cum = np.cumsum(H, axis=1)
    total = cum[:, -1]
    hf = np.full(H.shape[0], np.nan)
    for i, tot in enumerate(total):
        if tot <= 1e-6: continue
        target = pct * tot
        idx = int(np.searchsorted(cum[i], target))
        if idx >= N_HF: hf[i] = Z_EDGES[-1]; continue
        z_lo = Z_EDGES[idx]; z_hi = Z_EDGES[idx + 1]
        c_lo = cum[i, idx-1] if idx > 0 else 0.0
        c_hi = cum[i, idx]
        if c_hi - c_lo < 1e-9: hf[i] = z_lo
        else: hf[i] = z_lo + (target - c_lo) / (c_hi - c_lo) * (z_hi - z_lo)
    return hf


def find_slice_hrrpuv(sim, orient, target):
    """Find HRRPUV slice at given orientation closest to target plane."""
    cands = [(abs(getattr(sl.extent,
                          "x_start" if orient==1 else
                          "y_start" if orient==2 else "z_start") - target), sl)
             for sl in sim.slices
             if sl.orientation == orient and sl.quantity.name == "HRRPUV"]
    if not cands: return None
    return min(cands, key=lambda t: t[0])[1]


def extents_from_slice(sl, plane):
    """Return time series of extents AND absolute z_max along BOTH axes of the slice.

    plane: 'yz' (YZ slice → returns L_y, L_z extent, z_max absolute)
           'xz' (XZ slice → returns L_x, L_z extent, z_max absolute)
    """
    if sl is None: return None, None, None, None
    Q = sl.to_global(masked=True, fill=0.0)   # (n_t, n_a, n_b)
    t = sl.times
    ext = sl.extent
    if plane == "yz":
        a_vals = np.linspace(ext.y_start, ext.y_end, Q.shape[1])
        b_vals = np.linspace(ext.z_start, ext.z_end, Q.shape[2])
    elif plane == "xz":
        a_vals = np.linspace(ext.x_start, ext.x_end, Q.shape[1])
        b_vals = np.linspace(ext.z_start, ext.z_end, Q.shape[2])
    La = np.zeros(len(t))   # along a-axis (Ly or Lx)
    Lb = np.zeros(len(t))   # along b-axis (Lz extent = z_max-z_min)
    Z_top = np.zeros(len(t))  # absolute z_max (B-family H_f)
    for i in range(len(t)):
        mask_2d = Q[i] > HRRPUV_THRESH
        if not mask_2d.any():
            continue
        ma = mask_2d.any(axis=1)
        mb = mask_2d.any(axis=0)
        ia = np.where(ma)[0]; ib = np.where(mb)[0]
        La[i] = a_vals[ia[-1]] - a_vals[ia[0]]
        Lb[i] = b_vals[ib[-1]] - b_vals[ib[0]]
        Z_top[i] = b_vals[ib[-1]]
    return t, La, Lb, Z_top


def derive(case_id):
    d = load_devc(case_id)
    if d is None: return None
    t_dev = d["Time"]
    # ─── PRIMARY H_f = A5  (cumsum 99.9% over fire base column) ───
    Hf    = heskestad_hf(d, pct=0.999)
    Hf_99 = heskestad_hf(d, pct=0.99)   # legacy A3 for comparison

    p = RES / case_id
    sim = fdsreader.Simulation(str(p))
    sl_yz_center = find_slice_hrrpuv(sim, 1, SLICE_X_CENTER)  # YZ at x=8.40
    sl_xz        = find_slice_hrrpuv(sim, 2, SLICE_Y_CENTER)  # XZ at y=1.45
    t_yz, Ly, Lz_yz, _ = extents_from_slice(sl_yz_center, "yz")
    t_xz, Lx, Lz_xz, _ = extents_from_slice(sl_xz,        "xz")

    # Align all to DEVC time grid by linear interp
    if Ly    is not None: Ly    = np.interp(t_dev, t_yz, Ly)
    if Lx    is not None: Lx    = np.interp(t_dev, t_xz, Lx)
    if Lz_yz is not None: Lz_yz = np.interp(t_dev, t_yz, Lz_yz)
    if Lz_xz is not None: Lz_xz = np.interp(t_dev, t_xz, Lz_xz)

    Lz_components = [a for a in [Lz_yz, Lz_xz] if a is not None]
    Lz = np.maximum.reduce(Lz_components) if Lz_components else None

    # Paper-correct angles
    #   θ_y = atan(L_x / L_y) × 57.3   — deflection from y-axis  (Fig 9)
    #   θ_z = atan(L_xy / L_z) × 57.3  — deflection from z-axis  (Fig 10)
    # with L_xy = sqrt(L_x² + L_y²)
    theta_y = np.full_like(t_dev, np.nan)
    theta_z = np.full_like(t_dev, np.nan)
    if Lx is not None and Ly is not None:
        good = Ly > 0.05
        theta_y[good] = np.degrees(np.arctan2(Lx[good], Ly[good]))
        Lxy = np.sqrt(Lx**2 + Ly**2)
        if Lz is not None:
            good_z = (Lz > 0.05) & ~np.isnan(Lz)
            theta_z[good_z] = np.degrees(np.arctan2(Lxy[good_z], Lz[good_z]))

    return dict(t=t_dev, Hf=Hf, Hf_99=Hf_99, Lx=Lx, Ly=Ly, Lz=Lz,
                theta_y=theta_y, theta_z=theta_z,
                V=d.get("flame_volume"),
                hrr_in_box=d.get("flame_hrr_in_box"),
                T_tip=d.get("T_tip"),
                vy_inlet=d.get("vy_inlet"))


def avg_window(arr, t, win=WIN):
    if arr is None: return np.nan
    m = (t >= win[0]) & (t <= win[1])
    if not m.any(): return np.nan
    a = arr[m]
    a = a[~np.isnan(a)]
    if len(a) == 0: return np.nan
    return float(a.mean())


def smooth(x, w=30):
    """Rolling mean with NaN-safe edges (paper uses ~30 step averaging)."""
    if x is None: return None
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan)
    half = w // 2
    for i in range(len(x)):
        lo = max(0, i - half); hi = min(len(x), i + half + 1)
        chunk = x[lo:hi]
        chunk = chunk[~np.isnan(chunk)]
        if len(chunk) > 0:
            out[i] = chunk.mean()
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    fig, axes = plt.subplots(3, 1, figsize=(12, 11), sharex=True)
    ax_Ly, ax_Hf, ax_th = axes

    t_max = 300.0
    SMOOTH_W = 60   # ~6 s window for clean curves (paper: every 30 steps + avg)
    for cid, lab, color in MESHES:
        print(f"processing {cid}...")
        D = derive(cid)
        if D is None:
            print(f"  skip"); continue
        t = D["t"]
        t_max = max(t_max, float(t[-1]))

        Ly_avg     = avg_window(D["Ly"], t)
        Lx_avg     = avg_window(D["Lx"], t)
        Lz_avg     = avg_window(D["Lz"], t)
        Hf_avg     = avg_window(D["Hf"], t)
        Hf99_avg   = avg_window(D["Hf_99"], t)
        thy_avg    = avg_window(D["theta_y"], t)
        thz_avg    = avg_window(D["theta_z"], t)
        V_avg   = avg_window(D["V"],  t)
        Tt_avg  = avg_window(D["T_tip"], t)
        vy_avg  = avg_window(D["vy_inlet"], t)
        hrr_box = avg_window(D["hrr_in_box"], t)

        ax_Ly.plot(t, smooth(D["Ly"], SMOOTH_W), color=color, lw=1.6,
                   label=f"{lab}   ⟨L_y⟩={Ly_avg:.2f} m")
        ax_Hf.plot(t, smooth(D["Hf"], SMOOTH_W), color=color, lw=1.6,
                   label=f"{lab}   ⟨H_f⟩(99.9%)={Hf_avg:.2f} m  [99%={Hf99_avg:.2f}]")
        ax_Hf.plot(t, smooth(D["Hf_99"], SMOOTH_W), color=color, lw=0.8, ls=":",
                   alpha=0.7)
        ax_th.plot(t, smooth(D["theta_y"], SMOOTH_W), color=color, lw=1.6,
                   label=f"{lab}   ⟨θ_y⟩={thy_avg:.1f}°")

        rows.append({
            "case_id": cid, "label": lab,
            "Lx_avg_m":  round(Lx_avg, 3),
            "Ly_avg_m":  round(Ly_avg, 3),
            "Lz_avg_m":  round(Lz_avg, 3),
            "Hf_avg_m":  round(Hf_avg, 3),          # B4 = envelope max
            "Hf_99_avg_m":  round(Hf99_avg, 3),     # A3 = legacy 99% cumsum
            "theta_y_avg_deg": round(thy_avg, 1),
            "theta_z_avg_deg": round(thz_avg, 1),
            "V_flame_avg_m3":  round(V_avg, 3),
            "hrr_in_box_avg_kW": round(hrr_box, 1) if not np.isnan(hrr_box) else None,
            "T_tip_avg_C":   round(Tt_avg, 1) if not np.isnan(Tt_avg) else None,
            "vy_inlet_avg_m_s": round(vy_avg, 3) if not np.isnan(vy_avg) else None,
        })

    # Paper reference overlays (Fig 9, 10_1, 10_2)
    def load_ref(p):
        if not p.exists(): return None
        return np.loadtxt(p, delimiter=",")
    ref9   = load_ref(REF_FIG9)
    ref101 = load_ref(REF_FIG10_1)
    ref102 = load_ref(REF_FIG10_2)
    if ref9   is not None: ax_Ly.plot(ref9[:,0],   ref9[:,1],   "k--x", lw=2.0, ms=5, label="Paper Fig 9 — L_y ref",   zorder=10)
    if ref101 is not None: ax_Hf.plot(ref101[:,0], ref101[:,1], "k--x", lw=2.0, ms=5, label="Paper Fig 10_1 — H_f ref", zorder=10)
    if ref102 is not None: ax_th.plot(ref102[:,0], ref102[:,1], "k--x", lw=2.0, ms=5, label="Paper Fig 10_2 — θ_y ref", zorder=10)

    for ax in axes:
        ax.axvspan(*WIN, color="lightgray", alpha=0.3, zorder=0,
                   label=f"avg window [{WIN[0]:.0f}, {WIN[1]:.0f}] s")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="upper right", framealpha=0.95)

    ax_Ly.set_ylabel("L_y  (m)   — y-extent of flame")
    ax_Ly.set_title("paper Fig 9 — L_y  (HRRPUV>200, YZ@x=8.40)")
    ax_Hf.set_ylabel("H_f  (m)   — 99.9% cumsum  [solid]  /  99% cumsum [dotted]")
    ax_Hf.set_title("paper Fig 10_1 — H_f  (A5: Heskestad cumsum 99.9% over fire base column)")
    ax_th.set_ylabel("θ_y  (deg)   — atan(L_x / L_y) × 57.3")
    ax_th.set_title("paper Fig 10_2 — flame deflection from y-axis")
    ax_th.set_xlabel("Time (s)")
    ax_th.set_xlim(0, t_max)

    fig.suptitle("Grid convergence — flame envelope time series  (with paper ref overlay)",
                 fontsize=12)
    fig.tight_layout()
    fig_path = OUT / "flame_envelope.png"
    fig.savefig(fig_path, dpi=140)
    plt.close(fig)
    print(f"\nwrote {fig_path}")

    if rows:
        csv_path = OUT / "flame_envelope.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows: w.writerow(r)
        print(f"wrote {csv_path}")

        print(f"\n{'Mesh':<22} {'L_x':>6} {'L_y':>6} {'L_z':>6} "
              f"{'Hf99.9%':>8} {'Hf99%':>6} {'θ_y°':>6} {'θ_z°':>6} {'HRRbx':>7}")
        print("-" * 90)
        for r in rows:
            print(f"{r['case_id']:<22} "
                  f"{r['Lx_avg_m']:>6.2f} {r['Ly_avg_m']:>6.2f} "
                  f"{r['Lz_avg_m']:>6.2f} "
                  f"{r['Hf_avg_m']:>7.2f} {r['Hf_99_avg_m']:>6.2f} "
                  f"{r['theta_y_avg_deg']:>6.1f} {r['theta_z_avg_deg']:>6.1f} "
                  f"{(r['hrr_in_box_avg_kW'] or 0):>7.1f}")


if __name__ == "__main__":
    main()
