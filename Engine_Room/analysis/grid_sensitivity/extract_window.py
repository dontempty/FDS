#!/usr/bin/env python3
"""
Re-extract sensitivity metrics using a CUSTOM averaging window.

Uses YZ SLCF at x=8.10 (sliced per time step) instead of the line.csv built-in
average (which is fixed at t>=100).  Samples at:
    +1.0 m offset:  y = 2.45
    +0.5 m offset:  y = 1.95

Defaults: window = [200, 300] s, output suffix "_w200"

Outputs:
    analysis/sensitivity/table_summary{suffix}.csv
    analysis/sensitivity/cases{suffix}.json

Usage:
    python3 extract_window.py
    python3 extract_window.py --t-start 200 --t-end 300 --suffix _w200
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
import fdsreader

# Reuse CASES / constants from extract.py
sys.path.insert(0, str(Path(__file__).parent))
from extract import (CASES, BASELINE, REF_CSV, Z_PLOT, Z_BANDS,
                     HRR_EXPECTED, HRR_BASE,
                     load_ref, load_hrr_avg, check_completed, safe_idx)

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "sensitivity"

SLICE_X = 8.10
OFFSET_Y = {"p1m": 2.45, "p05m": 1.95}   # +1m and +0.5m


def load_T_z_window(case_id, offset_key, t_start, t_end):
    """Extract T(z) sampled at y=OFFSET_Y[offset_key], averaged over [t_start, t_end]."""
    p = RES / case_id
    if not (p / f"{case_id}.smv").exists():
        return None
    try:
        sim = fdsreader.Simulation(str(p))
    except Exception:
        return None
    cands = [(abs(s.extent.x_start - SLICE_X), s)
             for s in sim.slices
             if s.orientation == 1 and s.quantity.name == "TEMPERATURE"]
    if not cands: return None
    sl = min(cands, key=lambda t: t[0])[1]
    T = sl.to_global(masked=True, fill=np.nan)   # (n_t, n_y, n_z)
    t_arr = sl.times
    if t_arr[-1] < t_start:
        return None
    ext = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T.shape[2])
    iy = int(np.argmin(np.abs(y_arr - OFFSET_Y[offset_key])))
    win = (t_arr >= t_start) & (t_arr <= t_end)
    if not win.any():
        return None
    T_avg = np.nanmean(T[win, iy, :], axis=0)
    return np.interp(Z_PLOT, z_arr, T_avg)


def metrics_one_offset(T_z, ref_z, base_z):
    if T_z is None:
        empty = {}
        for band in Z_BANDS:
            empty[f"{band}_mean"] = empty[f"{band}_max"] = np.nan
            empty[f"delta_base_{band}"] = empty[f"signed_delta_base_{band}"] = np.nan
        empty.update({"T_floor": np.nan, "T_mid": np.nan, "T_ceil": np.nan})
        return empty
    abs_paper = np.abs(T_z - ref_z)
    out = {}
    for band, mask in Z_BANDS.items():
        out[f"{band}_mean"] = float(abs_paper[mask].mean())
        out[f"{band}_max"]  = float(abs_paper[mask].max())
        if base_z is not None:
            diff = T_z - base_z
            d_abs = np.abs(diff)
            out[f"delta_base_{band}"]        = float(d_abs[mask].mean())
            out[f"signed_delta_base_{band}"] = float(diff[mask].mean())
        else:
            out[f"delta_base_{band}"] = np.nan
            out[f"signed_delta_base_{band}"] = np.nan
    out["T_floor"] = float(T_z[safe_idx(0.1)])
    out["T_mid"]   = float(T_z[safe_idx(1.5)])
    out["T_ceil"]  = float(T_z[safe_idx(2.9)])
    return out


def extract_case(case_id, group, variable, value, ref_at, base_p1, base_p05,
                 t_start, t_end):
    completed = check_completed(case_id)
    T_p1  = load_T_z_window(case_id, "p1m",  t_start, t_end)
    T_p05 = load_T_z_window(case_id, "p05m", t_start, t_end)
    hrr   = load_hrr_avg(case_id, t_start=t_start)
    expected_hrr = HRR_EXPECTED.get(case_id, HRR_BASE)
    hrr_pct = (hrr - expected_hrr) / expected_hrr * 100 if hrr is not None else None

    if not completed:                            status = "FAIL_NOT_COMPLETED"
    elif T_p1 is None or T_p05 is None:          status = "FAIL_NO_DATA"
    elif (T_p1 == 0).all() or (T_p05 == 0).all(): status = "FAIL_AVG_ZERO"
    elif hrr_pct is not None and abs(hrr_pct) > 15: status = "FAIL_HRR_OFF"
    elif hrr_pct is not None and abs(hrr_pct) > 5:  status = "WARN_HRR"
    else: status = "OK"

    m_p1  = metrics_one_offset(T_p1,  ref_at, base_p1)
    m_p05 = metrics_one_offset(T_p05, ref_at, base_p05)

    row = {
        "case_id": case_id, "group": group, "variable": variable,
        "value": value if value is not None else "",
        "status": status,
        "hrr_expected_kw": expected_hrr,
        "hrr_avg_kw": hrr,
        "hrr_pct_err": hrr_pct,
        "window_start": t_start,
        "window_end": t_end,
    }
    for k, v in m_p1.items():  row[f"p1m_{k}"]  = v
    for k, v in m_p05.items(): row[f"p05m_{k}"] = v
    row["_T_z_p1m"]  = T_p1.tolist()  if T_p1  is not None else None
    row["_T_z_p05m"] = T_p05.tolist() if T_p05 is not None else None
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t-start", type=float, default=200.0)
    ap.add_argument("--t-end",   type=float, default=300.0)
    ap.add_argument("--suffix",  default="_w200")
    args = ap.parse_args()

    print(f"Averaging window: t = [{args.t_start}, {args.t_end}] s")
    ref_at = load_ref()
    base_p1  = load_T_z_window(BASELINE, "p1m",  args.t_start, args.t_end)
    base_p05 = load_T_z_window(BASELINE, "p05m", args.t_start, args.t_end)
    if base_p1 is None or base_p05 is None:
        print(f"WARNING: baseline {BASELINE} no data in window — Δ vs base will be NaN.")
        base_p1 = base_p05 = None

    rows = [extract_case(BASELINE, "baseline", "—", "—",
                          ref_at, base_p1, base_p05,
                          args.t_start, args.t_end)]
    for case_id, grp, var, val in CASES:
        rows.append(extract_case(case_id, grp, var, val, ref_at, base_p1, base_p05,
                                  args.t_start, args.t_end))

    csv_path = OUT / f"table_summary{args.suffix}.csv"
    flat_keys = [k for k in rows[0].keys() if not k.startswith("_")]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat_keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in flat_keys})
    print(f"wrote {csv_path}")

    json_path = OUT / f"cases{args.suffix}.json"
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"wrote {json_path}")

    print(f"\n{'Case':<40} {'Stat':<10} "
          f"{'+1m low':>8} {'mid':>7} {'high':>7} {'full':>7} "
          f"{'Δ_full':>8} {'HRR%':>6}")
    print("-" * 100)
    for r in rows:
        stat = r["status"].replace("FAIL_","F_").replace("WARN_","W_")
        hp = r.get("hrr_pct_err")
        hp_s = f"{hp:+5.1f}" if hp is not None else "  ---"
        try:
            print(f"{r['case_id']:<40} {stat:<10} "
                  f"{r['p1m_low_mean']:>8.2f} {r['p1m_mid_mean']:>7.2f} "
                  f"{r['p1m_high_mean']:>7.2f} {r['p1m_full_mean']:>7.2f} "
                  f"{r['p1m_delta_base_full']:>8.2f} {hp_s:>6}")
        except (KeyError, TypeError, ValueError):
            print(f"{r['case_id']:<40} {stat:<10}  (no data)")

    from collections import Counter
    print(f"\nStatus summary: {dict(Counter(r['status'] for r in rows))}")


if __name__ == "__main__":
    main()
