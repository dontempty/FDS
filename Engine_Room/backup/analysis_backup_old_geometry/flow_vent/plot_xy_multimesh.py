#!/usr/bin/env python3
"""
XY plane (PBZ=const) streamlines for multi-mesh runs.  Uses fdsreader to
auto-stitch all sub-mesh slice files into a single global slice, then masks
out OBST cells and overlays vents with explicit direction arrows.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import fdsreader

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
JOB  = sys.argv[1] if len(sys.argv) > 1 else "grid_mesh1_759273"
DIR  = ROOT / "Results" / JOB
INP  = ROOT / "inputs" / f"{JOB}.fds"
OUT  = ROOT / "analysis" / "flow_vent"


def parse_obsts(inp):
    txt = inp.read_text()
    out = []
    for m in re.finditer(r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID", txt):
        out.append([float(v) for v in m.group(1).replace(",", " ").split()])
    return out


def parse_vents(inp):
    pat = re.compile(
        r"&VENT\s+XB=\s*([\d.,\s\-+eE]+?),\s+SURF_ID='(vent_intake|vent_exhaust|fire)'",
        re.IGNORECASE)
    return [([float(v) for v in m.group(1).replace(",", " ").split()], m.group(2))
            for m in pat.finditer(inp.read_text())]


def parse_vent_signs(inp):
    """Return dict {SURF_ID: VEL value}."""
    out = {}
    for m in re.finditer(r"&SURF\s+ID='(vent_intake|vent_exhaust)'[^/]*VEL\s*=\s*([\d.\-]+)", inp.read_text()):
        out[m.group(1)] = float(m.group(2))
    return out


def main():
    sim = fdsreader.Simulation(str(DIR))
    obsts = parse_obsts(INP)
    vents = parse_vents(INP)
    vent_signs = parse_vent_signs(INP)
    print(f"job {JOB}: {len(sim.meshes)} sub-meshes, {len(sim.slices)} slices, "
          f"{len(obsts)} OBSTs, {len(vents)} VENTs")
    print(f"vent_intake VEL={vent_signs.get('vent_intake')}, "
          f"vent_exhaust VEL={vent_signs.get('vent_exhaust')}")

    # Collect XY (orient=3) slices, group by z-position
    by_z = {}  # z -> {qty: slice}
    for sl in sim.slices:
        if sl.orientation != 3: continue
        z = round(sl.extent.z_start, 3)
        by_z.setdefault(z, {})[sl.quantity.name] = sl
    print(f"z planes: {sorted(by_z.keys())}")

    for z_target, qdict in by_z.items():
        # Need TEMPERATURE + at least 2 velocity components for streamlines
        sl_T = qdict.get("TEMPERATURE")
        if sl_T is None: continue
        # try to find V and W; fdsreader may only expose VELOCITY magnitude
        sl_V = qdict.get("V-VELOCITY"); sl_W = qdict.get("W-VELOCITY")
        # Heuristic: for vertical velocity, fdsreader exposes W-VELOCITY.
        # For horizontal, we need U-VELOCITY or VELOCITY mag.
        sl_U_mag = qdict.get("VELOCITY")          # vector magnitude exposed
        T = sl_T.to_global(masked=True, fill=np.nan)[-1]  # (nx, ny)
        ext = sl_T.extent
        nx, ny = T.shape
        xc = np.linspace(ext.x_start, ext.x_end, nx)
        yc = np.linspace(ext.y_start, ext.y_end, ny)

        # OBST mask at this z
        Xc, Yc = np.meshgrid(xc, yc, indexing="ij")
        mask = np.zeros_like(T, dtype=bool)
        for ob in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = ob
            if not (oz1 <= z_target <= oz2): continue
            mask |= ((Xc >= ox1) & (Xc <= ox2) & (Yc >= oy1) & (Yc <= oy2))
        T_plot = T.copy(); T_plot[mask] = np.nan

        # Stitch U, V components from per-subslice vector_data
        def stitch(sl, comp):
            global_ext = sl.extent
            shape = sl.to_global(masked=True, fill=np.nan)[-1].shape  # (nx, ny)
            result = np.full(shape, np.nan)
            dx = (global_ext.x_end - global_ext.x_start) / (shape[0] - 1)
            dy = (global_ext.y_end - global_ext.y_start) / (shape[1] - 1)
            for ss in sl.subslices:
                if ss.vector_data is None or comp not in ss.vector_data: continue
                local = ss.vector_data[comp][-1]   # (nx_l, ny_l) last timestep
                ext = ss.mesh.extent
                i_lo = int(round((ext.x_start - global_ext.x_start) / dx))
                j_lo = int(round((ext.y_start - global_ext.y_start) / dy))
                nx_l, ny_l = local.shape
                result[i_lo:i_lo+nx_l, j_lo:j_lo+ny_l] = local
            return result

        U_inst = V_inst = None
        if sl_U_mag is not None:
            U_inst = stitch(sl_U_mag, 'u'); U_inst[mask] = np.nan
            V_inst = stitch(sl_U_mag, 'v'); V_inst[mask] = np.nan
            speed = np.sqrt(U_inst**2 + V_inst**2)
        else:
            speed = np.full_like(T, np.nan)

        fig, ax = plt.subplots(figsize=(11, 8.5))
        Xg, Yg = np.meshgrid(xc, yc, indexing="ij")
        cf = ax.contourf(Xg, Yg, speed, levels=20, cmap="viridis")
        plt.colorbar(cf, ax=ax, label="|u_h| (m/s)")
        # streamlines
        if U_inst is not None:
            sp = speed
            ax.streamplot(xc, yc, U_inst.T, V_inst.T, color="white",
                          linewidth=0.6 + 2.0*np.nan_to_num(sp.T)/max(np.nanmax(sp), 1e-6),
                          density=2.0, arrowsize=1.2)

        # OBST overlay (gray)
        for ob in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = ob
            if not (oz1 <= z_target <= oz2): continue
            ax.add_patch(patches.Rectangle((ox1, oy1), ox2-ox1, oy2-oy1,
                                           lw=0.6, edgecolor="black",
                                           facecolor="lightgray", alpha=0.9))

        # Vent flow — sample ACTUAL local velocity from the simulated field
        # in a small band just inside the room next to each vent (not the
        # prescribed input VEL).  This shows how the flow is really behaving
        # at the vent, which may differ from the SURF VEL due to surrounding
        # flow conditions.
        def sample_vent(x1, x2, y1, y2, normal):
            # find indices in the slice arrays covering the vent face,
            # offset 1 cell into the room (along inward normal direction)
            ix_lo = int(np.searchsorted(xc, x1)); ix_hi = int(np.searchsorted(xc, x2))
            iy_lo = int(np.searchsorted(yc, y1)); iy_hi = int(np.searchsorted(yc, y2))
            # 2-cell band offset by 1 cell into the room
            if normal == "-y":      # gas at y>y1 (room is +y of solid)
                iy_lo += 1; iy_hi = iy_lo + 2
            elif normal == "+y":    # gas at y<y1 (room is -y of solid)
                iy_hi -= 1; iy_lo = max(iy_hi - 2, 0)
            ix_lo = max(ix_lo, 0); ix_hi = max(ix_hi, ix_lo+1)
            iy_lo = max(iy_lo, 0); iy_hi = max(iy_hi, iy_lo+1)
            v_loc = np.nanmean(V_inst[ix_lo:ix_hi, iy_lo:iy_hi])
            u_loc = np.nanmean(U_inst[ix_lo:ix_hi, iy_lo:iy_hi])
            return u_loc, v_loc

        for xb, kind in vents:
            x1,x2,y1,y2,z1,z2 = xb
            if not (z1 <= z_target <= z2): continue
            if kind == "fire":
                ax.add_patch(patches.Rectangle((x1, y1), x2-x1, y2-y1,
                                               lw=2.5, edgecolor="orange",
                                               facecolor="none"))
                continue
            if   abs(y1 - 0.2) < 1e-3: normal = "-y"   # outer_south (room +y)
            elif abs(y1 - 2.8) < 1e-3: normal = "+y"   # osr_north OSR (OSR -y)
            elif abs(y1 - 3.0) < 1e-3: normal = "-y"   # osr_north MER (MER +y)
            elif abs(y1 - 9.8) < 1e-3: normal = "+y"   # outer_north (MER -y)
            else:                       normal = None
            if U_inst is None or normal is None:
                color, tag = "gray", "?"
                v_normal_local = float('nan')
            else:
                u_loc, v_loc = sample_vent(x1, x2, y1, y2, normal)
                # Velocity component along inward direction (into room)
                if normal == "-y":    v_into = v_loc       # room is +y → +V = into room
                else:                  v_into = -v_loc      # room is -y → -V = into room
                if np.isnan(v_into):
                    color, tag = "gray", "?"
                    v_normal_local = float('nan')
                elif v_into > 0:
                    color = "lime"; tag = f"IN {v_into:.2f}"
                    v_normal_local = v_into
                else:
                    color = "red";  tag = f"OUT {abs(v_into):.2f}"
                    v_normal_local = v_into
            rect = patches.Rectangle((x1, y1), x2-x1, y2-y1,
                                     lw=2.5, edgecolor=color, facecolor="none")
            ax.add_patch(rect)
            cx, cy0 = (x1+x2)/2, (y1+y2)/2
            if not np.isnan(v_normal_local):
                # arrow points in actual flow direction
                if normal == "-y":  dy_arrow = +1 if v_normal_local > 0 else -1
                else:               dy_arrow = -1 if v_normal_local > 0 else +1
                ax.annotate("", xy=(cx, cy0 + dy_arrow*0.5),
                            xytext=(cx, cy0 - dy_arrow*0.5),
                            arrowprops=dict(arrowstyle="->,head_width=0.5",
                                            color=color, lw=3))
            txt_dy = 0.7 if cy0 < 5 else -0.7
            ax.text(cx, cy0 + txt_dy, tag, color=color,
                    fontsize=9, ha="center", va="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                              edgecolor=color, alpha=0.9))

        ax.set_xlim(0, 13); ax.set_ylim(0, 10)
        ax.set_aspect("equal")
        ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
        ax.set_title(f"{JOB} — XY at z={z_target:.3f} m  "
                     f"(intake VEL={vent_signs.get('vent_intake')}, "
                     f"exhaust VEL={vent_signs.get('vent_exhaust')})")
        out_png = OUT / f"{JOB}_uv_z{z_target:.3f}.png"
        fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
        print(f"  wrote {out_png}")


if __name__ == "__main__":
    main()
