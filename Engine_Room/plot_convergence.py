"""
Plot grid-convergence T(z) profiles from FDS LINE DEVC output.

Usage:
  python3 plot_convergence.py          # uses Results/w_M1, w_M3, w_M5
  python3 plot_convergence.py --m5only # M5 y-profiles only (if M1/M3 not done)
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm

ROOT = Path(__file__).parent
RESULTS = ROOT / "Results"

MESHES = {
    "M1": {"dir": RESULTS / "w_M1", "prefix": "w_M1", "ijk": (130, 100, 30), "color": "tab:blue"},
    "M3": {"dir": RESULTS / "w_M3", "prefix": "w_M3", "ijk": (130, 100, 30), "color": "tab:orange"},
    "M5": {"dir": RESULTS / "w_M5", "prefix": "w_M5", "ijk": (156, 120, 36), "color": "tab:green"},
}

Z_START, Z_END, N_POINTS = 0.05, 2.95, 30
Z = np.linspace(Z_START, Z_END, N_POINTS)

DY_VALUES = np.arange(0, 15) * 0.1  # 0.0, 0.1, ..., 1.4 m


def read_line_csv(path: Path):
    """Read _line.csv → shape (N_POINTS, N_SENSORS).
    Skips 2 header rows. Returns None if file missing or wrong shape."""
    if not path.exists():
        return None
    data = np.genfromtxt(path, delimiter=",", skip_header=2)
    if data.ndim == 1:
        data = data[np.newaxis, :]
    # Take the last N_POINTS rows (final snapshot)
    if data.shape[0] >= N_POINTS:
        data = data[-N_POINTS:, :]
    return data


def get_sim_time(hrr_path: Path) -> float:
    """Return last simulation time from _hrr.csv."""
    if not hrr_path.exists():
        return 0.0
    last = None
    with open(hrr_path) as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith(("s", "T", "H")):
                last = s
    if last is None:
        return 0.0
    try:
        return float(last.split(",")[0])
    except ValueError:
        return 0.0


# ── Plot 1: M5 y-offset profiles ──────────────────────────────────────────────

def plot_m5_yprofiles(out_path: Path):
    info = MESHES["M5"]
    data = read_line_csv(info["dir"] / f"{info['prefix']}_line.csv")
    t = get_sim_time(info["dir"] / f"{info['prefix']}_hrr.csv")

    if data is None:
        print("M5 _line.csv not found — skipping y-profile plot")
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    cmap = cm.get_cmap("plasma", len(DY_VALUES))

    for i, dy in enumerate(DY_VALUES):
        col = data[:, i] if i < data.shape[1] else None
        if col is None:
            continue
        ax.plot(col, Z, color=cmap(i), label=f"Δy={dy:.1f} m")

    ax.set_xlabel("Temperature (°C)", fontsize=12)
    ax.set_ylabel("Height z (m)", fontsize=12)
    ax.set_title(f"M5 — T(z) by y-offset from fire centre  (t = {t:.0f} s)", fontsize=13)
    ax.set_ylim(0, 3)
    ax.grid(True, alpha=0.3)
    sm = plt.cm.ScalarMappable(cmap="plasma", norm=plt.Normalize(0, 1.4))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label("Δy from fire centre (m)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.close(fig)


# ── Plot 2: grid convergence at each dy — M1 vs M3 vs M5 ──────────────────────

def plot_grid_convergence(out_path: Path):
    datasets = {}
    sim_times = {}
    for name, info in MESHES.items():
        data = read_line_csv(info["dir"] / f"{info['prefix']}_line.csv")
        t = get_sim_time(info["dir"] / f"{info['prefix']}_hrr.csv")
        if data is not None:
            datasets[name] = data
            sim_times[name] = t

    if len(datasets) < 2:
        print("Need at least 2 mesh results for convergence plot — skipping")
        return

    n_dy = len(DY_VALUES)
    ncols = 3
    nrows = (n_dy + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(14, nrows * 3.2), sharey=True)
    axes_flat = axes.flatten()

    for i, dy in enumerate(DY_VALUES):
        ax = axes_flat[i]
        for name, data in datasets.items():
            if i >= data.shape[1]:
                continue
            color = MESHES[name]["color"]
            t = sim_times[name]
            ax.plot(data[:, i], Z, color=color, label=f"{name} (t={t:.0f}s)")
        ax.set_title(f"Δy = {dy:.1f} m", fontsize=9)
        ax.set_xlim(left=0)
        ax.set_ylim(0, 3)
        ax.grid(True, alpha=0.3)
        if i % ncols == 0:
            ax.set_ylabel("z (m)", fontsize=8)
        ax.tick_params(labelsize=7)

    # Hide unused subplots
    for j in range(n_dy, len(axes_flat)):
        axes_flat[j].set_visible(False)

    # Shared legend
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower right", fontsize=10,
               bbox_to_anchor=(0.98, 0.02))
    fig.supxlabel("Temperature (°C)", fontsize=11)
    fig.suptitle("Grid Convergence — T(z) by y-offset (M1 / M3 / M5)", fontsize=13)
    fig.tight_layout(rect=[0, 0.04, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.close(fig)


# ── Plot 3: convergence at centre line (dy=0) only, all 3 meshes ──────────────

def plot_centre_convergence(out_path: Path):
    fig, ax = plt.subplots(figsize=(7, 6))
    for name, info in MESHES.items():
        data = read_line_csv(info["dir"] / f"{info['prefix']}_line.csv")
        t = get_sim_time(info["dir"] / f"{info['prefix']}_hrr.csv")
        if data is None:
            continue
        nx, ny, nz = info["ijk"]
        total = nx * ny * nz
        ax.plot(data[:, 0], Z, color=info["color"],
                label=f"{name}  ({nx}×{ny}×{nz}={total/1e3:.0f}k, t={t:.0f}s)")

    ax.set_xlabel("Temperature (°C)", fontsize=12)
    ax.set_ylabel("Height z (m)", fontsize=12)
    ax.set_title("Grid Convergence — T(z) at fire centre (Δy=0)", fontsize=13)
    ax.set_ylim(0, 3)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.close(fig)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m5only", action="store_true")
    args = ap.parse_args()

    out_dir = ROOT / "Results"
    out_dir.mkdir(exist_ok=True)

    plot_m5_yprofiles(out_dir / "m5_yprofiles.png")

    if not args.m5only:
        plot_grid_convergence(out_dir / "grid_convergence_all_dy.png")
        plot_centre_convergence(out_dir / "grid_convergence_centre.png")


if __name__ == "__main__":
    main()
