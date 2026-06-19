#!/usr/bin/env python3
"""
Flame envelope sensitivity to extraction thresholds — M5 only.

Vary two "HRR criteria" while re-extracting from the SAME M5 sim data:
    1. HRRPUV_THRESH for envelope (cells included as "flame")
       → affects L_x, L_y, θ_y
    2. Heskestad cumulative-HRR percentage for H_f
       → affects H_f

For each threshold, redraw the 3 panels (Fig 9, Fig 10_1, Fig 10_2)
overlaid against paper refs.

Output: analysis/flame/threshold_sweep.png   (3 rows × 2 cols)
        analysis/flame/threshold_sweep.csv   (steady-state avgs)
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "backup" / "Results_backup_old_geometry"
OUT = ROOT / "analysis" / "flame"
REF_FIG9    = OUT / "Fig9.csv"     # L_x(t)
REF_FIG10_1 = OUT / "Fig10_1.csv"  # H_f(t)
REF_FIG10_2 = OUT / "Fig10_2.csv"  # θ_y(t)

CASE_ID = "grid_mesh5_759808"   # M5 only
SLICE_X_CENTER = 8.40            # YZ slice  → L_y, L_z
SLICE_Y_CENTER = 1.45            # XZ slice  → L_x, L_z

# Sweep ranges
HRRPUV_THRESHOLDS = [50, 100, 200, 500, 1000]    # kW/m³ for envelope
HF_PERCENTAGES    = [0.80, 0.90, 0.95, 0.99, 0.995]  # cumulative-HRR cutoff

N_HF = 30
Z_MAX = 3.0
DZ_HF = Z_MAX / N_HF
Z_EDGES = np.arange(N_HF + 1) * DZ_HF
WIN = (200.0, 300.0)


def load_devc(case_id):
    f = RES / case_id / f"{case_id}_devc.csv"
    rows = list(csv.reader(open(f)))
    hdr = [c.strip() for c in rows[1]]
    data = {h: [] for h in hdr}
    for r in rows[2:]:
        if len(r) != len(hdr): continue
        for h, v in zip(hdr, r):
            try: data[h].append(float(v))
            except ValueError: data[h].append(np.nan)
    return {h: np.asarray(v) for h, v in data.items()}


def heskestad_hf(d, pct):
    """H_f(t) using cumulative HRR up to `pct` of total."""
    hf_cols = [f"Hf_int_{k:02d}" for k in range(N_HF)]
    H = np.stack([d[c] for c in hf_cols], axis=1)
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
        hf[i] = z_lo if c_hi - c_lo < 1e-9 else \
                z_lo + (target - c_lo) / (c_hi - c_lo) * (z_hi - z_lo)
    return hf


def find_slice_hrrpuv(sim, orient, target):
    cands = [(abs(getattr(sl.extent,
                          "x_start" if orient == 1 else
                          "y_start" if orient == 2 else "z_start") - target), sl)
             for sl in sim.slices
             if sl.orientation == orient and sl.quantity.name == "HRRPUV"]
    return min(cands, key=lambda t: t[0])[1] if cands else None


def extents_from_slice(sl, plane, thresh):
    if sl is None: return None, None, None
    Q = sl.to_global(masked=True, fill=0.0)
    t = sl.times
    ext = sl.extent
    if plane == "yz":
        a_vals = np.linspace(ext.y_start, ext.y_end, Q.shape[1])
    else:
        a_vals = np.linspace(ext.x_start, ext.x_end, Q.shape[1])
    b_vals = np.linspace(ext.z_start, ext.z_end, Q.shape[2])
    La = np.zeros(len(t)); Lb = np.zeros(len(t))
    for i in range(len(t)):
        mask_2d = Q[i] > thresh
        if not mask_2d.any(): continue
        ma = mask_2d.any(axis=1); mb = mask_2d.any(axis=0)
        ia = np.where(ma)[0]; ib = np.where(mb)[0]
        La[i] = a_vals[ia[-1]] - a_vals[ia[0]]
        Lb[i] = b_vals[ib[-1]] - b_vals[ib[0]]
    return t, La, Lb


def smooth(x, w=60):
    if x is None: return None
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan)
    half = w // 2
    for i in range(len(x)):
        chunk = x[max(0, i-half):min(len(x), i+half+1)]
        chunk = chunk[~np.isnan(chunk)]
        if len(chunk) > 0: out[i] = chunk.mean()
    return out


def avg_window(arr, t, win=WIN):
    if arr is None: return np.nan
    m = (t >= win[0]) & (t <= win[1])
    if not m.any(): return np.nan
    a = arr[m]; a = a[~np.isnan(a)]
    return float(a.mean()) if len(a) else np.nan


def main():
    # 1) Load DEVC and slices once
    d = load_devc(CASE_ID)
    t_dev = d["Time"]
    sim = fdsreader.Simulation(str(RES / CASE_ID))
    sl_yz = find_slice_hrrpuv(sim, 1, SLICE_X_CENTER)
    sl_xz = find_slice_hrrpuv(sim, 2, SLICE_Y_CENTER)

    # 2) Compute Lx, Ly per HRRPUV threshold
    sweep_envelope = {}  # thresh -> (Lx, Ly, theta_y)
    for thr in HRRPUV_THRESHOLDS:
        t_yz, Ly, _   = extents_from_slice(sl_yz, "yz", thr)
        t_xz, Lx, _   = extents_from_slice(sl_xz, "xz", thr)
        Ly = np.interp(t_dev, t_yz, Ly)
        Lx = np.interp(t_dev, t_xz, Lx)
        good = Ly > 0.05
        theta_y = np.full_like(t_dev, np.nan)
        theta_y[good] = np.degrees(np.arctan2(Lx[good], Ly[good]))
        sweep_envelope[thr] = (Lx, Ly, theta_y)

    # 3) Compute H_f per percentage
    sweep_hf = {pct: heskestad_hf(d, pct) for pct in HF_PERCENTAGES}

    # 4) Plot — 3 rows × 2 cols
    #    Left  col: HRRPUV-threshold sweep (L_x, L_y panels)
    #    Right col: H_f sweep (H_f panel) + θ_y from threshold sweep
    fig, axes = plt.subplots(3, 2, figsize=(15, 11))
    (ax_Lx_thr, ax_Hf_pct) = axes[0]
    (ax_Ly_thr, ax_Hf_blank) = axes[1]
    (ax_th_thr, ax_legend) = axes[2]
    ax_Hf_blank.set_visible(False)
    ax_legend.set_visible(False)

    cmap_thr = plt.cm.viridis
    cmap_pct = plt.cm.plasma

    # Paper refs
    def load_ref(p):
        return np.loadtxt(p, delimiter=",") if p.exists() else None
    r9   = load_ref(REF_FIG9)
    r101 = load_ref(REF_FIG10_1)
    r102 = load_ref(REF_FIG10_2)

    rows = []
    # L_x panel + θ_y panel — HRRPUV threshold sweep
    for i, thr in enumerate(HRRPUV_THRESHOLDS):
        Lx, Ly, ty = sweep_envelope[thr]
        col = cmap_thr(i / max(1, len(HRRPUV_THRESHOLDS) - 1))
        Lx_avg = avg_window(Lx, t_dev)
        Ly_avg = avg_window(Ly, t_dev)
        ty_avg = avg_window(ty, t_dev)
        ax_Lx_thr.plot(t_dev, smooth(Lx), color=col, lw=1.6,
                       label=f"thr={thr:.0f}  ⟨L_x⟩={Lx_avg:.2f}m")
        ax_Ly_thr.plot(t_dev, smooth(Ly), color=col, lw=1.6,
                       label=f"thr={thr:.0f}  ⟨L_y⟩={Ly_avg:.2f}m")
        ax_th_thr.plot(t_dev, smooth(ty), color=col, lw=1.6,
                       label=f"thr={thr:.0f}  ⟨θ_y⟩={ty_avg:.1f}°")
        rows.append({"kind":"thresh", "value":thr,
                     "Lx_avg":round(Lx_avg,3), "Ly_avg":round(Ly_avg,3),
                     "theta_y_avg":round(ty_avg,1), "Hf_avg":None})

    # H_f panel — percentage sweep
    for i, pct in enumerate(HF_PERCENTAGES):
        Hf = sweep_hf[pct]
        col = cmap_pct(i / max(1, len(HF_PERCENTAGES) - 1))
        Hf_avg = avg_window(Hf, t_dev)
        ax_Hf_pct.plot(t_dev, smooth(Hf), color=col, lw=1.6,
                       label=f"pct={pct*100:.1f}%  ⟨H_f⟩={Hf_avg:.2f}m")
        rows.append({"kind":"pct", "value":pct,
                     "Lx_avg":None, "Ly_avg":None,
                     "theta_y_avg":None, "Hf_avg":round(Hf_avg,3)})

    # Paper refs
    if r9 is not None:
        ax_Ly_thr.plot(r9[:,0], r9[:,1], "k--x", lw=2.0, ms=5,
                       label="Paper Fig 9 (L_y)", zorder=10)
    if r101 is not None:
        ax_Hf_pct.plot(r101[:,0], r101[:,1], "k--x", lw=2.0, ms=5,
                       label="Paper Fig 10_1 (H_f)", zorder=10)
    if r102 is not None:
        ax_th_thr.plot(r102[:,0], r102[:,1], "k--x", lw=2.0, ms=5,
                       label="Paper Fig 10_2 (θ_y)", zorder=10)

    for ax in [ax_Lx_thr, ax_Ly_thr, ax_th_thr, ax_Hf_pct]:
        ax.axvspan(*WIN, color="lightgray", alpha=0.3, zorder=0)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="best")
        ax.set_xlabel("Time (s)")

    ax_Lx_thr.set_ylabel("L_x (m)"); ax_Lx_thr.set_title("L_x: HRRPUV threshold sweep")
    ax_Ly_thr.set_ylabel("L_y (m)"); ax_Ly_thr.set_title("Fig 9 — L_y: HRRPUV threshold sweep")
    ax_th_thr.set_ylabel("θ_y (°)"); ax_th_thr.set_title("Fig 10_2 — θ_y = atan(L_x/L_y) : threshold sweep")
    ax_Hf_pct.set_ylabel("H_f (m)"); ax_Hf_pct.set_title("Fig 10_1 — H_f: cumulative-HRR cutoff sweep")

    fig.suptitle(f"Mesh-5 only — flame envelope sensitivity to HRR criteria\n"
                 f"(HRRPUV thresh ∈ {HRRPUV_THRESHOLDS} kW/m³,  "
                 f"H_f cutoff ∈ {[f'{p*100:.1f}%' for p in HF_PERCENTAGES]})",
                 fontsize=11)
    fig.tight_layout()
    out_path = OUT / "threshold_sweep.png"
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"wrote {out_path}")

    csv_path = OUT / "threshold_sweep.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)
    print(f"wrote {csv_path}")

    # Console table
    print(f"\n{'kind':<8} {'value':>8} {'Lx':>7} {'Ly':>7} {'θ_y°':>7} {'H_f':>7}")
    print("-" * 60)
    for r in rows:
        v = f"{r['value']}"
        print(f"{r['kind']:<8} {v:>8} "
              f"{(r['Lx_avg'] if r['Lx_avg'] is not None else '—'):>7} "
              f"{(r['Ly_avg'] if r['Ly_avg'] is not None else '—'):>7} "
              f"{(r['theta_y_avg'] if r['theta_y_avg'] is not None else '—'):>7} "
              f"{(r['Hf_avg'] if r['Hf_avg'] is not None else '—'):>7}")


if __name__ == "__main__":
    main()
