#!/usr/bin/env python3
"""
w_M5 — temperature field + streamlines on all slice planes.
Walls and obstacles are filled solid gray (drawn on top of the field
so data inside solid regions is hidden — no bleeding).

Slices : PBX=8.10, PBX=8.40  (YZ)
         PBY=1.45              (XZ)
         PBZ=0.30, PBZ=2.00, PBZ=2.70  (XY)
Time   : averaged 550–600 s
Output : analysis/vis/w_M5/T_<plane>.png
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging;  logging.disable(logging.CRITICAL)
import re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

plt.rcParams.update({
    "axes.labelsize": 16,
    "axes.titlesize": 18,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 11,
})
import fdsreader
from matplotlib.ticker import FixedLocator, FixedFormatter

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES  = ROOT / "Results"
OUT  = ROOT / "analysis" / "vis" / "w_M5"
OUT.mkdir(parents=True, exist_ok=True)

CASE = "w_M5"
WIN  = (550.0, 600.0)

SLICES = [
    # (ori, target, horiz_label, vert_label, horiz_lim, vert_lim, vmin, vmax)
    (1, 8.10, "Y (m)", "Height (m)", (-0.2, 10.2), (0.0, 3.0),   20, 150),
    (1, 8.40, "Y (m)", "Height (m)", (-0.2, 10.2), (0.0, 3.0),   20, 150),
    (2, 1.45, "X (m)", "Height (m)", (-0.2, 13.2), (0.0, 3.0),   20, 200),
    (3, 0.30, "X (m)", "Y (m)", (-0.2, 13.2), (-0.2, 10.2), 20, 250),
    (3, 2.00, "X (m)", "Y (m)", (-0.2, 13.2), (-0.2, 10.2), 20, 250),
    (3, 2.70, "X (m)", "Y (m)", (-0.2, 13.2), (-0.2, 10.2), 20, 250),
]

VEL = {
    1: ("V-VELOCITY", "W-VELOCITY"),
    2: ("U-VELOCITY", "W-VELOCITY"),
    3: ("U-VELOCITY", "V-VELOCITY"),
}

CMAP    = "jet"
NLEVELS = 40
GRAY    = "#444444"
ORI_ATTR = {1: "x_start", 2: "y_start", 3: "z_start"}

SCALE   = 0.7          # inches per metre — figure sized to the actual domain extent
MARGIN  = (2.4, 1.4)   # (width, height) inches reserved for labels + colorbar


# ── geometry parsing ──────────────────────────────────────────────────────────

def parse_fds(case_id):
    p = ROOT / "inputs" / f"{case_id}.fds"
    txt = p.read_text()

    obsts = []
    for m in re.finditer(
        r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID='([^']+)'", txt
    ):
        vals = [float(v) for v in m.group(1).replace(",", " ").split()]
        if len(vals) == 6:
            obsts.append(vals)

    holes = []
    for m in re.finditer(r"&HOLE\s+XB=\s*([\d.,\s\-+eE]+?)\s*/", txt):
        vals = [float(v) for v in m.group(1).replace(",", " ").split()]
        if len(vals) == 6:
            holes.append(vals)

    return obsts, holes


# ── slice helpers ─────────────────────────────────────────────────────────────

def fill_nan_nearest(arr):
    """Replace NaN cells with the nearest non-NaN neighbour (iterative dilation)."""
    filled = arr.copy()
    nan_mask = np.isnan(filled)
    if not nan_mask.any():
        return filled
    shifts = [(-1, 0), (1, 0), (0, -1), (0, 1),
              (-1, -1), (-1, 1), (1, -1), (1, 1)]
    prev_count = nan_mask.sum() + 1
    while nan_mask.any() and nan_mask.sum() < prev_count:
        prev_count = nan_mask.sum()
        for ds, da in shifts:
            neighbour = np.roll(np.roll(filled, ds, axis=0), da, axis=1)
            replace = nan_mask & ~np.isnan(neighbour)
            filled[replace] = neighbour[replace]
        nan_mask = np.isnan(filled)
    return filled


def find_sl(sim, ori, target, qty_key):
    attr = ORI_ATTR[ori]
    cands = [s for s in sim.slices
             if s.orientation == ori and qty_key in s.quantity.name.upper()]
    return min(cands, key=lambda s: abs(getattr(s.extent, attr) - target)) if cands else None


def tavg(sl):
    t = sl.times
    t_max = t.max()
    if t_max < WIN[0]:
        return None, t_max
    mask = (t >= WIN[0]) & (t <= min(t_max, WIN[1]))
    data = sl.to_global(masked=True, fill=np.nan)
    return np.nanmean(data[mask], axis=0), min(t_max, WIN[1])


# ── geometry drawing ──────────────────────────────────────────────────────────

def cs(xb, ori, coord):
    """Cross-section of XB on slice plane. Returns (a1,a2,b1,b2) or None."""
    x1,x2,y1,y2,z1,z2 = xb
    tol = 1e-6
    if ori == 1:
        if not (x1 - tol <= coord <= x2 + tol): return None
        return y1, y2, z1, z2
    elif ori == 2:
        if not (y1 - tol <= coord <= y2 + tol): return None
        return x1, x2, z1, z2
    else:
        if not (z1 - tol <= coord <= z2 + tol): return None
        return x1, x2, y1, y2


def subtract_rect(outer, inner):
    """Sub-rectangles covering outer minus inner (rectangle with a hole punched out)."""
    a1, a2, b1, b2 = outer
    ha1 = max(inner[0], a1); ha2 = min(inner[1], a2)
    hb1 = max(inner[2], b1); hb2 = min(inner[3], b2)
    if ha1 >= ha2 or hb1 >= hb2:
        return [outer]                       # no overlap — keep whole rect
    pieces = []
    if a1  < ha1: pieces.append((a1,  ha1, b1,  b2 ))  # left
    if ha2 < a2:  pieces.append((ha2, a2,  b1,  b2 ))  # right
    if b1  < hb1: pieces.append((ha1, ha2, b1,  hb1))  # bottom
    if hb2 < b2:  pieces.append((ha1, ha2, hb2, b2 ))  # top
    return pieces


def draw_geometry(ax, obsts, holes, ori, coord):
    """Gray-fill OBST cross-sections with HOLE regions punched out (door openings stay open)."""
    for xb in obsts:
        rect = cs(xb, ori, coord)
        if rect is None:
            continue
        pieces = [rect]
        for hxb in holes:
            hrect = cs(hxb, ori, coord)
            if hrect is None:
                continue
            new_pieces = []
            for p in pieces:
                new_pieces.extend(subtract_rect(p, hrect))
            pieces = new_pieces
        for (a1, a2, b1, b2) in pieces:
            ax.add_patch(mpatches.Rectangle(
                (a1, b1), a2-a1, b2-b1,
                facecolor=GRAY, edgecolor="none", zorder=20,
            ))


# ── main plot routine ─────────────────────────────────────────────────────────

def plot_slice(sim, obsts, holes, ori, target,
               hlabel, vlabel, hlim, vlim, vmin, vmax):

    sl_T = find_sl(sim, ori, target, "TEMP")
    if sl_T is None:
        print(f"  ori={ori} @{target:.2f}: TEMPERATURE slice not found"); return

    raw_T = sl_T.to_global(masked=True, fill=np.nan)
    t     = sl_T.times
    t_max = t.max()
    if t_max < WIN[0]:
        print(f"  ori={ori} @{target:.2f}: only {t_max:.0f} s (< {WIN[0]:.0f})"); return

    mask_t = (t >= WIN[0]) & (t <= min(t_max, WIN[1]))
    T_avg  = np.nanmean(raw_T[mask_t], axis=0)   # (nA, nB)
    T_avg  = fill_nan_nearest(T_avg)              # propagate into wall NaN cells
    t_end  = min(t_max, WIN[1])

    ext = sl_T.extent
    coord = getattr(ext, ORI_ATTR[ori])
    if ori == 1:
        A = np.linspace(ext.y_start, ext.y_end, T_avg.shape[0])
        B = np.linspace(ext.z_start, ext.z_end, T_avg.shape[1])
    elif ori == 2:
        A = np.linspace(ext.x_start, ext.x_end, T_avg.shape[0])
        B = np.linspace(ext.z_start, ext.z_end, T_avg.shape[1])
    else:
        A = np.linspace(ext.x_start, ext.x_end, T_avg.shape[0])
        B = np.linspace(ext.y_start, ext.y_end, T_avg.shape[1])

    # ── figure layout: horizontal colorbar at TOP ────────────────────────────
    dom_w = hlim[1] - hlim[0]
    dom_h = vlim[1] - vlim[0]

    H_LEFT  = 1.5          # y-label margin + space for colorbar label (inches)
    H_RIGHT = 0.25
    H_BOT   = 0.65         # x-label margin
    H_GAP   = 0.20         # gap between plot top and colorbar bottom
    H_CB    = 0.32         # colorbar strip thickness
    H_CBTOP = 0.40         # tick labels above strip + top padding

    fw = dom_w * SCALE + H_LEFT + H_RIGHT
    fh = dom_h * SCALE + H_BOT + H_GAP + H_CB + H_CBTOP

    # axes fractions
    ax_l = H_LEFT / fw
    ax_b = H_BOT  / fh
    ax_w = 1.0 - ax_l - H_RIGHT / fw
    ax_h = (dom_h * SCALE) / fh
    cb_b = (H_BOT + dom_h * SCALE + H_GAP) / fh
    cb_h = H_CB / fh

    fig = plt.figure(figsize=(fw, fh))
    ax  = fig.add_axes([ax_l, ax_b, ax_w, ax_h])
    cax = fig.add_axes([ax_l, cb_b, ax_w, cb_h])

    # ── 9 specific levels ─────────────────────────────────────────────────────
    if abs(vmax - 150) < 1:
        levels_spec = np.array([20.0, 36.25, 52.50, 68.75, 85.0,
                                 101.3, 117.5, 133.8, 150.0])
        tick_strs   = ['20.00', '36.25', '52.50', '68.75', '85.00',
                        '101.3', '117.5', '133.8', '150.0']
    elif abs(vmax - 200) < 1:
        levels_spec = np.linspace(20, 200, 9)
        tick_strs   = [f'{v:.1f}' for v in levels_spec]
    else:
        levels_spec = np.linspace(vmin, vmax, 9)
        tick_strs   = [f'{v:.1f}' for v in levels_spec]

    # Fill range padded by 5 beyond each endpoint (labeled levels_spec unchanged),
    # so the colorbar can have flat rectangular ends instead of pointy extends.
    levels_fill = np.linspace(vmin - 5, vmax + 5, NLEVELS)
    # Clamp out-of-range values to the fill extremes so they take the end (max/min)
    # color instead of being left white. NaNs (outside geometry) stay white.
    T_plot = np.clip(T_avg.T, levels_fill[0], levels_fill[-1])

    # ── contourf + contour lines ──────────────────────────────────────────────
    cf = ax.contourf(A, B, T_plot, levels=levels_fill, cmap=CMAP, extend="neither")
    ax.contour(A, B, T_plot, levels=levels_spec, colors='k',
               linewidths=0.8, alpha=0.9, zorder=3)

    # ── streamlines ──────────────────────────────────────────────────────────
    qa, qb = VEL[ori]
    sl_va = find_sl(sim, ori, target, qa)
    sl_vb = find_sl(sim, ori, target, qb)
    if sl_va is not None and sl_vb is not None:
        raw_a = sl_va.to_global(masked=True, fill=0.0)
        raw_b = sl_vb.to_global(masked=True, fill=0.0)
        mask_v = (sl_va.times >= WIN[0]) & (sl_va.times <= min(sl_va.times.max(), WIN[1]))
        Va = np.nanmean(raw_a[mask_v], axis=0).T
        Vb = np.nanmean(raw_b[mask_v], axis=0).T
        Va = np.nan_to_num(Va)
        Vb = np.nan_to_num(Vb)
        speed = np.sqrt(Va**2 + Vb**2)
        if speed.max() > 0:
            ax.streamplot(A, B, Va, Vb,
                         density=1.5, linewidth=0.7, arrowsize=0.7,
                         color="k", zorder=4)

    # ── axes formatting ───────────────────────────────────────────────────────
    ax.set_xlim(*hlim)
    ax.set_ylim(*vlim)
    ax.set_xlabel(hlabel, fontsize=13)
    ax.set_ylabel(vlabel, fontsize=13)
    ax.tick_params(labelsize=12)
    ax.set_aspect("equal")

    # ── gray walls/obstacles LAST ─────────────────────────────────────────────
    draw_geometry(ax, obsts, holes, ori, coord)

    # ── horizontal colorbar at top ────────────────────────────────────────────
    cbar = fig.colorbar(cf, cax=cax, orientation='horizontal', extend='neither')
    cbar.ax.xaxis.set_major_locator(FixedLocator(levels_spec))
    cbar.ax.xaxis.set_major_formatter(FixedFormatter(tick_strs))
    cbar.ax.xaxis.tick_top()
    cbar.ax.xaxis.set_label_position('top')
    cbar.ax.invert_xaxis()          # 150 (red) on LEFT, 20 (blue) on RIGHT
    cbar.ax.tick_params(labelsize=12, top=True, labeltop=True,
                        bottom=False, labelbottom=False, length=4)

    tag_str = {1: "PBX", 2: "PBY", 3: "PBZ"}[ori]
    coord_str = f"{coord:.2f}".replace(".", "p")
    out = OUT / f"T_{tag_str}_{coord_str}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  → {out}")


def main():
    res_path = RES / CASE
    if not (res_path / f"{CASE}.smv").exists():
        raise FileNotFoundError(f"{res_path}/{CASE}.smv")

    sim = fdsreader.Simulation(str(res_path))
    obsts, holes = parse_fds(CASE)
    print(f"Geometry: {len(obsts)} OBSTs,  {len(holes)} HOLEs")

    for ori, target, hlabel, vlabel, hlim, vlim, vmin, vmax in SLICES:
        plane = {1: "YZ", 2: "XZ", 3: "XY"}[ori]
        print(f"\n{plane} @ {target:.2f}")
        plot_slice(sim, obsts, holes, ori, target,
                   hlabel, vlabel, hlim, vlim, vmin, vmax)

    print("\nDone.")


if __name__ == "__main__":
    main()
