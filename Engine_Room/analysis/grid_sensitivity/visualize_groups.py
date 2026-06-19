#!/usr/bin/env python3
"""
Generate slice visualizations for all sensitivity cases, organized by group.

For each case, produces 5 slice plots at the new fixed SLCF positions:
    XZ at y=1.45     (PBY plane — paper Fig 6 longitudinal)
    YZ at x=8.10     (PBX plane — paper Fig 6 monitoring slice)
    XY at z=0.30     (PBZ plane — floor area)
    XY at z=2.00     (PBZ plane — engine top)
    XY at z=2.70     (PBZ plane — ceiling smoke layer)

Output structure:
    analysis/sensitivity/visualizations/
        baseline/   grid_mesh1_764327_{xz_y1.45, yz_x8.10, xy_z0.30, ...}.png
        A/          sens_A1a_kappa_0p5_*.png  sens_A1b_kappa_1p0_*.png  ...
        B/          ...
        C/  D/  E/
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)
import re, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES_DIR = ROOT / "Results"
OUT_BASE = ROOT / "analysis" / "sensitivity" / "visualizations"

# Per-plane temperature ranges and tick counts (9 ticks, 30 contour levels)
PLANE_RANGE = {
    "yz": (20.0, 150.0),    # YZ at x=8.10  (through fire flank)
    "xz": (20.0, 200.0),    # XZ at y=1.45  (longitudinal through fire)
    "xy_floor":   (20.0, 250.0),    # XY at z=0.3
    "xy_engine":  (20.0, 250.0),    # XY at z=2.0
    "xy_ceiling": (20.0, 250.0),    # XY at z=2.7
}
AVG_START = 100.0
N_TICKS = 9
N_LEVELS = 30

# All sensitivity cases grouped
GROUPS = {
    "baseline": [("grid_mesh1_764327", "baseline")],
    "A": [
        ("sens_A1a_kappa_0p5",       "KAPPA0=0.5"),
        ("sens_A1b_kappa_1p0",       "KAPPA0=1.0"),
        ("sens_A1c_kappa_2p5",       "KAPPA0=2.5"),
        ("sens_A1d_kappa_3p0",       "KAPPA0=3.0"),
        ("sens_A2a_radfrac_0p2",     "RAD_FRAC=0.2"),
        ("sens_A2b_radfrac_0p4",     "RAD_FRAC=0.4"),
        ("sens_A3a_soot_0p02",       "SOOT=0.02"),
        ("sens_A3b_soot_0p10",       "SOOT=0.10"),
        ("sens_A4a_hrr_700",         "HRR=700"),
        ("sens_A4b_hrr_1100",        "HRR=1100"),
    ],
    "B": [
        ("sens_B1a_floor_thick_0p005",  "floor_thick=0.005"),
        ("sens_B1b_floor_thick_0p05",   "floor_thick=0.05"),
        ("sens_B1c_floor_thick_0p2",    "floor_thick=0.2"),
        ("sens_B2_floor_backing_exposed","floor BACKING=EXPOSED"),
        ("sens_B3_floor_coldsink20",    "floor=20C cold sink"),
    ],
    "C": [
        ("sens_C1a_divider_thick_0p05", "divider_thick=0.05"),
        ("sens_C1b_divider_thick_0p5",  "divider_thick=0.5"),
        ("sens_C2_divider_backing_insulated", "divider BACKING=INSULATED"),
        ("sens_C3_divider_inert",       "divider=INERT"),
    ],
    "D": [
        ("sens_D1_walls_insulated_steel","walls INSULATED steel"),
        ("sens_D2_walls_coldsink20",    "walls=20C cold sink"),
        ("sens_D3_walls_exposed_steel", "walls EXPOSED steel 0.2m"),
    ],
    "E": [
        ("sens_E1_engine_tmp20",        "engine=20C cold sink"),
        ("sens_E2a_engine_thick_0p001", "engine_thick=0.001"),
        ("sens_E2b_engine_thick_0p05",  "engine_thick=0.05"),
        ("sens_E2c_engine_thick_0p2",   "engine_thick=0.2"),
        ("sens_E3_engine_backing_exposed","engine BACKING=EXPOSED"),
    ],
    "OPT": [
        ("sens_OPT1_combined",       "OPT1: engine_thick=0.2 + cold-walls + KAPPA0=1.0 + SOOT=0.10 + floor EXPOSED"),
        ("sens_OPT2_engine_walls",   "OPT2: engine_thick=0.2 + cold-walls only"),
    ],
}

# 5 fixed slice positions
SLICES = [
    ("xz",          "PBY", 1.45,  "y=1.45"),   # XZ longitudinal
    ("yz",          "PBX", 8.10,  "x=8.10"),   # YZ flank
    ("xy_floor",    "PBZ", 0.30,  "z=0.30"),   # floor
    ("xy_engine",   "PBZ", 2.00,  "z=2.00"),   # engine top
    ("xy_ceiling",  "PBZ", 2.70,  "z=2.70"),   # ceiling
]


def parse_input(case_id):
    """Parse OBSTs (with SURF_ID) and HOLEs from input fds."""
    p = ROOT / "inputs" / f"{case_id}.fds"
    if not p.exists(): return [], []
    txt = p.read_text()
    obsts = []
    for m in re.finditer(r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID='([^']+)'", txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        obsts.append((xb, m.group(2)))
    holes = []
    for m in re.finditer(r"&HOLE\s+XB=\s*([\d.,\s\-+eE]+?)\s*/", txt):
        holes.append([float(v) for v in m.group(1).replace(",", " ").split()])
    return obsts, holes


def find_slice(sim, orient, target):
    """Find TEMPERATURE SLCF at given orientation closest to target."""
    cands = [(abs(getattr(sl.extent,
                          "x_start" if orient == 1 else
                          "y_start" if orient == 2 else "z_start") - target), sl)
             for sl in sim.slices
             if sl.orientation == orient and sl.quantity.name == "TEMPERATURE"]
    if not cands: return None
    return min(cands, key=lambda t: t[0])[1]


def is_osr_mer_divider(xb):
    x1,x2,y1,y2,z1,z2 = xb
    return (abs(x1 - 4.0) < 0.05 and abs(x2 - 12.8) < 0.05 and
            abs(y1 - 2.8) < 0.05 and abs(y2 - 3.0) < 0.05)


def plot_slice(case_id, label, sim, plane_key, pb_axis, target,
               obsts, holes, out_path):
    """Plot one slice with paper-style colormap, OBST overlay, NaN fill."""
    orient = {"PBX": 1, "PBY": 2, "PBZ": 3}[pb_axis]
    sl = find_slice(sim, orient, target)
    if sl is None:
        print(f"   - no {plane_key} slice"); return False

    T = sl.to_global(masked=True, fill=np.nan)
    t = sl.times
    win = t >= AVG_START
    if not win.any():
        T_inst = T[-1]; tlabel = f"t={t[-1]:.0f}s"
    else:
        T_inst = np.nanmean(T[win], axis=0); tlabel = f"avg {AVG_START:.0f}->{t[-1]:.0f}s"

    ext = sl.extent
    nA, nB = T_inst.shape
    if plane_key.startswith("xy"):
        A = np.linspace(ext.x_start, ext.x_end, nA); A_lbl = "X (m)"
        B = np.linspace(ext.y_start, ext.y_end, nB); B_lbl = "Y (m)"
        lim_A = (0, 13); lim_B = (0, 10)
    elif plane_key == "xz":
        A = np.linspace(ext.x_start, ext.x_end, nA); A_lbl = "X (m)"
        B = np.linspace(ext.z_start, ext.z_end, nB); B_lbl = "Z (m)"
        lim_A = (0, 13); lim_B = (0, 3)
    elif plane_key == "yz":
        A = np.linspace(ext.y_start, ext.y_end, nA); A_lbl = "Y (m)"
        B = np.linspace(ext.z_start, ext.z_end, nB); B_lbl = "Z (m)"
        lim_A = (0, 10); lim_B = (0, 3)
    Ag, Bg = np.meshgrid(A, B, indexing="ij")

    # Fill HOLE NaN cells with neighbour mean (so doorways aren't white)
    dA, dB = A[1]-A[0], B[1]-B[0]
    for hxb in holes:
        hx1,hx2,hy1,hy2,hz1,hz2 = hxb
        if plane_key.startswith("xy"):
            if not (hz1 <= target <= hz2): continue
            a1,a2,b1,b2 = hx1,hx2,hy1,hy2
        elif plane_key == "xz":
            if not (hy1 <= target <= hy2): continue
            a1,a2,b1,b2 = hx1,hx2,hz1,hz2
        elif plane_key == "yz":
            if not (hx1 <= target <= hx2): continue
            a1,a2,b1,b2 = hy1,hy2,hz1,hz2
        in_box = (Ag>=a1-dA)&(Ag<=a2+dA)&(Bg>=b1-dB)&(Bg<=b2+dB)
        nan_in = in_box & np.isnan(T_inst)
        valid_in = in_box & ~np.isnan(T_inst)
        if nan_in.any() and valid_in.any():
            T_inst[nan_in] = float(np.nanmean(T_inst[valid_in]))

    # NaN out OBST interior cells (avoid SLCF node interpolation leakage)
    for xb, sid in obsts:
        ox1,ox2,oy1,oy2,oz1,oz2 = xb
        if plane_key.startswith("xy") and not (oz1 <= target <= oz2): continue
        if plane_key == "xz" and not (oy1 <= target <= oy2): continue
        if plane_key == "yz" and not (ox1 <= target <= ox2): continue
        if plane_key.startswith("xy"): a1,a2,b1,b2 = ox1,ox2,oy1,oy2
        elif plane_key == "xz": a1,a2,b1,b2 = ox1,ox2,oz1,oz2
        elif plane_key == "yz": a1,a2,b1,b2 = oy1,oy2,oz1,oz2
        in_box = (Ag>=a1)&(Ag<=a2)&(Bg>=b1)&(Bg<=b2)
        # carve out HOLE cells
        for hxb in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = hxb
            if plane_key.startswith("xy") and not (hz1 <= target <= hz2): continue
            if plane_key == "xz" and not (hy1 <= target <= hy2): continue
            if plane_key == "yz" and not (hx1 <= target <= hx2): continue
            if plane_key.startswith("xy"): h_a1,h_a2,h_b1,h_b2 = hx1,hx2,hy1,hy2
            elif plane_key == "xz": h_a1,h_a2,h_b1,h_b2 = hx1,hx2,hz1,hz2
            elif plane_key == "yz": h_a1,h_a2,h_b1,h_b2 = hy1,hy2,hz1,hz2
            in_box &= ~((Ag>=h_a1)&(Ag<=h_a2)&(Bg>=h_b1)&(Bg<=h_b2))
        T_inst[in_box] = np.nan

    vmin, vmax = PLANE_RANGE[plane_key]
    ticks  = np.linspace(vmin, vmax, N_TICKS).tolist()
    levels = np.linspace(vmin, vmax, N_LEVELS)

    fig, ax = plt.subplots(figsize=(11, 7))
    cf = ax.contourf(Ag, Bg, T_inst, levels=levels, cmap="jet", extend="both")
    cf.cmap.set_under(plt.cm.jet(0.0))
    plt.colorbar(cf, ax=ax, label="Temperature (°C)", ticks=ticks)

    # OBST overlay
    for xb, sid in obsts:
        x1,x2,y1,y2,z1,z2 = xb
        if plane_key.startswith("xy") and not (z1 <= target <= z2): continue
        if plane_key == "xz" and not (y1 <= target <= y2): continue
        if plane_key == "yz" and not (x1 <= target <= x2): continue
        if plane_key.startswith("xy"): a_lo,a_hi,b_lo,b_hi = x1,x2,y1,y2
        elif plane_key == "xz": a_lo,a_hi,b_lo,b_hi = x1,x2,z1,z2
        elif plane_key == "yz": a_lo,a_hi,b_lo,b_hi = y1,y2,z1,z2
        if is_osr_mer_divider(xb):
            # split BLACK fill around HOLE openings
            hxs = []
            for hxb in holes:
                hx1,hx2,hy1,hy2,hz1,hz2 = hxb
                if plane_key.startswith("xy"):
                    if not (hz1 <= target <= hz2): continue
                    hxs.append((hx1, hx2))
                elif plane_key == "yz":
                    if not (hx1 <= target <= hx2): continue
                    hxs.append((hz1, hz2))
                elif plane_key == "xz":
                    if not (hy1 <= target <= hy2): continue
                    hxs.append((hx1, hx2))
            hxs.sort()
            seg = a_lo
            for hl, hh in hxs:
                seg_end = max(seg, min(a_hi, hl))
                if seg_end > seg:
                    ax.add_patch(patches.Rectangle((seg, b_lo), seg_end-seg,
                                                   b_hi-b_lo, lw=0, facecolor="black"))
                seg = max(seg, min(a_hi, hh))
            if seg < a_hi:
                ax.add_patch(patches.Rectangle((seg, b_lo), a_hi-seg,
                                               b_hi-b_lo, lw=0, facecolor="black"))
        else:
            ax.add_patch(patches.Rectangle((a_lo, b_lo), a_hi-a_lo,
                                           b_hi-b_lo, lw=1.0, edgecolor="black",
                                           facecolor="none"))

    ax.set_xlim(*lim_A); ax.set_ylim(*lim_B)
    ax.set_aspect("equal")
    ax.set_xlabel(A_lbl); ax.set_ylabel(B_lbl)
    plane_disp = {"xz":"XZ","yz":"YZ",
                  "xy_floor":"XY","xy_engine":"XY","xy_ceiling":"XY"}[plane_key]
    const_disp = pb_axis[-1].lower()
    ax.set_title(f"{label}  [{case_id}]\n"
                 f"{plane_disp} @ {const_disp}={target:.2f} m  ({tlabel})")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def process_case(case_id, label, group_dir):
    """Generate 5 slices for one case."""
    case_res = RES_DIR / case_id
    if not (case_res / f"{case_id}.smv").exists():
        print(f"  skip {case_id} (no .smv)"); return
    try:
        sim = fdsreader.Simulation(str(case_res))
    except Exception as e:
        print(f"  fdsreader fail for {case_id}: {e}"); return
    obsts, holes = parse_input(case_id)
    print(f"  {case_id} ({label}): {len(sim.slices)} slices, "
          f"{len(obsts)} OBSTs, {len(holes)} HOLEs")
    n_ok = 0
    for plane_key, pb_axis, target, tag in SLICES:
        out_path = group_dir / f"{case_id}_{plane_key}_{tag.replace('=','')}.png"
        try:
            if plot_slice(case_id, label, sim, plane_key, pb_axis, target,
                          obsts, holes, out_path):
                n_ok += 1
        except Exception as e:
            print(f"     {plane_key} failed: {e}")
    print(f"     → {n_ok}/5 slices saved")


def main():
    only_group = sys.argv[1] if len(sys.argv) > 1 else None
    for group, cases in GROUPS.items():
        if only_group and group != only_group: continue
        group_dir = OUT_BASE / group
        group_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Group {group} ({len(cases)} cases) → {group_dir} ===")
        for case_id, label in cases:
            process_case(case_id, label, group_dir)


if __name__ == "__main__":
    main()
