#!/usr/bin/env python3
"""
Phase 1 + 2.1: Extract metrics from all sensitivity cases + baseline.

NEW: T(z) error is decomposed into FOUR z-ranges:
    low    z ∈ [0.0, 1.0]
    mid    z ∈ [1.0, 2.0]
    high   z ∈ [2.0, 3.0]
    full   z ∈ [0.0, 3.0]

Outputs:
    analysis/sensitivity/table_summary.csv  — machine-readable
    analysis/sensitivity/cases.json         — same data, with T(z) arrays

Usage:
    python3 analysis/sensitivity/extract.py
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
import numpy as np

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "sensitivity"
OUT.mkdir(parents=True, exist_ok=True)
REF_CSV = ROOT / "analysis" / "grid_conv" / "ref_Mesh5.csv"

N_SIM   = 30
Z_SIM   = np.linspace(0.05, 2.95, N_SIM)
Z_PLOT  = np.linspace(0.0, 3.0, 16)
Z_BANDS = {
    "low":  (Z_PLOT >= 0.0) & (Z_PLOT <= 1.0),
    "mid":  (Z_PLOT >= 1.0) & (Z_PLOT <= 2.0),
    "high": (Z_PLOT >= 2.0) & (Z_PLOT <= 3.0),
    "full": (Z_PLOT >= 0.0) & (Z_PLOT <= 3.0),
}

# New baseline (M1 with fire/door at x=7.5-8.5, fixed slices)
BASELINE = "grid_mesh1_764327"

# (case_id, group, variable, value)
CASES = [
    # Group A: Fire chemistry / radiation
    ("sens_A1a_kappa_0p5",          "A", "KAPPA0",            0.5),
    ("sens_A1b_kappa_1p0",          "A", "KAPPA0",            1.0),
    ("sens_A1c_kappa_2p5",          "A", "KAPPA0",            2.5),
    ("sens_A1d_kappa_3p0",          "A", "KAPPA0",            3.0),
    ("sens_A2a_radfrac_0p2",        "A", "RAD_FRAC",          0.2),
    ("sens_A2b_radfrac_0p4",        "A", "RAD_FRAC",          0.4),
    ("sens_A3a_soot_0p02",          "A", "SOOT",              0.02),
    ("sens_A3b_soot_0p10",          "A", "SOOT",              0.10),
    ("sens_A4a_hrr_700",            "A", "HRR",               700),
    ("sens_A4b_hrr_1100",           "A", "HRR",               1100),
    # Group B: Floor / ceiling
    ("sens_B1a_floor_thick_0p005",  "B", "floor_thick",       0.005),
    ("sens_B1b_floor_thick_0p05",   "B", "floor_thick",       0.05),
    ("sens_B1c_floor_thick_0p2",    "B", "floor_thick",       0.2),
    ("sens_B2_floor_backing_exposed","B", "floor_backing",   "EXPOSED"),
    ("sens_B3_floor_coldsink20",    "B", "floor_model",       "isothermal_20"),
    # Group C: osr_north_wall divider
    ("sens_C1a_divider_thick_0p05", "C", "divider_thick",     0.05),
    ("sens_C1b_divider_thick_0p5",  "C", "divider_thick",     0.5),
    ("sens_C2_divider_backing_insulated", "C", "divider_backing", "INSULATED"),
    ("sens_C3_divider_inert",       "C", "divider_model",     "INERT"),
    # Group D: Interior partition walls
    ("sens_D1_walls_insulated_steel","D", "walls_model",      "INSULATED_steel"),
    ("sens_D2_walls_coldsink20",    "D", "walls_model",       "isothermal_20"),
    ("sens_D3_walls_exposed_steel", "D", "walls_model",       "EXPOSED_steel_0.2m"),
    # Group E: Engine + equipment
    ("sens_E1_engine_tmp20",        "E", "engine_model",      "isothermal_20"),
    ("sens_E2a_engine_thick_0p001", "E", "engine_thick",      0.001),
    ("sens_E2b_engine_thick_0p05",  "E", "engine_thick",      0.05),
    ("sens_E2c_engine_thick_0p2",   "E", "engine_thick",      0.2),
    ("sens_E3_engine_backing_exposed","E", "engine_backing",  "EXPOSED"),
]

HRR_EXPECTED = {"sens_A4a_hrr_700": 700, "sens_A4b_hrr_1100": 1100}
HRR_BASE = 863


def load_ref():
    z, T = [], []
    for ln in REF_CSV.read_text().splitlines():
        if not ln.strip(): continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.interp(Z_PLOT, np.asarray(z), np.asarray(T))


def load_T_z(case_id, col):
    f = RES / case_id / f"{case_id}_line.csv"
    if not f.exists(): return None
    try:
        rows = list(csv.reader(open(f)))
    except Exception:
        return None
    if len(rows) < N_SIM + 2: return None
    hdr = [c.strip() for c in rows[1]]
    if col not in hdr: return None
    j = hdr.index(col)
    try:
        raw = np.array([float(rows[2+i][j]) for i in range(N_SIM)])
    except (IndexError, ValueError):
        return None
    return np.interp(Z_PLOT, Z_SIM, raw)


def load_hrr_avg(case_id, t_start=100.0):
    f = RES / case_id / f"{case_id}_hrr.csv"
    if not f.exists(): return None
    try:
        rows = list(csv.reader(open(f)))
    except Exception:
        return None
    if len(rows) < 3: return None
    hdr = [c.strip() for c in rows[1]]
    if "HRR" not in hdr or "Time" not in hdr: return None
    jt, jh = hdr.index("Time"), hdr.index("HRR")
    ts, hs = [], []
    for row in rows[2:]:
        try:
            t = float(row[jt]); h = float(row[jh])
            if t >= t_start:
                ts.append(t); hs.append(h)
        except (ValueError, IndexError):
            continue
    if not hs: return None
    return float(np.mean(hs))


def check_completed(case_id):
    f = RES / case_id / f"{case_id}.out"
    if not f.exists(): return False
    try:
        last_lines = f.read_text().strip().split("\n")[-5:]
        return any("STOP: FDS completed successfully" in ln for ln in last_lines)
    except Exception:
        return False


def safe_idx(z_target):
    return int(np.argmin(np.abs(Z_PLOT - z_target)))


def metrics_one_offset(T_z, ref_z, base_z):
    """For each z-band: mean|ΔT| & max|ΔT| vs paper; Δ vs baseline mean.
    Also reports T at floor / mid-room / ceiling for diagnostic."""
    if T_z is None:
        empty = {}
        for band in Z_BANDS:
            empty[f"{band}_mean"] = empty[f"{band}_max"] = np.nan
            empty[f"delta_base_{band}"] = np.nan
        empty.update({"T_floor": np.nan, "T_mid": np.nan, "T_ceil": np.nan})
        return empty

    abs_paper = np.abs(T_z - ref_z)
    out = {}
    for band, mask in Z_BANDS.items():
        out[f"{band}_mean"] = float(abs_paper[mask].mean())
        out[f"{band}_max"]  = float(abs_paper[mask].max())
        if base_z is not None:
            diff = T_z - base_z       # signed
            d_abs = np.abs(diff)
            out[f"delta_base_{band}"]        = float(d_abs[mask].mean())   # magnitude
            out[f"signed_delta_base_{band}"] = float(diff[mask].mean())    # signed (direction)
        else:
            out[f"delta_base_{band}"]        = np.nan
            out[f"signed_delta_base_{band}"] = np.nan
    out["T_floor"] = float(T_z[safe_idx(0.1)])
    out["T_mid"]   = float(T_z[safe_idx(1.5)])
    out["T_ceil"]  = float(T_z[safe_idx(2.9)])
    return out


def extract_case(case_id, group, variable, value, ref_at, base_p1, base_p05):
    completed = check_completed(case_id)
    T_p1  = load_T_z(case_id, "gridconv_T_center_avg")
    T_p05 = load_T_z(case_id, "gridconv_T_center_05m_avg")
    hrr   = load_hrr_avg(case_id)

    expected_hrr = HRR_EXPECTED.get(case_id, HRR_BASE)
    if hrr is None or expected_hrr == 0:
        hrr_pct = None
    else:
        hrr_pct = (hrr - expected_hrr) / expected_hrr * 100

    if not completed:
        status = "FAIL_NOT_COMPLETED"
    elif T_p1 is None or T_p05 is None:
        status = "FAIL_NO_DATA"
    elif (T_p1 == 0).all() or (T_p05 == 0).all():
        status = "FAIL_AVG_ZERO"
    elif hrr_pct is not None and abs(hrr_pct) > 15:
        status = "FAIL_HRR_OFF"
    elif hrr_pct is not None and abs(hrr_pct) > 5:
        status = "WARN_HRR"
    else:
        status = "OK"

    m_p1  = metrics_one_offset(T_p1,  ref_at, base_p1)
    m_p05 = metrics_one_offset(T_p05, ref_at, base_p05)

    row = {
        "case_id": case_id, "group": group, "variable": variable,
        "value": value if value is not None else "",
        "status": status,
        "hrr_expected_kw": expected_hrr,
        "hrr_avg_kw": hrr,
        "hrr_pct_err": hrr_pct,
    }
    for k, v in m_p1.items():  row[f"p1m_{k}"]  = v
    for k, v in m_p05.items(): row[f"p05m_{k}"] = v
    row["_T_z_p1m"]  = T_p1.tolist()  if T_p1  is not None else None
    row["_T_z_p05m"] = T_p05.tolist() if T_p05 is not None else None
    return row


def main():
    ref_at = load_ref()
    base_p1  = load_T_z(BASELINE, "gridconv_T_center_avg")
    base_p05 = load_T_z(BASELINE, "gridconv_T_center_05m_avg")
    if base_p1 is None or base_p05 is None:
        print(f"WARNING: baseline {BASELINE} not yet complete — Δ vs base will be NaN.")
        base_p1 = base_p05 = None

    rows = [extract_case(BASELINE, "baseline", "—", "—",
                         ref_at, base_p1, base_p05)]
    for case_id, grp, var, val in CASES:
        rows.append(extract_case(case_id, grp, var, val, ref_at, base_p1, base_p05))

    csv_path = OUT / "table_summary.csv"
    flat_keys = [k for k in rows[0].keys() if not k.startswith("_")]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat_keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in flat_keys})
    print(f"wrote {csv_path}")

    json_path = OUT / "cases.json"
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
        print(f"{r['case_id']:<40} {stat:<10} "
              f"{r['p1m_low_mean']:>8.2f} {r['p1m_mid_mean']:>7.2f} "
              f"{r['p1m_high_mean']:>7.2f} {r['p1m_full_mean']:>7.2f} "
              f"{r['p1m_delta_base_full']:>8.2f} {hp_s:>6}")

    from collections import Counter
    cnt = Counter(r["status"] for r in rows)
    print(f"\nStatus summary: {dict(cnt)}")


if __name__ == "__main__":
    main()
