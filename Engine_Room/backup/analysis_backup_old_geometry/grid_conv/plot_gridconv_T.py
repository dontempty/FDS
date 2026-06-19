#!/usr/bin/env python3
"""
Plot gridconv vertical T(z) profiles for one or more grid_mesh{N}_<JOBID>
runs against Lan et al. 2023 Fig 5 reference.

For each run the four DEVCs are plotted:
    gridconv_T_center        instantaneous T(z), x=8.25, y=2.45 (centre+1m, OSR)
    gridconv_T_center_avg    time-averaged T(z) since STATISTICS_START=100 s
    gridconv_T_edge          instantaneous T(z), x=8.25, y=2.893 (edge+1m,
                             *inside* door void — anomalous)
    gridconv_T_edge_avg      time-averaged "

CLI:
    python3 plot_gridconv_T.py                     # auto: latest run per mesh
    python3 plot_gridconv_T.py grid_mesh1_756422   # one specific case
    python3 plot_gridconv_T.py grid_mesh1_756422 grid_mesh1_756526   # compare

Output (next to this script):
    gridconv_T_<dirstems>.png
"""
from __future__ import annotations
import csv
import re
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT    = Path("/scratch/x3319a05/fds/Engine_Room")
RESULTS = ROOT / "Results"
OUT_DIR = Path(__file__).parent

N_POINTS = 30
LINE_INFO = {
    # time-averaged only; offset labelled in the legend
    "gridconv_T_center_avg":      dict(z_lo=0.05, z_hi=2.95, off="+1.0m"),
    "gridconv_T_center_05m_avg":  dict(z_lo=0.05, z_hi=2.95, off="+0.5m"),
    "gridconv_T_center_n05m_avg": dict(z_lo=0.05, z_hi=2.95, off="-0.5m"),
    "gridconv_T_center_n10m_avg": dict(z_lo=0.05, z_hi=2.95, off="-1.0m"),
}

# Lan et al. 2023 Fig 5 reference — loaded from ref.csv (z, T per line)
REF_CSV = Path(__file__).parent / "ref.csv"


def load_reference():
    if not REF_CSV.exists():
        sys.exit(f"missing reference data: {REF_CSV}")
    z, T = [], []
    for line in REF_CSV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        a, b = line.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def z_grid(did):
    info = LINE_INFO[did]
    return np.linspace(info["z_lo"], info["z_hi"], N_POINTS)


def read_columns(line_csv: Path):
    with open(line_csv) as f:
        rows = list(csv.reader(f))
    if len(rows) < 2 + N_POINTS:
        raise RuntimeError(f"{line_csv}: only {len(rows)} rows")
    names = [c.strip() for c in rows[1]]
    out = {}
    for did in LINE_INFO:
        if did not in names:
            continue
        j = names.index(did)
        vals = []
        for r in rows[2:2 + N_POINTS]:
            try:
                vals.append(float(r[j].strip()))
            except (ValueError, IndexError):
                vals.append(float("nan"))
        if max(vals) == 0 and min(vals) == 0:
            continue   # job still running, column empty
        out[did] = np.asarray(vals)
    return out


def resolve_case(arg: str) -> Path:
    p = RESULTS / arg
    if p.is_dir():
        return p
    # try wildcard prefix match
    candidates = sorted(RESULTS.glob(arg + "*"))
    if len(candidates) == 1:
        return candidates[0]
    sys.exit(f"ambiguous or missing case: {arg} (candidates: {candidates})")


ALLOWED_MESHES = (1, 3)   # restrict default auto-pick to these meshes only


def auto_pick():
    """Latest grid_mesh{N}_<JOB> per N, restricted to ALLOWED_MESHES.
    Excludes sign-test variants (chid contains 'sign')."""
    pat = re.compile(r"^grid_mesh(\d+)_(\d+)$")     # strict — no signpos/signneg
    bymesh = {}
    for d in RESULTS.iterdir():
        if not d.is_dir(): continue
        m = pat.match(d.name)
        if not m: continue
        mesh, job = int(m.group(1)), int(m.group(2))
        if mesh not in ALLOWED_MESHES: continue
        if mesh not in bymesh or job > bymesh[mesh][0]:
            bymesh[mesh] = (job, d)
    return [p for _, p in sorted(bymesh.values(), key=lambda x: x[1].name)]


def main():
    cases = ([resolve_case(a) for a in sys.argv[1:]]
             if len(sys.argv) > 1 else auto_pick())
    if not cases:
        sys.exit("no cases found")

    # --- per-case data
    series = []   # list of (case_label, dict of did->vals)
    for d in cases:
        line_csv = d / f"{d.name}_line.csv"
        if not line_csv.exists():
            print(f"skip {d.name}: no _line.csv"); continue
        try:
            cols = read_columns(line_csv)
        except RuntimeError as e:
            print(f"skip {d.name}: {e}"); continue
        if not cols:
            print(f"skip {d.name}: all gridconv_T* columns empty"); continue
        # short label: mesh + last 4 of JOBID
        m = re.match(r"^grid_mesh(\d+)_(\d+)$", d.name)
        if m:
            label = f"M{m.group(1)} (…{m.group(2)[-4:]})"
        else:
            label = d.name
        series.append((label, cols))
        print(f"loaded {d.name}: {list(cols.keys())}")

    if not series:
        sys.exit("no usable data")

    # --- plot
    fig, ax = plt.subplots(figsize=(10, 7))

    # palette per run; line style per offset
    cmap = plt.get_cmap("tab10")
    OFFSET_STYLE = {
        "+1.0m": dict(marker="o", linestyle="-",  lw=1.4),
        "+0.5m": dict(marker="s", linestyle=":",  lw=1.4),
        "-0.5m": dict(marker="^", linestyle="--", lw=1.4),
        "-1.0m": dict(marker="v", linestyle="-.", lw=1.4),
    }

    for i, (case_label, cols) in enumerate(series):
        color = cmap(i % 10)
        for did, vals in cols.items():
            info = LINE_INFO[did]
            z = z_grid(did)
            s = OFFSET_STYLE.get(info["off"], dict(linestyle="-"))
            ax.plot(z, vals, color=color, ms=4, mfc="none",
                    label=f"{case_label} · {info['off']}", **s)

    # paper reference (Lan 2023 Fig 5) from ref.csv
    ref_z, ref_T = load_reference()
    ax.plot(ref_z, ref_T, "k--x", lw=2, ms=7, label="Reference (Lan 2023, Fig 5)")

    ax.set_xlabel("Height z (m)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xlim(0, 3.0)
    ax.set_ylim(20, 340)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=1, loc="upper left", framealpha=0.95)
    ax.set_title("T(z) center ±{0.5, 1.0} m (y-offset from fire centre), "
                 "time-avg 100→300 s",
                 fontsize=10)

    stems = "_".join(d.name.split("_")[-1][-4:] for d in cases if (d / f"{d.name}_line.csv").exists())
    out_png = OUT_DIR / f"gridconv_T_{stems}.png"
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    print(f"\nwrote {out_png}")


if __name__ == "__main__":
    main()
