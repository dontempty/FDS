#!/usr/bin/env python3
"""
YZ-plane TEMP slice plots for multi-mesh runs (e.g. Mesh 6 = 32 sub-meshes).
Uses fdsreader for automatic multi-mesh stitching at PBX slices.

For runs that DO have V/W velocity at PBX (added after this run was submitted),
streamlines are overlaid on top of the TEMP contour.  For runs without, only
TEMP is drawn.

Usage:
    python3 plot_yz_multimesh.py grid_mesh6_756425
    python3 plot_yz_multimesh.py grid_mesh1_756526   # works for single mesh too
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
JOB  = sys.argv[1] if len(sys.argv) > 1 else "grid_mesh6_756425"
DIR  = ROOT / "Results" / JOB
INP  = ROOT / "inputs" / f"{JOB}.fds"
OUT  = ROOT / "analysis" / "flow_vent"

# If 'avg' passed as 2nd CLI arg, plot time-averaged T (100→end) instead of
# the last instantaneous snapshot.  Streamlines remain instantaneous (avg of
# velocity vector field is less meaningful for ventilation studies).
MODE = sys.argv[2] if len(sys.argv) > 2 else "inst"
AVG_START = 100.0   # seconds


def parse_obsts_and_holes(inp: Path):
    """Return obsts as list of (XB, SURF_ID), holes as list of XB."""
    txt = inp.read_text()
    obsts, holes = [], []
    for m in re.finditer(r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID='([^']+)'", txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        sid = m.group(2)
        obsts.append((xb, sid))
    for m in re.finditer(r"&HOLE\s+XB=\s*([\d.,\s\-+eE]+?)\s*/", txt):
        holes.append([float(v) for v in m.group(1).replace(",", " ").split()])
    return obsts, holes


def parse_cold_surfs(inp: Path):
    """Return {SURF_ID: TMP_FRONT} for SURFs with no MATL_ID (isothermal)."""
    txt = inp.read_text()
    cold = {}
    for m in re.finditer(r"&SURF\s+ID='([^']+)'[^/]*TMP_FRONT\s*=\s*([\d.]+)[^/]*/", txt):
        sid, tmp = m.group(1), float(m.group(2))
        # block must not contain MATL_ID
        block = m.group(0)
        if "MATL_ID" not in block and sid not in ("vent_intake", "vent_exhaust", "fire"):
            cold[sid] = tmp
    return cold


def parse_vents(inp: Path):
    pat = re.compile(
        r"&VENT\s+XB=\s*([\d.,\s\-+eE]+?),\s+SURF_ID='(vent_intake|vent_exhaust|fire)'",
        re.IGNORECASE)
    out = []
    for m in pat.finditer(inp.read_text()):
        out.append(([float(v) for v in m.group(1).replace(",", " ").split()],
                    m.group(2)))
    return out


def overlay_solids(ax, obsts, holes, x_plane, cold_surfs=None):
    """OBST gray (or skipped if cold-sink, so contour color shows through);
    HOLE∩OBST as white void."""
    cold_surfs = cold_surfs or {}
    for xb, sid in obsts:
        if sid in cold_surfs:
            continue   # cold-sink OBST already filled by contour
        x1,x2,y1,y2,z1,z2 = xb
        if not (x1 <= x_plane <= x2): continue
        ax.add_patch(patches.Rectangle((y1, z1), y2-y1, z2-z1,
                                       lw=0.6, edgecolor="black",
                                       facecolor="lightgray", alpha=0.6))

    def inter(a, b):
        return [max(a[0], b[0]), min(a[1], b[1]),
                max(a[2], b[2]), min(a[3], b[3]),
                max(a[4], b[4]), min(a[5], b[5])]

    for h in holes:
        for xb, _ in obsts:
            ix = inter(h, xb)
            if ix[1] <= ix[0] or ix[3] <= ix[2] or ix[5] <= ix[4]: continue
            ix1,ix2,iy1,iy2,iz1,iz2 = ix
            if not (ix1 <= x_plane <= ix2): continue
            ax.add_patch(patches.Rectangle((iy1, iz1), iy2-iy1, iz2-iz1,
                                           lw=0.8, edgecolor="green",
                                           facecolor="white",
                                           alpha=1.0, linestyle="--"))


def overlay_vents(ax, vents, x_plane):
    for xb, kind in vents:
        x1,x2,y1,y2,z1,z2 = xb
        if not (x1 <= x_plane <= x2): continue
        color = {"vent_intake": "lime", "vent_exhaust": "red",
                 "fire": "orange"}[kind]
        ax.add_patch(patches.Rectangle((y1, z1), y2-y1, max(z2-z1, 0.05),
                                       lw=2, edgecolor=color, facecolor="none"))


def main():
    if not DIR.exists():
        sys.exit(f"missing {DIR}")

    sim    = fdsreader.Simulation(str(DIR))
    obsts, holes = parse_obsts_and_holes(INP)
    vents  = parse_vents(INP)
    cold_surfs = parse_cold_surfs(INP)
    print(f"job {JOB}: {len(sim.meshes)} sub-meshes, {len(sim.slices)} slices "
          f"({len(obsts)} OBSTs, {len(holes)} HOLEs, {len(vents)} VENTs, "
          f"{len(cold_surfs)} cold-sink SURFs)")

    # collect TEMP slices and VELOCITY (vector) slices at PBX = const.
    # For multi-mesh runs, fdsreader exposes 'VELOCITY' (magnitude) at PBX=const
    # but the U/V/W components are buried in each subslice.vector_data dict.
    yz_temp = []
    yz_vec  = []
    for sl in sim.slices:
        if sl.orientation != 1: continue
        x = sl.extent.x_start
        q = sl.quantity.name.upper()
        if q == "TEMPERATURE":  yz_temp.append((round(x, 3), sl))
        elif q == "VELOCITY":   yz_vec.append((round(x, 3), sl))
    print(f"YZ TEMP planes:    {[x for x,_ in yz_temp]}")
    print(f"YZ VELOCITY (vec): {[x for x,_ in yz_vec]}")
    vec_by_x = dict(yz_vec)

    def stitch_yz(sl, comp):
        """Stitch a 'v' or 'w' component across all subslices into a YZ array.
        Returns 2D (ny, nz) of the last timestep, NaN where no data."""
        global_T = sl.to_global(masked=True, fill=np.nan)[-1]   # (ny, nz)
        ny, nz = global_T.shape
        ext = sl.extent
        dy = (ext.y_end - ext.y_start) / (ny - 1)
        dz = (ext.z_end - ext.z_start) / (nz - 1)
        result = np.full((ny, nz), np.nan)
        for ss in sl.subslices:
            if ss.vector_data is None or comp not in ss.vector_data: continue
            local = ss.vector_data[comp][-1]        # (ny_l, nz_l)
            mext = ss.mesh.extent
            j_lo = int(round((mext.y_start - ext.y_start) / dy))
            k_lo = int(round((mext.z_start - ext.z_start) / dz))
            ny_l, nz_l = local.shape
            result[j_lo:j_lo+ny_l, k_lo:k_lo+nz_l] = local
        return result

    for x_face, sl_T in yz_temp:
        T = sl_T.to_global(masked=True, fill=np.nan)   # (nt, ny, nz) or similar
        t = sl_T.times
        if T.ndim != 3:
            print(f"  unexpected T shape {T.shape}, skip x={x_face}")
            continue
        if MODE == "avg":
            window = t >= AVG_START
            T_inst = np.nanmean(T[window], axis=0)
            t_label = f"avg {AVG_START:.0f}→{t[-1]:.0f} s"
        else:
            T_inst = T[-1]
            t_label = f"t={t[-1]:.0f} s"
        t_last = float(t[-1])

        # build y, z axes from extent
        ny, nz = T_inst.shape
        ext = sl_T.extent
        yc = np.linspace(ext.y_start, ext.y_end, ny)
        zc = np.linspace(ext.z_start, ext.z_end, nz)

        # mask OBSTs that intersect the x=x_face plane (HOLE carves voids).
        # Cold-sink OBSTs are FILLED with their TMP_FRONT (so they appear in
        # the contour as a solid colored block).  Others are NaN'd and drawn
        # gray by overlay_solids.
        Yc, Zc = np.meshgrid(yc, zc, indexing="ij")
        obst_mask_gray = np.zeros_like(T_inst, dtype=bool)
        cold_fill = np.full_like(T_inst, np.nan)
        for xb, sid in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = xb
            if not (ox1 <= x_face <= ox2): continue
            in_box = ((Yc >= oy1) & (Yc <= oy2) &
                      (Zc >= oz1) & (Zc <= oz2))
            if sid in cold_surfs:
                cold_fill[in_box] = cold_surfs[sid]
            else:
                obst_mask_gray |= in_box
        for h in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = h
            if not (hx1 <= x_face <= hx2): continue
            in_h = ((Yc >= hy1) & (Yc <= hy2) &
                    (Zc >= hz1) & (Zc <= hz2))
            obst_mask_gray &= ~in_h
            cold_fill[in_h] = np.nan
        T_plot = T_inst.copy()
        T_plot[obst_mask_gray] = np.nan
        # apply cold fill where set (cold-sink OBSTs)
        cm = ~np.isnan(cold_fill)
        T_plot[cm] = cold_fill[cm]
        # for streamline masking, cold-sink OBSTs are still solid (no flow)
        obst_mask = obst_mask_gray | cm

        fig, ax = plt.subplots(figsize=(11, 4.5))
        Yg, Zg = np.meshgrid(yc, zc, indexing="ij")
        # Paper Fig 18 scale: 20-150 °C with rainbow-like colormap (cold→hot).
        # contourf with explicit levels matches paper's 8 contour bands.
        levels = np.linspace(20, 150, 14)
        cf = ax.contourf(Yg, Zg, T_plot, levels=levels, cmap="jet", extend="max")
        plt.colorbar(cf, ax=ax, label="T (°C)",
                     ticks=[20, 36.25, 52.5, 68.75, 85.0, 101.3, 117.5, 133.8, 150])

        # streamlines from VELOCITY (vector) slice — stitch V and W per subslice
        have_vw = x_face in vec_by_x
        if have_vw:
            V = stitch_yz(vec_by_x[x_face], 'v'); V[obst_mask] = np.nan
            W = stitch_yz(vec_by_x[x_face], 'w'); W[obst_mask] = np.nan
            sp = np.sqrt(V**2 + W**2)
            try:
                ax.streamplot(yc, zc, V.T, W.T,
                              color=np.nan_to_num(sp.T), cmap="cool",
                              linewidth=1.0 + 1.5*np.nan_to_num(sp.T)/max(np.nanmax(sp), 1e-6),
                              density=2.0, arrowsize=1.1)
            except Exception as e:
                print(f"  streamplot failed at x={x_face}: {e}")

        overlay_solids(ax, obsts, holes, x_face, cold_surfs=cold_surfs)
        overlay_vents(ax, vents, x_face)
        ax.set_xlim(0, 10); ax.set_ylim(0, 3)
        ax.set_aspect("equal")
        ax.set_xlabel("y (m)"); ax.set_ylabel("z (m)")
        ttl_extra = "T + (V,W) streamlines" if have_vw else "T contour (no V/W)"
        ax.set_title(f"{JOB} — YZ slice at x={x_face:.2f} m  ({ttl_extra}), "
                     f"{t_label}")
        suffix = "_avg" if MODE == "avg" else ""
        out_png = OUT / f"{JOB}_yz_x{x_face:.3f}{suffix}.png"
        fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
        Tmax = float(np.nanmax(T_inst)) if np.isfinite(T_inst).any() else float("nan")
        print(f"  wrote {out_png}  T_max={Tmax:.1f} °C")


if __name__ == "__main__":
    main()
