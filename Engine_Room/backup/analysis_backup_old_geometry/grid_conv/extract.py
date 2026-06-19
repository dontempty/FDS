#!/usr/bin/env python3
"""
Extract Lan et al. 2023 §3.3 grid-convergence T(z) data from FDS _line.csv
outputs.

Paper specifies "1 m from fire source in y-direction" without sign or
reference (centre vs edge).  We emit three vertical lines:
    gridconv_T          = centre +1 m, y = cy + 1.0           (in OSR)
    gridconv_T_neg      = centre -1 m, y = cy - 1.0           (in OSR)
    gridconv_T_edge_pos = edge   +1 m, y = fire_y_max + 1 - δ (2 cm before
                          OSR-MER divider wall, still inside OSR gas)

For each Results/grid_mesh{N}_*/ directory:
    - read *_line.csv
    - extract gridconv_T, gridconv_T_neg, gridconv_T_edge_pos columns
    - z values computed from DEVC definition (0.05..2.95, 30 pts, dz=0.1)

Outputs in this dir:
    gridconv_T_pos.csv          z, mesh1, mesh3, ...   (centre +y line)
    gridconv_T_neg.csv          z, mesh1, mesh3, ...   (centre -y line)
    gridconv_T_edge_pos.csv     z, mesh1, mesh3, ...   (edge   +y line)
    summary.txt                 per-mesh stats + pairwise deviation
    cases.txt                   list of source result dirs

Cases whose gridconv_T_* column is all-zero (run not finished) are skipped.
Old runs that do not contain a column simply contribute to the CSVs they
do have data for.
"""
from __future__ import annotations
import csv
import re
import sys
from pathlib import Path

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RESULTS = ROOT / "Results"
OUT = ROOT / "analysis" / "grid_conv"
OUT.mkdir(parents=True, exist_ok=True)

N_POINTS = 30

# Per-DEVC vertical z grid -- must match gen_engine_room.py emission ranges.
#   gridconv_T_center : z=[0.05, 2.95]  -> dz ≈ 0.100 m  (OSR gas, full column)
#   gridconv_T_edge   : z=[0.05, 1.95]  -> dz ≈ 0.066 m  (door void only)
LINE_INFO = {
    "gridconv_T_center": dict(z_lo=0.05, z_hi=2.95, label="center+y"),
    "gridconv_T_edge":   dict(z_lo=0.05, z_hi=1.95, label="edge+y"),
}
LINE_IDS = list(LINE_INFO.keys())


def z_grid(did: str) -> list[float]:
    info = LINE_INFO[did]
    z_lo, z_hi = info["z_lo"], info["z_hi"]
    return [z_lo + i * (z_hi - z_lo) / (N_POINTS - 1) for i in range(N_POINTS)]


def find_cases() -> list[tuple[int, Path]]:
    """Return [(mesh_no, devc_dir), ...] sorted by mesh_no, latest JOBID per mesh."""
    pat = re.compile(r"^grid_mesh(\d+)_(\d+)$")
    bymesh: dict[int, tuple[int, Path]] = {}
    for d in RESULTS.iterdir():
        if not d.is_dir():
            continue
        m = pat.match(d.name)
        if not m:
            continue
        mesh, job = int(m.group(1)), int(m.group(2))
        if mesh not in bymesh or job > bymesh[mesh][0]:
            bymesh[mesh] = (job, d)
    return sorted([(m, p) for m, (_, p) in bymesh.items()])


def read_columns(line_csv: Path, ids: list[str]) -> dict[str, list[float]]:
    """Return {id: [N_POINTS floats]} for each requested DEVC id present in the
    file.  Missing IDs are simply absent from the returned dict."""
    with open(line_csv) as f:
        rows = list(csv.reader(f))
    if len(rows) < 2 + N_POINTS:
        raise RuntimeError(f"{line_csv}: only {len(rows)} rows, need ≥{2+N_POINTS}")
    names = [c.strip() for c in rows[1]]
    out: dict[str, list[float]] = {}
    for did in ids:
        if did not in names:
            continue
        j = names.index(did)
        vals: list[float] = []
        for r in rows[2:2 + N_POINTS]:
            try:
                vals.append(float(r[j].strip()))
            except (ValueError, IndexError):
                vals.append(float("nan"))
        out[did] = vals
    return out


def deviation_stats(ref: list[float], other: list[float]) -> tuple[float, float]:
    """Return (mean_dev_%, max_dev_%) pointwise vs ref (skipping ref==0)."""
    devs = []
    for r, o in zip(ref, other):
        if r == 0:
            continue
        devs.append(abs(o - r) / abs(r) * 100)
    if not devs:
        return float("nan"), float("nan")
    return sum(devs) / len(devs), max(devs)


def write_wide_csv(path: Path, columns: dict[int, list[float]],
                   label_prefix: str, z: list[float]) -> None:
    """columns = {mesh_no: [30 floats]}, sorted by key.  z = z-grid for this DEVC."""
    meshes = sorted(columns)
    with open(path, "w") as f:
        f.write("z_m," + ",".join(f"{label_prefix}_mesh{m}" for m in meshes) + "\n")
        for i in range(N_POINTS):
            row = [f"{z[i]:.4f}"] + [f"{columns[m][i]:.3f}" for m in meshes]
            f.write(",".join(row) + "\n")


def main() -> None:
    cases = find_cases()
    if not cases:
        sys.exit(f"ERROR: no grid_mesh*_<JOBID> dirs under {RESULTS}")

    # Per-line collected data:  {line_id: {mesh_no: [30 floats]}}
    perline: dict[str, dict[int, list[float]]] = {lid: {} for lid in LINE_IDS}
    cases_log: list[str] = []

    for mesh, d in cases:
        line_csv = d / f"{d.name}_line.csv"
        if not line_csv.exists():
            print(f"Mesh {mesh}: skip — no _line.csv")
            continue
        try:
            cols = read_columns(line_csv, LINE_IDS)
        except RuntimeError as e:
            print(f"Mesh {mesh}: skip — {e}")
            continue
        if not cols:
            print(f"Mesh {mesh}: skip — no gridconv_T* columns in CSV")
            continue
        kept: list[str] = []
        for lid, vals in cols.items():
            if max(vals) == 0.0 and min(vals) == 0.0:
                continue                                # job still running
            perline[lid][mesh] = vals
            kept.append(f"{lid}: min={min(vals):.1f} max={max(vals):.1f}")
        if not kept:
            print(f"Mesh {mesh}: skip — all gridconv_T* columns all-zero (still running?)")
            continue
        cases_log.append(f"Mesh {mesh}: {d.name}")
        print(f"Mesh {mesh}  ({d.name}):")
        for line in kept:
            print(f"    {line}")

    if not any(perline.values()):
        sys.exit("ERROR: no usable data extracted")

    # ---- write wide CSVs (one per DEVC)
    for lid in LINE_IDS:
        if perline[lid]:
            out_path = OUT / f"{lid}.csv"
            write_wide_csv(out_path, perline[lid],
                           LINE_INFO[lid]["label"], z_grid(lid))
            print(f"\nwrote {out_path}")

    # ---- summary
    summ_lines: list[str] = ["Lan et al. 2023 §3.3 grid-convergence T(z) summary",
                             ""]
    for lid in LINE_IDS:
        cols = perline[lid]
        if not cols:
            continue
        z = z_grid(lid)
        z_lo, z_hi = LINE_INFO[lid]['z_lo'], LINE_INFO[lid]['z_hi']
        summ_lines.append(f"### {lid}  ({LINE_INFO[lid]['label']}, "
                          f"z=[{z_lo:.2f}, {z_hi:.2f}], dz={z[1]-z[0]:.4f})")
        summ_lines.append(f"{'Mesh':<6}{'min':>10}{'mean':>10}{'max':>10}"
                          f"{'T(z=lo)':>12}{'T(z=mid)':>12}{'T(z=hi)':>12}")
        for m in sorted(cols):
            v = cols[m]
            summ_lines.append(f"{m:<6}{min(v):>10.2f}{sum(v)/len(v):>10.2f}{max(v):>10.2f}"
                              f"{v[0]:>12.2f}{v[15]:>12.2f}{v[29]:>12.2f}")
        # pairwise deviation vs finest
        ref = sorted(cols)[-1]
        summ_lines.append("")
        summ_lines.append(f"  Point-wise % deviation vs Mesh {ref} (finest available):")
        summ_lines.append(f"  {'Mesh':<6}{'mean_dev_%':>12}{'max_dev_%':>12}")
        for m in sorted(cols):
            if m == ref:
                continue
            mean_d, max_d = deviation_stats(cols[ref], cols[m])
            summ_lines.append(f"  {m:<6}{mean_d:>12.2f}{max_d:>12.2f}")
        summ_lines.append("")

    (OUT / "summary.txt").write_text("\n".join(summ_lines) + "\n")
    print(f"wrote {OUT / 'summary.txt'}")

    (OUT / "cases.txt").write_text("\n".join(cases_log) + "\n")


if __name__ == "__main__":
    main()
