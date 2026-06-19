#!/usr/bin/env python3
"""
T(z) overlay for OPT cases vs baseline + paper reference.

Loads OPT1, OPT2 T(z) directly from Results/<case>/<case>_line.csv
(OPT cases are NOT in cases.json — they are composite recipes, not
single-variable sensitivity cases).

Output: analysis/sensitivity/sensitivity/OPT/T_z_{p1p0m,p0p5m}.png
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
REF_CSV = ROOT / "analysis" / "grid_conv" / "ref_Mesh5.csv"
BASELINE = "grid_mesh1_764327"

N_SIM   = 30
Z_SIM   = np.linspace(0.05, 2.95, N_SIM)
Z_PLOT  = np.linspace(0.0, 3.0, 16)

OPT_CASES = [
    ("sens_OPT1_combined",     "OPT1: engine_thick=0.2 + cold-walls + KAPPA0=1.0 + SOOT=0.10 + floor EXPOSED"),
    ("sens_OPT2_engine_walls", "OPT2: engine_thick=0.2 + cold-walls only"),
]


def load_ref():
    z, T = [], []
    for ln in REF_CSV.read_text().splitlines():
        if not ln.strip(): continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def load_T_z(case_id, col):
    f = RES / case_id / f"{case_id}_line.csv"
    if not f.exists(): return None
    rows = list(csv.reader(open(f)))
    if len(rows) < N_SIM + 2: return None
    hdr = [c.strip() for c in rows[1]]
    if col not in hdr: return None
    j = hdr.index(col)
    raw = np.array([float(rows[2+i][j]) for i in range(N_SIM)])
    return np.interp(Z_PLOT, Z_SIM, raw)


def load_T_z_window(case_id, offset_key, t_start, t_end):
    """SLCF-based T(z) averaged over [t_start, t_end] — for custom windows."""
    import warnings; warnings.filterwarnings("ignore")
    import logging; logging.disable(logging.CRITICAL)
    import fdsreader
    p = RES / case_id
    if not (p / f"{case_id}.smv").exists(): return None
    try:
        sim = fdsreader.Simulation(str(p))
    except Exception:
        return None
    cands = [(abs(s.extent.x_start - 8.10), s)
             for s in sim.slices
             if s.orientation == 1 and s.quantity.name == "TEMPERATURE"]
    if not cands: return None
    sl = min(cands, key=lambda t: t[0])[1]
    T = sl.to_global(masked=True, fill=np.nan)
    t_arr = sl.times
    ext = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T.shape[2])
    y_target = 2.45 if offset_key == "p1m" else 1.95
    iy = int(np.argmin(np.abs(y_arr - y_target)))
    win = (t_arr >= t_start) & (t_arr <= t_end)
    if not win.any(): return None
    T_avg = np.nanmean(T[win, iy, :], axis=0)
    return np.interp(Z_PLOT, z_arr, T_avg)


def metrics(T, base, ref):
    bands = {"low":  (Z_PLOT >= 0.0) & (Z_PLOT <= 1.0),
             "mid":  (Z_PLOT >= 1.0) & (Z_PLOT <= 2.0),
             "high": (Z_PLOT >= 2.0) & (Z_PLOT <= 3.0),
             "full": (Z_PLOT >= 0.0) & (Z_PLOT <= 3.0)}
    out = {}
    for k, mask in bands.items():
        out[f"{k}_signed"] = float((T - base)[mask].mean())
        out[f"{k}_mag"]    = float(np.abs(T - base)[mask].mean())
        out[f"{k}_paper"]  = float(np.abs(T - ref)[mask].mean())
    return out


def _load(case_id, col, offset_key, win):
    if win is None:
        return load_T_z(case_id, col)
    return load_T_z_window(case_id, offset_key, win[0], win[1])


def plot(offset_tag, col, ref_z, ref_T, out_dir, win=None):
    offset_key = "p1m" if offset_tag == "p1p0m" else "p05m"
    base_T = _load(BASELINE, col, offset_key, win)
    if base_T is None:
        print(f"  baseline {col} missing"); return

    fig, ax = plt.subplots(figsize=(11, 7))
    for zg in (1.0, 2.0):
        ax.axvline(zg, color="lightgray", lw=1.0, ls=":", zorder=0)
    ax.plot(ref_z, ref_T, "k--x", lw=2.5, ms=8,
            label="Paper (ref_Mesh5)", zorder=10)
    ax.plot(Z_PLOT, base_T, color="gray", lw=2.5, marker="s", ms=6,
            mfc="none", label="baseline (764327)", zorder=9)

    ref_interp = np.interp(Z_PLOT, ref_z, ref_T)
    colors = ["tab:red", "tab:blue", "tab:green", "tab:purple"]
    for i, (cid, lab) in enumerate(OPT_CASES):
        T = _load(cid, col, offset_key, win)
        if T is None:
            print(f"  skip {cid}: no data"); continue
        m = metrics(T, base_T, ref_interp)
        short_lab = lab.split(":")[0]   # "OPT1" / "OPT2"
        ax.plot(Z_PLOT, T, marker="o", ms=5, mfc="none", lw=1.8,
                color=colors[i % len(colors)],
                label=f"{short_lab}  (vs paper full={m['full_paper']:.1f}°C,  "
                      f"Δbase={m['full_signed']:+.1f}°C)")

    ax.set_xlabel("Height z (m)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(0, 3); ax.set_ylim(20, 300)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9, loc="upper left", framealpha=0.95)
    offset_lbl = "+1.0m" if offset_tag == "p1p0m" else "+0.5m"
    win_lbl = "" if win is None else f"  (avg t={win[0]:.0f}-{win[1]:.0f}s)"
    ax.set_title(f"OPT cases — T(z) @ {offset_lbl}{win_lbl}\n"
                 f"vertical dotted = z-band boundaries (low | mid | high)")
    fig.tight_layout()
    out_path = out_dir / f"T_z_{offset_tag}.png"
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"  wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-base",
                    default=str(ROOT / "analysis" / "sensitivity" / "sensitivity"))
    ap.add_argument("--t-start", type=float, default=None,
                    help="custom avg window start (default: use line.csv built-in avg)")
    ap.add_argument("--t-end",   type=float, default=300.0)
    args = ap.parse_args()
    out_dir = Path(args.out_base) / "OPT"
    out_dir.mkdir(parents=True, exist_ok=True)
    win = (args.t_start, args.t_end) if args.t_start is not None else None

    ref_z, ref_T = load_ref()
    plot("p1p0m", "gridconv_T_center_avg",     ref_z, ref_T, out_dir, win=win)
    plot("p0p5m", "gridconv_T_center_05m_avg", ref_z, ref_T, out_dir, win=win)

    # Console summary
    base_p1  = _load(BASELINE, "gridconv_T_center_avg",     "p1m",  win)
    base_p05 = _load(BASELINE, "gridconv_T_center_05m_avg", "p05m", win)
    ref_interp = np.interp(Z_PLOT, ref_z, ref_T)
    win_lbl = "" if win is None else f"  [t={win[0]:.0f}-{win[1]:.0f}s]"
    print(f"\n{'Case':<32} {'Offset':<6} {'low':>13} {'mid':>13} {'high':>13} {'full':>13}{win_lbl}")
    print(f"{'':32} {'':6} {'sgn|pap':>13} {'sgn|pap':>13} {'sgn|pap':>13} {'sgn|pap':>13}")
    print("-" * 90)
    for cid, lab in OPT_CASES:
        for off, col, base, ok in [("+1m",   "gridconv_T_center_avg",     base_p1,  "p1m"),
                                    ("+0.5m", "gridconv_T_center_05m_avg", base_p05, "p05m")]:
            T = _load(cid, col, ok, win)
            if T is None or base is None: continue
            m = metrics(T, base, ref_interp)
            print(f"{cid:<32} {off:<6} "
                  f"{m['low_signed']:+5.1f}|{m['low_paper']:5.1f}  "
                  f"{m['mid_signed']:+5.1f}|{m['mid_paper']:5.1f}  "
                  f"{m['high_signed']:+5.1f}|{m['high_paper']:5.1f}  "
                  f"{m['full_signed']:+5.1f}|{m['full_paper']:5.1f}")


if __name__ == "__main__":
    main()
