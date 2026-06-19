#!/usr/bin/env python3
"""
Compact grid-convergence T(z) plot — center+1 m, time-averaged only,
Mesh 1/3/6 vs paper reference (ref.csv).

Highlights pointwise deviation of each mesh vs paper in the right-hand panel.
"""
from __future__ import annotations
import csv, re, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT    = Path("/scratch/x3319a05/fds/Engine_Room")
RESULTS = ROOT / "Results"
OUT_DIR = Path(__file__).parent
REF_CSV = OUT_DIR / "ref.csv"

CELLS  = {1: "84 k", 2: "200 k", 3: "390 k", 4: "674 k",
          5: "1.07 M", 6: "1.60 M", 7: "2.27 M"}
COLORS = {1: "tab:blue", 2: "tab:cyan",   3: "tab:orange",
          4: "tab:red",  5: "tab:purple", 6: "tab:green",
          7: "tab:brown"}
N_PTS = 30
Z_SIM = np.linspace(0.05, 2.95, N_PTS)


# M6 (760359) now matches the canonical M1/M3/M5 baseline setup so it IS
# included in the convergence plot.
EXCLUDE_MESHES = set()
# Specific job IDs that should be skipped in auto-discovery even though their
# data is valid — e.g. one-off sensitivity tests that don't match the canonical
# setup of the current grid-convergence sweep.
EXCLUDE_JOBS = {
    759278,    # 0.886² + ADIABATIC test; M1 canonical = 759273
    761013, 761176, 761266, 761633,    # cold-walls/cold-engine/door-shift variants
}


def discover_runs():
    """Per mesh N (not in EXCLUDE_MESHES), return the most-recent run with
    non-empty center_avg (excludes sign-test variants and partially-completed
    runs)."""
    pat = re.compile(r"^grid_mesh(\d+)_(\d+)$")    # strict — no signpos/signneg
    bymesh = {}
    for d in RESULTS.iterdir():
        if not d.is_dir(): continue
        m = pat.match(d.name)
        if not m: continue
        mesh, job = int(m.group(1)), int(m.group(2))
        if mesh in EXCLUDE_MESHES: continue
        if job in EXCLUDE_JOBS: continue
        bymesh.setdefault(mesh, []).append((job, d.name))
    out = []
    for mesh in sorted(bymesh):
        for job, dirname in sorted(bymesh[mesh], reverse=True):  # newest first
            try:
                vals = load_avg(dirname)
                if np.max(vals) > 0 or np.min(vals) < 0:
                    out.append((mesh, (job, dirname)))
                    break
            except Exception:
                continue
    return out


def load_ref():
    z, T = [], []
    for line in REF_CSV.read_text().splitlines():
        if not line.strip(): continue
        a, b = line.split(",")
        z.append(float(a)); T.append(float(b))
    return np.asarray(z), np.asarray(T)


def load_avg(d, col="gridconv_T_center_avg"):
    f = RESULTS / d / f"{d}_line.csv"
    rows = list(csv.reader(open(f)))
    hdr  = [c.strip() for c in rows[1]]
    if col not in hdr:
        return None
    j = hdr.index(col)
    return np.array([float(rows[2+i][j]) for i in range(N_PTS)])


def load_time_std(d, sensor_y, x_target=8.4, t_start=100.0, n_win=4):
    """Window-mean std of T(z) at the sensor (x≈8.4, y=sensor_y).  Splits
    [t_start, end] into n_win equal windows, computes mean T(z) in each
    window, then returns std of those n_win means at each z.  This measures
    how stable the time-averaged value is — for a converged simulation this
    should DECREASE with grid refinement (less sampling error)."""
    import fdsreader
    try:
        sim = fdsreader.Simulation(str(RESULTS / d))
    except Exception:
        return None
    candidates = [(abs(sl.extent.x_start - x_target), sl) for sl in sim.slices
                  if sl.orientation == 1 and sl.quantity.name == "TEMPERATURE"]
    if not candidates: return None
    sl = sorted(candidates)[0][1]
    T = sl.to_global(masked=True, fill=np.nan)         # (nt, ny, nz)
    if T.ndim != 3: return None
    t = sl.times
    ext = sl.extent
    yc = np.linspace(ext.y_start, ext.y_end, T.shape[1])
    zc = np.linspace(ext.z_start, ext.z_end, T.shape[2])
    iy = int(np.argmin(np.abs(yc - sensor_y)))
    # Bin time into windows over [t_start, t_end]
    t_end = float(t[-1])
    bin_edges = np.linspace(t_start, t_end, n_win + 1)
    win_means = []          # list of (nz,) arrays
    for w in range(n_win):
        m = (t >= bin_edges[w]) & (t < bin_edges[w+1] + 1e-6)
        if m.sum() < 1: continue
        win_means.append(np.nanmean(T[m, iy, :], axis=0))
    if len(win_means) < 2: return None
    Wm = np.stack(win_means, axis=0)                    # (n_win, nz)
    win_std = np.nanstd(Wm, axis=0)
    return np.interp(Z_SIM, zc, win_std)


def main():
    ref_z, ref_T = load_ref()
    runs = discover_runs()

    # (offset_label, column suffix) — order matters for legend
    OFFSETS = [
        ("+1.0m", "gridconv_T_center_avg"),
        ("+0.5m", "gridconv_T_center_05m_avg"),
        ("-0.5m", "gridconv_T_center_n05m_avg"),
        ("-1.0m", "gridconv_T_center_n10m_avg"),
    ]
    sim, used = {}, []   # sim[(label,offset)] = vals;  used = [(mesh_n, label, offset)]
    for mesh_n, (job, dirname) in runs:
        label = f"Mesh {mesh_n}"
        found_any = False
        for off, col in OFFSETS:
            vals = load_avg(dirname, col)
            if vals is None or (np.max(vals) == 0 and np.min(vals) == 0):
                continue
            sim[(label, off)] = vals
            used.append((mesh_n, label, off))
            found_any = True
        if not found_any:
            print(f"skip M{mesh_n} ({dirname}): no usable center_avg columns")
            continue
        offsets_here = [o for m, _, o in used if m == mesh_n]
        print(f"loaded M{mesh_n}: {dirname}  ({', '.join(offsets_here)})")
    if not sim:
        sys.exit("no usable runs")

    # Apply z-direction 3-point moving average to smooth sub-mesh / sensor
    # cell noise without changing trends.
    def smooth(v, w=3):
        kern = np.ones(w) / w
        pad = w // 2
        vv = np.concatenate([np.full(pad, v[0]), v, np.full(pad, v[-1])])
        return np.convolve(vv, kern, mode="valid")

    ref_at_sim = np.interp(Z_SIM, ref_z, ref_T)
    meshes_tag = "_".join(sorted({f"M{m}" for m, _, _ in used}))

    # Per-mesh per-offset time std at sensor location (for convergence proof)
    OFFSET_Y = {"+1.0m": 2.5, "+0.5m": 2.0, "-0.5m": 1.0, "-1.0m": 0.5}
    mesh_to_dir = {m: d for m, (_, d) in runs}
    std_cache = {}     # (label, off) -> std array (30,)
    for mesh_n, label, off in used:
        dirname = mesh_to_dir.get(mesh_n)
        sy = OFFSET_Y.get(off)
        if sy is None or dirname is None: continue
        std_arr = load_time_std(dirname, sy)
        if std_arr is not None:
            std_cache[(label, off)] = std_arr
            print(f"  std M{mesh_n} {off}: mean |σ| = {np.nanmean(np.abs(std_arr)):.2f} °C")

    # ---- Cauchy residuals (proper grid-convergence metric for LES) ----
    # For successive mesh pairs (M_coarse, M_fine), |T_fine - T_coarse| should
    # decrease as the meshes refine.  Uses 3-pt smoothed time-mean T(z).
    # cauchy[(off, mesh_fine)] = (mesh_coarse, residual_array, mean_|res|)
    cauchy = {}
    label_by_mesh = {m: lbl for m, lbl, _ in used}
    for off_target in sorted({o for _, _, o in used}):
        meshes_here = sorted({m for m, _, o in used if o == off_target})
        for i in range(1, len(meshes_here)):
            m_fine   = meshes_here[i]
            m_coarse = meshes_here[i-1]
            v_fine   = smooth(sim[(label_by_mesh[m_fine], off_target)],   3)
            v_coarse = smooth(sim[(label_by_mesh[m_coarse], off_target)], 3)
            res = v_fine - v_coarse
            cauchy[(off_target, m_fine)] = (m_coarse, res, float(np.nanmean(np.abs(res))))
            print(f"  Cauchy {off_target}  M{m_coarse}→M{m_fine}: "
                  f"mean |T_fine−T_coarse| = {np.nanmean(np.abs(res)):.2f} °C")

    # Two T(z) figures per offset:
    #   *_raw.png    = raw simulation values (no smoothing)  — keep original
    #   *_smooth.png = 3-point z-direction moving average    — new
    offsets_present = sorted({o for _, _, o in used})
    for off_target in offsets_present:
        # ---- raw plot (existing behaviour) ----
        fig, ax1 = plt.subplots(figsize=(8, 6))
        ax1.plot(ref_z, ref_T, "k--x", lw=2.0, ms=7,
                 label="Reference", zorder=10)
        for mesh_n, label, off in used:
            if off != off_target: continue
            raw = sim[(label, off)]
            color = COLORS.get(mesh_n, "gray")
            ax1.plot(Z_SIM, raw, color=color, marker="o", ms=4, mfc="none",
                     lw=1.6, linestyle="-", label=label)
        ax1.set_xlabel("Height z (m)")
        ax1.set_ylabel("Temperature (°C)")
        ax1.set_xlim(0, 3.0); ax1.set_ylim(20, 270)
        ax1.grid(alpha=0.3)
        ax1.legend(fontsize=10, loc="upper left", framealpha=0.95)
        ax1.set_title(f"T(z) — sensor at fire centre {off_target} in y")
        tag = off_target.replace("+", "p").replace(".", "p")
        out = OUT_DIR / f"gridconv_summary_{meshes_tag}_{tag}_raw.png"
        fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)
        print(f"wrote {out}")

        # ---- smoothed plot (3-pt moving average, faint raw underlay) ----
        fig, ax1 = plt.subplots(figsize=(8, 6))
        ax1.plot(ref_z, ref_T, "k--x", lw=2.0, ms=7,
                 label="Reference", zorder=10)
        for mesh_n, label, off in used:
            if off != off_target: continue
            raw = sim[(label, off)]
            sm  = smooth(raw, 3)
            color = COLORS.get(mesh_n, "gray")
            ax1.plot(Z_SIM, raw, color=color, lw=0.6, alpha=0.3, linestyle="-")
            ax1.plot(Z_SIM, sm, color=color, marker="o", ms=4, mfc="none",
                     lw=1.6, linestyle="-", label=label)
        ax1.set_xlabel("Height z (m)")
        ax1.set_ylabel("Temperature (°C, 3-pt z-moving-avg)")
        ax1.set_xlim(0, 3.0); ax1.set_ylim(20, 270)
        ax1.grid(alpha=0.3)
        ax1.legend(fontsize=10, loc="upper left", framealpha=0.95)
        ax1.set_title(f"T(z) — sensor at fire centre {off_target} in y (smoothed)")
        out = OUT_DIR / f"gridconv_summary_{meshes_tag}_{tag}_smooth.png"
        fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)
        print(f"wrote {out}")

    # text summary
    print("\nMean |ΔT| over z=[0.95, 2.45] (the well-converging middle band):")
    mid = (Z_SIM >= 0.95) & (Z_SIM <= 2.45)
    for mesh_n, label, off in used:
        dev = sim[(label, off)][mid] - ref_at_sim[mid]
        print(f"  M{mesh_n} ({off}): mean |Δ| = {np.mean(np.abs(dev)):5.1f} °C, "
              f"max |Δ| = {np.max(np.abs(dev)):5.1f} °C")


if __name__ == "__main__":
    main()
