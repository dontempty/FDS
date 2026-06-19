#!/usr/bin/env python3
"""
Aggregate 27 sensitivity cases + baseline, produce comparison tables and plots.
Each case = baseline + ONE variable changed.
"""
import csv, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "sensitivity"
OUT.mkdir(parents=True, exist_ok=True)
REF_CSV = ROOT / "analysis" / "grid_conv" / "ref.csv"

N_SIM = 30
Z_SIM = np.linspace(0.05, 2.95, N_SIM)
Z_PLOT = np.linspace(0.0, 3.0, 16)
MID = (Z_PLOT >= 0.95) & (Z_PLOT <= 2.45)

BASELINE = "grid_mesh1_759273"

# (case_id, short label, group)
CASES = [
    # Group A: Fire chemistry / radiation
    ("sens_A1a_kappa_0p5",          "KAPPA0=0.5",                   "A"),
    ("sens_A1b_kappa_1p0",          "KAPPA0=1.0",                   "A"),
    ("sens_A1c_kappa_2p5",          "KAPPA0=2.5",                   "A"),
    ("sens_A1d_kappa_3p0",          "KAPPA0=3.0",                   "A"),
    ("sens_A2a_radfrac_0p2",        "RAD_FRAC=0.2",                 "A"),
    ("sens_A2b_radfrac_0p4",        "RAD_FRAC=0.4",                 "A"),
    ("sens_A3a_soot_0p02",          "SOOT=0.02",                    "A"),
    ("sens_A3b_soot_0p10",          "SOOT=0.10",                    "A"),
    ("sens_A4a_hrr_700",            "HRR=700 kW",                   "A"),
    ("sens_A4b_hrr_1100",           "HRR=1100 kW",                  "A"),
    # Group B: Floor / ceiling
    ("sens_B1a_floor_thick_0p005",  "floor_thick=0.005",            "B"),
    ("sens_B1b_floor_thick_0p05",   "floor_thick=0.05",             "B"),
    ("sens_B1c_floor_thick_0p2",    "floor_thick=0.2",              "B"),
    ("sens_B2_floor_backing_exposed","floor BACKING=EXPOSED",       "B"),
    ("sens_B3_floor_coldsink20",    "floor=20°C cold sink",         "B"),
    # Group C: osr_north_wall divider
    ("sens_C1a_divider_thick_0p05", "divider_thick=0.05",           "C"),
    ("sens_C1b_divider_thick_0p5",  "divider_thick=0.5",            "C"),
    ("sens_C2_divider_backing_insulated", "divider BACKING=INSULATED", "C"),
    ("sens_C3_divider_inert",       "divider=INERT",                "C"),
    # Group D: Interior partition walls
    ("sens_D1_walls_insulated_steel","walls INSULATED steel",       "D"),
    ("sens_D2_walls_coldsink20",    "walls=20°C cold sink",         "D"),
    ("sens_D3_walls_exposed_steel", "walls EXPOSED steel 0.2m",     "D"),
    # Group E: Engine + equipment
    ("sens_E1_engine_tmp20",        "engine=20°C cold sink",        "E"),
    ("sens_E2a_engine_thick_0p001", "engine_thick=0.001",           "E"),
    ("sens_E2b_engine_thick_0p05",  "engine_thick=0.05",            "E"),
    ("sens_E2c_engine_thick_0p2",   "engine_thick=0.2",             "E"),
    ("sens_E3_engine_backing_exposed","engine BACKING=EXPOSED",     "E"),
]

GROUP_COLOR = {"A": "tab:red", "B": "tab:orange", "C": "tab:green",
               "D": "tab:blue", "E": "tab:purple"}


def load_avg(case_id, col):
    f = RES / case_id / f"{case_id}_line.csv"
    if not f.exists(): return None
    rows = list(csv.reader(open(f)))
    hdr = [c.strip() for c in rows[1]]
    if col not in hdr: return None
    j = hdr.index(col)
    try:
        raw = np.array([float(rows[2+i][j]) for i in range(N_SIM)])
    except (IndexError, ValueError):
        return None
    return np.interp(Z_PLOT, Z_SIM, raw)


def load_ref():
    z, T = [], []
    for ln in REF_CSV.read_text().splitlines():
        if not ln.strip(): continue
        a, b = ln.split(",")
        z.append(float(a)); T.append(float(b))
    return np.interp(Z_PLOT, np.asarray(z), np.asarray(T))


def main():
    ref_at = load_ref()
    base_p1 = load_avg(BASELINE, "gridconv_T_center_avg")
    base_p05 = load_avg(BASELINE, "gridconv_T_center_05m_avg")
    if base_p1 is None or base_p05 is None:
        sys.exit(f"baseline {BASELINE} missing _avg data")

    rows = []
    for case_id, lbl, grp in CASES:
        v1 = load_avg(case_id, "gridconv_T_center_avg")
        v05 = load_avg(case_id, "gridconv_T_center_05m_avg")
        if v1 is None or v05 is None:
            rows.append((case_id, lbl, grp, None, None, None, None))
            continue
        # vs paper
        e1_paper = float(np.mean(np.abs(v1[MID] - ref_at[MID])))
        e05_paper = float(np.mean(np.abs(v05[MID] - ref_at[MID])))
        # delta vs baseline
        d1_base = float(np.mean(np.abs(v1[MID] - base_p1[MID])))
        d05_base = float(np.mean(np.abs(v05[MID] - base_p05[MID])))
        rows.append((case_id, lbl, grp, e1_paper, e05_paper, d1_base, d05_base))

    # ---- TEXT TABLE ----
    print(f"{'Case':<35} {'+1m vs paper':>13} {'+0.5m vs paper':>15} "
          f"{'+1m Δ vs base':>14} {'+0.5m Δ vs base':>15}")
    print("-" * 95)
    print(f"{'baseline (759273)':<35} "
          f"{float(np.mean(np.abs(base_p1[MID]-ref_at[MID]))):>13.2f} "
          f"{float(np.mean(np.abs(base_p05[MID]-ref_at[MID]))):>15.2f} "
          f"{'  0.00':>14} {'  0.00':>15}")
    for case_id, lbl, grp, e1, e05, d1, d05 in rows:
        if e1 is None:
            print(f"{lbl:<35} {'(missing)':>13}")
            continue
        print(f"{lbl:<35} {e1:>13.2f} {e05:>15.2f} {d1:>14.2f} {d05:>15.2f}")

    # ---- BAR CHART (Δ vs baseline) ----
    valid = [r for r in rows if r[3] is not None]
    valid_sorted_p1 = sorted(valid, key=lambda r: r[5], reverse=True)
    valid_sorted_p05 = sorted(valid, key=lambda r: r[6], reverse=True)

    for off, key, sorted_rows in [("+1.0m", 5, valid_sorted_p1),
                                  ("+0.5m", 6, valid_sorted_p05)]:
        fig, ax = plt.subplots(figsize=(10, max(6, 0.35 * len(sorted_rows))))
        labels = [r[1] for r in sorted_rows]
        vals = [r[key] for r in sorted_rows]
        colors = [GROUP_COLOR[r[2]] for r in sorted_rows]
        ax.barh(range(len(vals)), vals, color=colors)
        ax.set_yticks(range(len(vals)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel(f"Δ mean |T_case − T_baseline| at {off} (°C)")
        ax.set_title(f"Sensitivity ranking at {off} sensor (T_END=300s, M1)")
        # legend for groups
        from matplotlib.patches import Patch
        legend = [Patch(facecolor=GROUP_COLOR[g], label=lab)
                  for g, lab in [("A","A: Fire chem/rad"),("B","B: Floor/ceiling"),
                                 ("C","C: Divider"),("D","D: Walls"),
                                 ("E","E: Engine")]]
        ax.legend(handles=legend, loc="lower right", fontsize=8)
        ax.grid(axis="x", alpha=0.3)
        tag = off.replace("+","p").replace(".","p")
        fp = OUT / f"sensitivity_bars_{tag}.png"
        fig.tight_layout(); fig.savefig(fp, dpi=140); plt.close(fig)
        print(f"wrote {fp}")

    # ---- T(z) overlay per group ----
    ref_z = np.linspace(0, 3, 16)
    for grp in ["A","B","C","D","E"]:
        for off, col_suffix in [("+1.0m","_center"), ("+0.5m","_center_05m")]:
            fig, ax = plt.subplots(figsize=(9, 7))
            ax.plot(ref_z, ref_at, "k--x", lw=2.5, ms=7, label="Paper ref", zorder=10)
            ax.plot(Z_PLOT, (base_p1 if off=="+1.0m" else base_p05),
                    color="gray", lw=2.5, marker="s", ms=5, mfc="none",
                    label="baseline (759273)", zorder=9)
            for case_id, lbl, g in [(c[0],c[1],c[2]) for c in CASES if c[2]==grp]:
                col = f"gridconv_T{col_suffix}_avg"
                v = load_avg(case_id, col)
                if v is None: continue
                ax.plot(Z_PLOT, v, marker="o", ms=4, mfc="none", lw=1.4, label=lbl)
            ax.set_xlabel("Height z (m)"); ax.set_ylabel("Temperature (°C)")
            ax.set_xlim(0,3); ax.set_ylim(20,300); ax.grid(alpha=0.3)
            ax.legend(fontsize=8, loc="upper left", framealpha=0.95)
            ax.set_title(f"Group {grp} variants — T(z) at fire centre {off} in y")
            tag = off.replace("+","p").replace(".","p")
            fp = OUT / f"T_z_group_{grp}_{tag}.png"
            fig.tight_layout(); fig.savefig(fp, dpi=140); plt.close(fig)
            print(f"wrote {fp}")


if __name__ == "__main__":
    main()
