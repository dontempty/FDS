#!/usr/bin/env python3
"""
Phase 0 — Compare different H_f definitions on M5 data.

Goal: check whether the H_f gap (M5=0.45m vs paper=0.89m) is partly
      explained by how H_f is defined, not just by physics.

Definitions tested:
    Hf_int family  (DEVC Hf_int_00..29 — cumulative HRR over fire base column):
      A1. cumsum cutoff 90%
      A2. cumsum cutoff 95%
      A3. cumsum cutoff 99%  (current default)
      A4. cumsum cutoff 99.5%
      A5. cumsum cutoff 99.9%
      A6. weighted mean z   (Σ z*Hf_int / Σ Hf_int)
      A7. cumsum cutoff 50% (median z)

    SLCF envelope family  (HRRPUV > 200 kW/m³, z_max of flame cells):
      B1. z_max from YZ slice at x=8.40  (fire center x)
      B2. z_max from YZ slice at x=8.10  (off-center, fire flank)
      B3. z_max from XZ slice at y=1.45  (fire center y)
      B4. max(B1, B2, B3)               (combined upper envelope)

Output: analysis/flame/hf_definitions.png  (M5 only, all curves vs paper ref)
        analysis/flame/hf_definitions.csv
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
REF_FIG10_1 = OUT / "Fig10_1.csv"

CASE_ID = "grid_mesh5_759808"
HRRPUV_THRESH = 200.0
WIN = (200.0, 300.0)
N_HF = 30
Z_MAX = 3.0
DZ_HF = Z_MAX / N_HF
Z_EDGES = np.arange(N_HF + 1) * DZ_HF
Z_CENTERS = (Z_EDGES[:-1] + Z_EDGES[1:]) / 2


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


def hf_cumulative(H, cum, target):
    """Find z where cumulative HRR first reaches target, linear interp."""
    out = np.full(H.shape[0], np.nan)
    for i in range(H.shape[0]):
        if cum[i, -1] <= 1e-6: continue
        tgt = target * cum[i, -1] if target <= 1.0 else target
        if cum[i, -1] < tgt: continue
        idx = int(np.searchsorted(cum[i], tgt))
        if idx >= N_HF: out[i] = Z_EDGES[-1]; continue
        z_lo = Z_EDGES[idx]; z_hi = Z_EDGES[idx + 1]
        c_lo = cum[i, idx-1] if idx > 0 else 0.0
        c_hi = cum[i, idx]
        out[i] = z_lo if c_hi - c_lo < 1e-9 else \
                 z_lo + (tgt - c_lo) / (c_hi - c_lo) * (z_hi - z_lo)
    return out


def hf_weighted_mean(H):
    """Σ z*Hf_int / Σ Hf_int  per timestep — gives 'centre of HRR'."""
    out = np.full(H.shape[0], np.nan)
    for i in range(H.shape[0]):
        tot = H[i].sum()
        if tot <= 1e-6: continue
        out[i] = float(np.sum(Z_CENTERS * H[i]) / tot)
    return out


def find_slice_hrrpuv(sim, orient, target):
    cands = [(abs(getattr(sl.extent,
                          "x_start" if orient == 1 else
                          "y_start" if orient == 2 else "z_start") - target), sl)
             for sl in sim.slices
             if sl.orientation == orient and sl.quantity.name == "HRRPUV"]
    return min(cands, key=lambda t: t[0])[1] if cands else None


def z_max_from_slice(sl, plane, thresh=HRRPUV_THRESH):
    """Return time series of z_max where flame exists (HRRPUV > thresh)."""
    if sl is None: return None, None
    Q = sl.to_global(masked=True, fill=0.0)
    t = sl.times
    ext = sl.extent
    z = np.linspace(ext.z_start, ext.z_end, Q.shape[2])
    zmax = np.zeros(len(t))
    for i in range(len(t)):
        mask = Q[i] > thresh
        if not mask.any(): continue
        iz = np.where(mask.any(axis=0))[0]   # any over a-axis
        zmax[i] = z[iz[-1]]
    return t, zmax


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
    print(f"Loading {CASE_ID}...")
    d = load_devc(CASE_ID)
    t_dev = d["Time"]
    Hf_int = np.stack([d[f"Hf_int_{k:02d}"] for k in range(N_HF)], axis=1)
    Hf_int = np.maximum(Hf_int, 0.0)
    cum = np.cumsum(Hf_int, axis=1)

    # Hf_int family
    A1  = hf_cumulative(Hf_int, cum, 0.90)
    A2  = hf_cumulative(Hf_int, cum, 0.95)
    A3  = hf_cumulative(Hf_int, cum, 0.99)
    A4  = hf_cumulative(Hf_int, cum, 0.995)
    A5  = hf_cumulative(Hf_int, cum, 0.999)
    A6  = hf_weighted_mean(Hf_int)
    A7  = hf_cumulative(Hf_int, cum, 0.50)

    # SLCF envelope family
    sim = fdsreader.Simulation(str(RES / CASE_ID))
    sl_yz_center = find_slice_hrrpuv(sim, 1, 8.40)
    sl_yz_flank  = find_slice_hrrpuv(sim, 1, 8.10)
    sl_xz        = find_slice_hrrpuv(sim, 2, 1.45)
    t_b1, B1 = z_max_from_slice(sl_yz_center, "yz")
    t_b2, B2 = z_max_from_slice(sl_yz_flank,  "yz")
    t_b3, B3 = z_max_from_slice(sl_xz,        "xz")
    B1 = np.interp(t_dev, t_b1, B1) if B1 is not None else None
    B2 = np.interp(t_dev, t_b2, B2) if B2 is not None else None
    B3 = np.interp(t_dev, t_b3, B3) if B3 is not None else None
    if B1 is not None and B2 is not None and B3 is not None:
        B4 = np.maximum.reduce([B1, B2, B3])
    else:
        B4 = None

    DEFS = [
        ("A3 cumsum 99% (current)",  A3, "tab:blue",   "-"),
        ("A1 cumsum 90%",            A1, "lightblue",  "--"),
        ("A2 cumsum 95%",            A2, "deepskyblue","--"),
        ("A4 cumsum 99.5%",          A4, "navy",       "--"),
        ("A5 cumsum 99.9%",          A5, "darkblue",   ":"),
        ("A6 weighted-mean z",       A6, "gray",       "-"),
        ("A7 cumsum 50% (median)",   A7, "silver",     "-."),
        ("B1 z_max YZ@x=8.40",       B1, "tab:red",    "-"),
        ("B2 z_max YZ@x=8.10",       B2, "tab:orange", "-"),
        ("B3 z_max XZ@y=1.45",       B3, "tab:purple", "-"),
        ("B4 max(B1,B2,B3)",         B4, "black",      "-"),
    ]

    # Plot
    fig, ax = plt.subplots(figsize=(13, 8))
    for lab, arr, col, ls in DEFS:
        if arr is None: continue
        v = avg_window(arr, t_dev)
        ax.plot(t_dev, smooth(arr), color=col, ls=ls, lw=1.5,
                label=f"{lab}  ⟨H_f⟩={v:.2f} m")

    if REF_FIG10_1.exists():
        ref = np.loadtxt(REF_FIG10_1, delimiter=",")
        ax.plot(ref[:,0], ref[:,1], "k--x", lw=2.4, ms=6,
                label="Paper Fig 10_1  (~0.89 m)", zorder=20)

    ax.axvspan(*WIN, color="lightgray", alpha=0.3, zorder=0,
               label=f"avg window [{WIN[0]:.0f},{WIN[1]:.0f}] s")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("H_f  (m)")
    ax.set_xlim(0, 300); ax.set_ylim(0, 3.0)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper left", ncol=2, framealpha=0.95)
    ax.set_title(f"Phase 0 — H_f definitions compared, M5 only "
                 f"(HRRPUV>{HRRPUV_THRESH:.0f} for B-family)")
    fig.tight_layout()
    out_path = OUT / "hf_definitions.png"
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"wrote {out_path}")

    # CSV summary
    rows = []
    for lab, arr, _, _ in DEFS:
        if arr is None: continue
        rows.append({"definition": lab, "Hf_avg_t200_300_m": round(avg_window(arr, t_dev), 3)})
    csv_path = OUT / "hf_definitions.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)
    print(f"wrote {csv_path}")

    print(f"\n{'Definition':<32} {'⟨H_f⟩ (m)':>10}  gap-vs-paper(0.89)")
    print("-" * 65)
    for r in rows:
        gap = r["Hf_avg_t200_300_m"] - 0.89
        gap_pct = gap / 0.89 * 100
        print(f"{r['definition']:<32} {r['Hf_avg_t200_300_m']:>10.3f}  "
              f"{gap:+6.2f} ({gap_pct:+5.1f}%)")


if __name__ == "__main__":
    main()
