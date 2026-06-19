#!/usr/bin/env python3
"""
Reproduce Lan et al. 2023 Figs 9, 10, 12 from the CSV files emitted by
extract_flame.py.

Input CSVs (in --data-dir, default = this script's directory):

    fig9_data.csv
        Time-series for Method 1 flame-region diagnostics plus Ly(t) for
        Methods 2 and 3.
        Required columns (others are tolerated):
            t                          time [s]
            Lx_m1, Ly_m1, thy_m1       Method 1: flame Lx, Ly, theta_y
            Ly_m2, Ly_m3               Methods 2, 3 Ly(t)

    fig10_data.csv
        Required columns:
            t
            Hf_m1, Hf_m2, Hf_m3        flame height per method
            thz_m1, thz_m2, thz_m3     theta_z per method

    fig12_data.csv
        Energy-balance scatter for Method 1, cross-wind v=1 m/s.
        Required columns:
            LHS                         left-hand-side (e.g. dE/dt + advection)
            RHS                         right-hand-side (Q_in - Q_out)

Behaviour:

    * tries to ``import matplotlib``; if available, writes:
          fig09.png, fig10.png, fig12.png
    * if matplotlib is unavailable, prints a 20-row ASCII overlay for each
      figure (curves labelled by single digits), and writes:
          fig09_ascii.txt, fig10_ascii.txt, fig12_ascii.txt
    * always writes machine-readable per-figure summary CSVs:
          fig09_summary.csv, fig10_summary.csv, fig12_summary.csv

Fig 12 includes a least-squares linear regression (slope, intercept, R^2)
computed with the standard library only.

Usage:
    python plot_fig9_10_12.py [--data-dir DIR] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import ast
import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# matplotlib detection
# --------------------------------------------------------------------------- #
try:
    import matplotlib  # noqa: F401

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: F401

    HAVE_MPL = True
except Exception:  # pragma: no cover - depends on environment
    HAVE_MPL = False


# --------------------------------------------------------------------------- #
# CSV helpers
# --------------------------------------------------------------------------- #
def read_csv(path: Path) -> Dict[str, List[float]]:
    """Return {column_name: [floats]} for a CSV with a single header row.

    Non-numeric entries become NaN.  Empty cells become NaN.
    """
    if not path.exists():
        raise FileNotFoundError(f"missing input CSV: {path}")
    with open(path) as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise RuntimeError(f"{path}: empty file") from exc
        cols: Dict[str, List[float]] = {h.strip(): [] for h in header}
        names = [h.strip() for h in header]
        for row in reader:
            if not row:
                continue
            for i, name in enumerate(names):
                if i < len(row):
                    s = row[i].strip()
                    try:
                        cols[name].append(float(s))
                    except ValueError:
                        cols[name].append(float("nan"))
                else:
                    cols[name].append(float("nan"))
    return cols


def pick(cols: Dict[str, List[float]], *candidates: str) -> Tuple[str, List[float]]:
    """Return (name, values) for the first candidate present.  Raise otherwise."""
    for c in candidates:
        if c in cols:
            return c, cols[c]
    raise KeyError(
        f"none of {candidates} found in CSV; have: {sorted(cols.keys())}"
    )


def finite_pairs(xs: List[float], ys: List[float]) -> Tuple[List[float], List[float]]:
    xo: List[float] = []
    yo: List[float] = []
    for x, y in zip(xs, ys):
        if math.isfinite(x) and math.isfinite(y):
            xo.append(x)
            yo.append(y)
    return xo, yo


# --------------------------------------------------------------------------- #
# Linear regression (stdlib only)
# --------------------------------------------------------------------------- #
def linreg(xs: List[float], ys: List[float]) -> Tuple[float, float, float]:
    """Ordinary least-squares fit y = a*x + b.  Returns (slope, intercept, R^2)."""
    xs, ys = finite_pairs(xs, ys)
    n = len(xs)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0.0:
        return float("nan"), float("nan"), float("nan")
    slope = sxy / sxx
    intercept = my - slope * mx
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else float("nan")
    return slope, intercept, r2


# --------------------------------------------------------------------------- #
# ASCII overlay plotter
# --------------------------------------------------------------------------- #
def ascii_overlay(
    title: str,
    xs: List[float],
    series: List[Tuple[str, List[float]]],
    width: int = 70,
    height: int = 18,
) -> str:
    """Build an overlay ASCII plot.

    Each series is identified by its first character (digit/letter) when drawn.
    A small legend is appended.
    """
    out: List[str] = []
    out.append(f"=== {title} ===")
    fx, _ = finite_pairs(xs, xs)
    if not fx:
        out.append("(no finite x data)")
        return "\n".join(out)
    xmin, xmax = min(fx), max(fx)
    all_y: List[float] = []
    for _, ys in series:
        _, fy = finite_pairs(xs, ys)
        all_y.extend(fy)
    if not all_y:
        out.append("(no finite y data)")
        return "\n".join(out)
    ymin, ymax = min(all_y), max(all_y)
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0

    grid = [[" "] * width for _ in range(height)]
    for idx, (label, ys) in enumerate(series):
        mark = label[0] if label else str(idx + 1)
        for x, y in zip(xs, ys):
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            col = int(round((x - xmin) / (xmax - xmin) * (width - 1)))
            row = int(round((ymax - y) / (ymax - ymin) * (height - 1)))
            if 0 <= row < height and 0 <= col < width:
                grid[row][col] = mark

    # frame
    out.append(f"y in [{ymin:.2f}, {ymax:.2f}]   x in [{xmin:.2f}, {xmax:.2f}]")
    out.append("+" + "-" * width + "+")
    for r, row in enumerate(grid):
        if r == 0:
            tag = f"{ymax:>8.2f} |"
        elif r == height - 1:
            tag = f"{ymin:>8.2f} |"
        else:
            tag = " " * 8 + " |"
        out.append(tag + "".join(row) + "|")
    out.append(" " * 9 + "+" + "-" * width + "+")
    out.append(" " * 10 + f"{xmin:.2f}" + " " * (width - 10) + f"{xmax:.2f}")
    out.append("")
    out.append("Legend:")
    for idx, (label, _) in enumerate(series):
        mark = label[0] if label else str(idx + 1)
        out.append(f"  '{mark}' = {label}")
    return "\n".join(out)


def scatter_ascii(
    title: str,
    xs: List[float],
    ys: List[float],
    slope: float,
    intercept: float,
    r2: float,
    width: int = 60,
    height: int = 20,
) -> str:
    out: List[str] = []
    out.append(f"=== {title} ===")
    fx, fy = finite_pairs(xs, ys)
    if not fx:
        out.append("(no finite data)")
        return "\n".join(out)
    xmin, xmax = min(fx), max(fx)
    ymin, ymax = min(fy), max(fy)
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0
    grid = [[" "] * width for _ in range(height)]
    # regression line
    if math.isfinite(slope) and math.isfinite(intercept):
        for c in range(width):
            x = xmin + c / (width - 1) * (xmax - xmin)
            y = slope * x + intercept
            r = int(round((ymax - y) / (ymax - ymin) * (height - 1)))
            if 0 <= r < height:
                grid[r][c] = "-"
    # points (overwrite the line where data exists)
    for x, y in zip(fx, fy):
        c = int(round((x - xmin) / (xmax - xmin) * (width - 1)))
        r = int(round((ymax - y) / (ymax - ymin) * (height - 1)))
        if 0 <= r < height and 0 <= c < width:
            grid[r][c] = "*"
    out.append(
        f"y in [{ymin:.2f}, {ymax:.2f}]   x in [{xmin:.2f}, {xmax:.2f}]   N={len(fx)}"
    )
    out.append(f"fit: y = {slope:.2f} * x + {intercept:.2f}   R^2 = {r2:.2f}")
    out.append("+" + "-" * width + "+")
    for r, row in enumerate(grid):
        if r == 0:
            tag = f"{ymax:>8.2f} |"
        elif r == height - 1:
            tag = f"{ymin:>8.2f} |"
        else:
            tag = " " * 8 + " |"
        out.append(tag + "".join(row) + "|")
    out.append(" " * 9 + "+" + "-" * width + "+")
    out.append(" " * 10 + f"{xmin:.2f}" + " " * (width - 10) + f"{xmax:.2f}")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Summary CSV writers
# --------------------------------------------------------------------------- #
def write_summary_csv(path: Path, rows: List[List[str]]) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(",".join(r) + "\n")


def series_stats(name: str, values: List[float]) -> List[str]:
    fv = [v for v in values if math.isfinite(v)]
    if not fv:
        return [name, "0", "nan", "nan", "nan", "nan"]
    return [
        name,
        str(len(fv)),
        f"{min(fv):.4f}",
        f"{max(fv):.4f}",
        f"{sum(fv) / len(fv):.4f}",
        f"{fv[-1]:.4f}",
    ]


SUMMARY_HEADER = ["series", "n_finite", "min", "max", "mean", "last"]


# --------------------------------------------------------------------------- #
# Figure builders
# --------------------------------------------------------------------------- #
def build_fig9(data_dir: Path, out_dir: Path) -> List[Path]:
    cols = read_csv(data_dir / "fig9_data.csv")
    _, t = pick(cols, "t", "time", "t_s")

    _, lx1 = pick(cols, "Lx_m1", "Lx_method1", "Lx1")
    _, ly1 = pick(cols, "Ly_m1", "Ly_method1", "Ly1")
    _, thy1 = pick(cols, "thy_m1", "theta_y_m1", "thetay_m1", "thy1")
    _, ly2 = pick(cols, "Ly_m2", "Ly_method2", "Ly2")
    _, ly3 = pick(cols, "Ly_m3", "Ly_method3", "Ly3")

    written: List[Path] = []

    # always: summary
    summary_rows: List[List[str]] = [SUMMARY_HEADER]
    for name, vals in [
        ("Lx_m1", lx1),
        ("Ly_m1", ly1),
        ("thy_m1", thy1),
        ("Ly_m2", ly2),
        ("Ly_m3", ly3),
    ]:
        summary_rows.append(series_stats(name, vals))
    spath = out_dir / "fig9_summary.csv"
    write_summary_csv(spath, summary_rows)
    written.append(spath)

    if HAVE_MPL:
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.2))
        # panel (a): Lx, Ly on left; theta_y on right
        ax_a.plot(t, lx1, "-", label="Lx (Method 1)")
        ax_a.plot(t, ly1, "--", label="Ly (Method 1)")
        ax_a.set_xlabel("t [s]")
        ax_a.set_ylabel("Lx, Ly [m]")
        ax_aR = ax_a.twinx()
        ax_aR.plot(t, thy1, ":", color="tab:red", label=r"$\theta_y$ (Method 1)")
        ax_aR.set_ylabel(r"$\theta_y$ [deg]")
        h1, l1 = ax_a.get_legend_handles_labels()
        h2, l2 = ax_aR.get_legend_handles_labels()
        ax_a.legend(h1 + h2, l1 + l2, loc="best", fontsize=8)
        ax_a.set_title("Fig 9(a): Method 1 — Lx, Ly, theta_y")

        # panel (b): Ly methods 2 & 3
        ax_b.plot(t, ly2, "-", label="Ly (Method 2)")
        ax_b.plot(t, ly3, "--", label="Ly (Method 3)")
        ax_b.set_xlabel("t [s]")
        ax_b.set_ylabel("Ly [m]")
        ax_b.set_title("Fig 9(b): Ly for Methods 2 & 3")
        ax_b.legend(loc="best", fontsize=8)

        fig.tight_layout()
        png = out_dir / "fig09.png"
        fig.savefig(png, dpi=150)
        plt.close(fig)
        written.append(png)
    else:
        txt = []
        txt.append(
            ascii_overlay(
                "Fig 9(a) Method 1: 1=Lx, 2=Ly, 3=theta_y",
                t,
                [("1=Lx_m1", lx1), ("2=Ly_m1", ly1), ("3=thy_m1", thy1)],
            )
        )
        txt.append("")
        txt.append(
            ascii_overlay(
                "Fig 9(b) Ly: 2=Method2, 3=Method3",
                t,
                [("2=Ly_m2", ly2), ("3=Ly_m3", ly3)],
            )
        )
        tpath = out_dir / "fig09_ascii.txt"
        tpath.write_text("\n".join(txt) + "\n")
        print("\n".join(txt))
        written.append(tpath)

    return written


def build_fig10(data_dir: Path, out_dir: Path) -> List[Path]:
    cols = read_csv(data_dir / "fig10_data.csv")
    _, t = pick(cols, "t", "time", "t_s")

    _, hf1 = pick(cols, "Hf_m1", "Hf_method1", "Hf1")
    _, hf2 = pick(cols, "Hf_m2", "Hf_method2", "Hf2")
    _, hf3 = pick(cols, "Hf_m3", "Hf_method3", "Hf3")
    _, thz1 = pick(cols, "thz_m1", "theta_z_m1", "thetaz_m1", "thz1")
    _, thz2 = pick(cols, "thz_m2", "theta_z_m2", "thetaz_m2", "thz2")
    _, thz3 = pick(cols, "thz_m3", "theta_z_m3", "thetaz_m3", "thz3")

    written: List[Path] = []
    summary_rows: List[List[str]] = [SUMMARY_HEADER]
    for name, vals in [
        ("Hf_m1", hf1),
        ("Hf_m2", hf2),
        ("Hf_m3", hf3),
        ("thz_m1", thz1),
        ("thz_m2", thz2),
        ("thz_m3", thz3),
    ]:
        summary_rows.append(series_stats(name, vals))
    spath = out_dir / "fig10_summary.csv"
    write_summary_csv(spath, summary_rows)
    written.append(spath)

    if HAVE_MPL:
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.2))
        ax_a.plot(t, hf1, "-", label="Method 1")
        ax_a.plot(t, hf2, "--", label="Method 2")
        ax_a.plot(t, hf3, ":", label="Method 3")
        ax_a.set_xlabel("t [s]")
        ax_a.set_ylabel("Hf [m]")
        ax_a.set_title("Fig 10(a): Hf(t)")
        ax_a.legend(loc="best", fontsize=8)

        ax_b.plot(t, thz1, "-", label="Method 1")
        ax_b.plot(t, thz2, "--", label="Method 2")
        ax_b.plot(t, thz3, ":", label="Method 3")
        ax_b.set_xlabel("t [s]")
        ax_b.set_ylabel(r"$\theta_z$ [deg]")
        ax_b.set_title(r"Fig 10(b): $\theta_z$(t)")
        ax_b.legend(loc="best", fontsize=8)

        fig.tight_layout()
        png = out_dir / "fig10.png"
        fig.savefig(png, dpi=150)
        plt.close(fig)
        written.append(png)
    else:
        txt = []
        txt.append(
            ascii_overlay(
                "Fig 10(a) Hf(t): 1=M1, 2=M2, 3=M3",
                t,
                [("1=Hf_m1", hf1), ("2=Hf_m2", hf2), ("3=Hf_m3", hf3)],
            )
        )
        txt.append("")
        txt.append(
            ascii_overlay(
                "Fig 10(b) theta_z(t): 1=M1, 2=M2, 3=M3",
                t,
                [("1=thz_m1", thz1), ("2=thz_m2", thz2), ("3=thz_m3", thz3)],
            )
        )
        tpath = out_dir / "fig10_ascii.txt"
        tpath.write_text("\n".join(txt) + "\n")
        print("\n".join(txt))
        written.append(tpath)

    return written


def build_fig12(data_dir: Path, out_dir: Path) -> List[Path]:
    cols = read_csv(data_dir / "fig12_data.csv")
    _, lhs = pick(cols, "LHS", "lhs", "Lhs")
    _, rhs = pick(cols, "RHS", "rhs", "Rhs")

    slope, intercept, r2 = linreg(lhs, rhs)

    written: List[Path] = []
    summary_rows = [
        ["metric", "value"],
        ["n_finite", str(len(finite_pairs(lhs, rhs)[0]))],
        ["slope", f"{slope:.6f}"],
        ["intercept", f"{intercept:.6f}"],
        ["R2", f"{r2:.6f}"],
    ]
    spath = out_dir / "fig12_summary.csv"
    write_summary_csv(spath, summary_rows)
    written.append(spath)

    if HAVE_MPL:
        fig, ax = plt.subplots(1, 1, figsize=(5.5, 5.5))
        ax.scatter(lhs, rhs, s=14, alpha=0.7, label="data")
        fx, fy = finite_pairs(lhs, rhs)
        if fx and math.isfinite(slope):
            xx = [min(fx), max(fx)]
            yy = [slope * x + intercept for x in xx]
            ax.plot(xx, yy, "r-", lw=1.5, label="linear fit")
            # y = x reference
            lo = min(min(fx), min(fy))
            hi = max(max(fx), max(fy))
            ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, alpha=0.5, label="y = x")
        ax.set_xlabel("LHS")
        ax.set_ylabel("RHS")
        ax.set_title("Fig 12: Method 1, v=1 m/s — RHS vs LHS")
        ax.annotate(
            f"slope = {slope:.3f}\nintercept = {intercept:.3f}\n$R^2$ = {r2:.3f}",
            xy=(0.05, 0.95),
            xycoords="axes fraction",
            ha="left",
            va="top",
            fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="0.5"),
        )
        ax.legend(loc="lower right", fontsize=8)
        fig.tight_layout()
        png = out_dir / "fig12.png"
        fig.savefig(png, dpi=150)
        plt.close(fig)
        written.append(png)
    else:
        txt = scatter_ascii(
            "Fig 12: RHS vs LHS (Method 1, v=1 m/s)  '*'=data, '-'=fit",
            lhs,
            rhs,
            slope,
            intercept,
            r2,
        )
        tpath = out_dir / "fig12_ascii.txt"
        tpath.write_text(txt + "\n")
        print(txt)
        written.append(tpath)

    return written


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(HERE),
                    help="directory containing fig{9,10,12}_data.csv "
                         f"(default: {HERE})")
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: same as --data-dir)")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else data_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"matplotlib: {'available' if HAVE_MPL else 'NOT available — ASCII fallback'}")
    print(f"data-dir:   {data_dir}")
    print(f"out-dir:    {out_dir}")

    all_written: List[Path] = []
    for builder, label in [
        (build_fig9, "Fig 9"),
        (build_fig10, "Fig 10"),
        (build_fig12, "Fig 12"),
    ]:
        try:
            paths = builder(data_dir, out_dir)
            all_written.extend(paths)
            print(f"{label}: wrote {', '.join(str(p) for p in paths)}")
        except (FileNotFoundError, KeyError, RuntimeError) as e:
            print(f"{label}: SKIPPED — {e}", file=sys.stderr)

    if not all_written:
        sys.exit("ERROR: no figures produced")


if __name__ == "__main__":
    main()
