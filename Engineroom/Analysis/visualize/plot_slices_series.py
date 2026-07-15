#!/usr/bin/env python3
"""
Temperature 2D contour — 3 slice planes × 3 meshes.

Slices  : PBX=8.1 (YZ),  PBY=1.45→1.5 (XZ),  PBZ=2.0 (XY)
Time    : averaged 550–600 s  (uses available range if < 600 s)
Meshes  : M1 (84k), M3 (390k), M5 (674k)
Output  : analysis/vis/slices_fire600.png
"""
from __future__ import annotations
import sys, warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import re
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import fdsreader

ROOT = Path("/shared/home/wel1come1234/workspace/FDS/Engineroom")
RES  = ROOT / "Results"
SERIES = sys.argv[1] if len(sys.argv) > 1 else "fire1"
OUT  = ROOT / "Analysis" / "visualize" / "vis" / SERIES
OUT.mkdir(parents=True, exist_ok=True)

# series -> dict(tag, win, cases=[(case_dir, short_label), ...])
_REG = {
    "peak":  dict(tag="0.79 m2 fire", win=(300.0, 360.0),
                  cases=[(f"peak{tp:02d}_M5", f"HRR peak @{tp} s") for tp in (5,10,15,20)]),
    "fire1": dict(tag="1.0 m2 fire", win=(300.0, 360.0),
                  cases=[(f"peak{tp:02d}_fire1_M5", f"HRR peak @{tp} s") for tp in (5,10,15,20)]),
    "fire1_vent": dict(tag="1.0 m2 fire, HRR peak 10 s", win=(240.0, 300.0),
                       cases=[(f"fire1_p10_v{v}_M5", f"vent @{v} s") for v in (20,30,40)]),
}
if SERIES not in _REG:
    sys.exit(f"series must be one of {list(_REG)}")
WIN = _REG[SERIES]["win"]   # time-averaging window for slices
MESHES = [(c, f"{lbl} ({_REG[SERIES]['tag']})") for c, lbl in _REG[SERIES]["cases"]]

# Slice definitions: (orientation, target_coord, xlabel, ylabel, xlim, ylim, vmin, vmax, label)
SLICES = [
    (1, 8.40, "Y (m)", "Z (m)", (0, 10), (0, 3),   20, 150, "PBX = 8.4  (YZ plane)"),
    (1, 8.10, "Y (m)", "Z (m)", (0, 10), (0, 3),   20, 150, "PBX = 8.1  (YZ plane)"),
    (2, 1.45, "X (m)", "Z (m)", (0, 13), (0, 3),   20, 200, "PBY = 1.45→1.5  (XZ plane)"),
    (3, 2.00, "X (m)", "Y (m)", (0, 13), (0, 10),  20, 250, "PBZ = 2.0  (XY plane)"),
]
N_LEVELS   = 30
CMAP       = "jet"


def parse_obst(case_id):
    p = ROOT / "Inputs" / f"{case_id}.fds"
    if not p.exists():
        return [], []
    txt = p.read_text()
    obsts = []
    for m in re.finditer(
        r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID='([^']+)'", txt
    ):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        obsts.append(xb)
    holes = []
    for m in re.finditer(r"&HOLE\s+XB=\s*([\d.,\s\-+eE]+?)\s*/", txt):
        holes.append([float(v) for v in m.group(1).replace(",", " ").split()])
    return obsts, holes


def find_slice(sim, orientation, target):
    coord_attr = {1: "x_start", 2: "y_start", 3: "z_start"}[orientation]
    cands = [
        (abs(getattr(sl.extent, coord_attr) - target), sl)
        for sl in sim.slices
        if sl.orientation == orientation and "TEMP" in sl.quantity.name.upper()
    ]
    if not cands:
        return None
    return min(cands, key=lambda t: t[0])[1]


def time_avg(sl):
    t_arr = sl.times
    t_max = t_arr.max()
    if t_max < WIN[0]:
        return None, t_max
    t_end = min(t_max, WIN[1])
    win   = (t_arr >= WIN[0]) & (t_arr <= t_end)
    T_all = sl.to_global(masked=True, fill=np.nan)
    return np.nanmean(T_all[win], axis=0), t_end


def obst_patches_yz(obsts, holes, x_plane, ax, dA, dB, A, B):
    """Draw OBST rectangles on a YZ (y horizontal, z vertical) axis."""
    for xb in obsts:
        x1,x2,y1,y2,z1,z2 = xb
        if not (x1 - dA <= x_plane <= x2 + dA):
            continue
        # check if hole punches through
        cut = False
        for hxb in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = hxb
            if hx1 <= x_plane <= hx2 and hy1<=y1 and y2<=hy2 and hz1<=z1 and z2<=hz2:
                cut = True; break
        if not cut:
            ax.add_patch(mpatches.Rectangle(
                (y1, z1), y2-y1, z2-z1,
                linewidth=0.8, edgecolor="white", facecolor="none", zorder=5))


def obst_patches_xz(obsts, holes, y_plane, ax, dA, dB, A, B):
    """Draw OBST rectangles on an XZ (x horizontal, z vertical) axis."""
    for xb in obsts:
        x1,x2,y1,y2,z1,z2 = xb
        if not (y1 - dA <= y_plane <= y2 + dA):
            continue
        cut = False
        for hxb in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = hxb
            if hy1 <= y_plane <= hy2 and hx1<=x1 and x2<=hx2 and hz1<=z1 and z2<=hz2:
                cut = True; break
        if not cut:
            ax.add_patch(mpatches.Rectangle(
                (x1, z1), x2-x1, z2-z1,
                linewidth=0.8, edgecolor="white", facecolor="none", zorder=5))


def obst_patches_xy(obsts, holes, z_plane, ax, dA, dB, A, B):
    """Draw OBST rectangles on an XY (x horizontal, y vertical) axis."""
    for xb in obsts:
        x1,x2,y1,y2,z1,z2 = xb
        if not (z1 - dA <= z_plane <= z2 + dA):
            continue
        cut = False
        for hxb in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = hxb
            if hz1 <= z_plane <= hz2 and hx1<=x1 and x2<=hx2 and hy1<=y1 and y2<=hy2:
                cut = True; break
        if not cut:
            ax.add_patch(mpatches.Rectangle(
                (x1, y1), x2-x1, y2-y1,
                linewidth=0.8, edgecolor="white", facecolor="none", zorder=5))


# velocity component names for streamlines per orientation
# (horizontal-axis qty, vertical-axis qty)
VEL_COMPONENTS = {
    1: ("V-VELOCITY", "W-VELOCITY"),   # YZ plane: y-vel, z-vel
    2: ("U-VELOCITY", "W-VELOCITY"),   # XZ plane: x-vel, z-vel
    3: ("U-VELOCITY", "V-VELOCITY"),   # XY plane: x-vel, y-vel
}


def load_vel(sim, ori, target, qty):
    coord_attr = {1: "x_start", 2: "y_start", 3: "z_start"}[ori]
    cands = [
        (abs(getattr(s.extent, coord_attr) - target), s)
        for s in sim.slices
        if s.orientation == ori and s.quantity.name == qty
    ]
    if not cands:
        return None
    return min(cands, key=lambda t: t[0])[1]


def plot_single_slice(ax, fig, sim, obsts, holes, ori, target, xlabel, ylabel,
                      xlim, ylim, vmin, vmax, slc_lbl, case_dir):
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    levels = np.linspace(vmin, vmax, N_LEVELS)

    sl = find_slice(sim, ori, target)
    if sl is None:
        ax.text(0.5, 0.5, "no slice", ha="center", va="center",
                transform=ax.transAxes)
        print(f"  {case_dir} ori={ori}: slice not found"); return False

    T_avg, t_end = time_avg(sl)
    if T_avg is None:
        ax.text(0.5, 0.5, f"t_max < {WIN[0]:.0f} s\n({t_end:.0f} s)",
                ha="center", va="center", transform=ax.transAxes, fontsize=9)
        print(f"  {case_dir} ori={ori}: only {t_end:.0f} s available"); return False

    ext = sl.extent
    if ori == 1:
        A = np.linspace(ext.y_start, ext.y_end, T_avg.shape[0])
        B = np.linspace(ext.z_start, ext.z_end, T_avg.shape[1])
    elif ori == 2:
        A = np.linspace(ext.x_start, ext.x_end, T_avg.shape[0])
        B = np.linspace(ext.z_start, ext.z_end, T_avg.shape[1])
    else:
        A = np.linspace(ext.x_start, ext.x_end, T_avg.shape[0])
        B = np.linspace(ext.y_start, ext.y_end, T_avg.shape[1])

    Ag, Bg = np.meshgrid(A, B, indexing="ij")
    cf = ax.contourf(Ag, Bg, T_avg, levels=levels, cmap=CMAP, extend="both")

    dA = (A[1] - A[0]) if len(A) > 1 else 0.1
    dB = (B[1] - B[0]) if len(B) > 1 else 0.1
    coord = getattr(sl.extent, {1: "x_start", 2: "y_start", 3: "z_start"}[ori])
    if   ori == 1: obst_patches_yz(obsts, holes, coord, ax, dA, dB, A, B)
    elif ori == 2: obst_patches_xz(obsts, holes, coord, ax, dA, dB, A, B)
    else:          obst_patches_xy(obsts, holes, coord, ax, dA, dB, A, B)

    # ── streamlines ─────────────────────────────────────────────────────
    qa, qb = VEL_COMPONENTS[ori]
    sl_va = load_vel(sim, ori, target, qa)
    sl_vb = load_vel(sim, ori, target, qb)
    if sl_va is not None and sl_vb is not None:
        Va, _ = time_avg(sl_va)
        Vb, _ = time_avg(sl_vb)
        if Va is not None and Vb is not None:
            # streamplot expects (x=A, y=B, u=Va, v=Vb) with u,v in (nB, nA)
            Va_plot = Va.T
            Vb_plot = Vb.T
            speed = np.sqrt(Va_plot**2 + Vb_plot**2)
            speed_max = np.nanpercentile(speed, 95)
            if speed_max > 0:
                ax.streamplot(
                    A, B, Va_plot, Vb_plot,
                    density=1.2, linewidth=0.8,
                    color="black", arrowsize=0.8,
                    zorder=4,
                )

    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_xlabel(xlabel, fontsize=10); ax.set_ylabel(ylabel, fontsize=10)
    ax.tick_params(labelsize=9)
    ax.set_title(slc_lbl, fontsize=10)
    ax.set_aspect("equal")

    div = make_axes_locatable(ax)
    cax = div.append_axes("right", size="4%", pad=0.06)
    cbar = fig.colorbar(cf, cax=cax, ticks=np.linspace(vmin, vmax, 7))
    cbar.set_label("T (°C)", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    print(f"  ori={ori}: t_avg {WIN[0]:.0f}–{t_end:.0f} s  OK")
    return True


def plot_mesh(case_dir, mesh_lbl):
    res_path = RES / case_dir
    if not (res_path / f"{case_dir}.smv").exists():
        print(f"  {case_dir}: .smv not found – skip"); return
    try:
        sim = fdsreader.Simulation(str(res_path))
    except Exception as e:
        print(f"  {case_dir}: load error {e}"); return

    obsts, holes = parse_obst(case_dir)
    mesh_out = OUT / case_dir
    mesh_out.mkdir(parents=True, exist_ok=True)

    axis_tag = {1: "x", 2: "y", 3: "z"}
    axis_count = {1: 0, 2: 0, 3: 0}
    for (ori, target, xlabel, ylabel, xlim, ylim, vmin, vmax, slc_lbl) in SLICES:
        fig, ax = plt.subplots(1, 1, figsize=(7, 5))
        fig.subplots_adjust(left=0.10, right=0.88, top=0.88, bottom=0.12)

        ok = plot_single_slice(ax, fig, sim, obsts, holes,
                               ori, target, xlabel, ylabel,
                               xlim, ylim, vmin, vmax, slc_lbl, case_dir)

        fig.suptitle(
            f"{mesh_lbl}  |  {slc_lbl}\n"
            f"Temperature — time-averaged {WIN[0]:.0f}–{WIN[1]:.0f} s",
            fontsize=10,
        )
        tag = axis_tag[ori]
        axis_count[ori] += 1
        suffix = f"{tag}{axis_count[ori]}" if axis_count[ori] > 1 else tag
        out_path = mesh_out / f"slice_{suffix}_{target:.2f}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        if ok:
            print(f"  → {out_path}")

    fig.suptitle(
        f"{mesh_lbl}  [{case_dir}]\n"
        f"Temperature — time-averaged {WIN[0]:.0f}–{WIN[1]:.0f} s",
        fontsize=11,
    )
    out_path = OUT / f"slices_{case_dir}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  → {out_path}\n")


def main():
    for case_dir, mesh_lbl in MESHES:
        print(f"\n=== {mesh_lbl} ===")
        plot_mesh(case_dir, mesh_lbl)


if __name__ == "__main__":
    main()
