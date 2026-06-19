#!/usr/bin/env python3
"""
Vertical-plane slice plots (instantaneous t≈300 s):
  1. PBY = 1.450 m  (XZ plane through fire centroid y) — TEMP underlay +
     in-plane (U, W) quiver.  Shows plume rise and ventilation flow.
  2. PBX = 8.100 m  (YZ plane just west of fire centre) — TEMP contour.
  3. PBX = 8.400 m  (YZ plane just east of fire centre) — TEMP contour.
"""
from __future__ import annotations
import re
import struct
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
JOB  = sys.argv[1] if len(sys.argv) > 1 else "grid_mesh1_756471"
DIR  = ROOT / "Results" / JOB
OUT  = ROOT / "analysis" / "flow_vent"
OUT.mkdir(parents=True, exist_ok=True)


# ----- helpers (same .sf binary reader as plot_vent_uv.py) -----------------
def read_sf(path: Path):
    def rec(f):
        n = struct.unpack("<i", f.read(4))[0]
        b = f.read(n)
        assert struct.unpack("<i", f.read(4))[0] == n
        return b
    with open(path, "rb") as f:
        qty   = rec(f).decode("ascii").strip()
        short = rec(f).decode("ascii").strip()
        units = rec(f).decode("ascii").strip()
        ijk   = struct.unpack("<6i", rec(f))
        i1,i2,j1,j2,k1,k2 = ijk
        nx, ny, nz = i2-i1+1, j2-j1+1, k2-k1+1
        ts, ds = [], []
        while True:
            head = f.read(4)
            if not head: break
            assert struct.unpack("<i", head)[0] == 4
            t = struct.unpack("<f", f.read(4))[0]
            assert struct.unpack("<i", f.read(4))[0] == 4
            sz = struct.unpack("<i", f.read(4))[0]
            buf = f.read(sz)
            assert struct.unpack("<i", f.read(4))[0] == sz
            arr = np.frombuffer(buf, dtype="<f4").reshape((nx, ny, nz), order="F")
            ts.append(t); ds.append(arr)
    return qty, ijk, np.array(ts), np.stack(ds, axis=0)


def smv_slices(smv: Path):
    txt = smv.read_text().splitlines()
    out = []
    for i, line in enumerate(txt):
        if not line.startswith("SLCF"):
            continue
        fn = txt[i+1].strip()
        m  = re.match(r".*_1_(\d+)\.sf$", fn)
        if m:
            out.append((int(m.group(1)), txt[i+2].strip(), fn))
    return out


def mesh_xyz(smv: Path):
    lines = smv.read_text().splitlines()
    for i, l in enumerate(lines):
        if l.strip().startswith("GRID"):
            ijk = lines[i+1].split()
            nx, ny, nz = int(ijk[0]), int(ijk[1]), int(ijk[2])
        if l.strip().startswith("PDIM"):
            d = lines[i+1].split()
            xmin, xmax = float(d[0]), float(d[1])
            ymin, ymax = float(d[2]), float(d[3])
            zmin, zmax = float(d[4]), float(d[5])
    xf = xmin + np.arange(nx+1)*(xmax-xmin)/nx
    yf = ymin + np.arange(ny+1)*(ymax-ymin)/ny
    zf = zmin + np.arange(nz+1)*(zmax-zmin)/nz
    return dict(xf=xf, yf=yf, zf=zf,
                xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, zmin=zmin, zmax=zmax)


def parse_obsts_and_holes(inp: Path):
    txt = inp.read_text()
    obsts, holes = [], []
    for m in re.finditer(r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID", txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        obsts.append(xb)
    for m in re.finditer(r"&HOLE\s+XB=\s*([\d.,\s\-+eE]+?)\s*/", txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        holes.append(xb)
    return obsts, holes


def parse_vents(inp: Path):
    txt = inp.read_text()
    pat = re.compile(
        r"&VENT\s+XB=\s*([\d.,\s\-+eE]+?),\s+SURF_ID='(vent_intake|vent_exhaust|fire)'",
        re.IGNORECASE)
    out = []
    for m in pat.finditer(txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        out.append((xb, m.group(2)))
    return out


# ----- slice index resolution ----------------------------------------------
def collect_planes(slcfs, dir_path):
    """Build a dict keyed by (qty, orientation, position) -> (path, ijk)."""
    out = {}
    for idx, qty, fn in slcfs:
        path = dir_path / fn
        try:
            _, ijk, _, _ = read_sf(path)
        except Exception:
            continue
        i1,i2,j1,j2,k1,k2 = ijk
        # orientation = constant axis
        if i1 == i2:
            orient, pos_idx = "x", i1
        elif j1 == j2:
            orient, pos_idx = "y", j1
        elif k1 == k2:
            orient, pos_idx = "z", k1
        else:
            continue
        out.setdefault((qty.upper(), orient, pos_idx), (path, ijk))
    return out


# ----- per-plot helpers ----------------------------------------------------
def overlay_solids(ax, obsts, holes, axes="xz", y_plane=None, x_plane=None,
                   z_plane=None):
    """Outline OBST regions intersected by the slice plane, and draw HOLE
    voids ONLY as the geometric intersection of the HOLE with each OBST it
    punches through (so the displayed void width matches the actual wall
    thickness, not the HOLE's safety padding)."""
    # 1) draw OBSTs
    for xb in obsts:
        x1,x2,y1,y2,z1,z2 = xb
        if axes == "xz":
            if y_plane is None or not (y1 <= y_plane <= y2): continue
            rect = patches.Rectangle((x1, z1), x2-x1, z2-z1,
                                     linewidth=0.6, edgecolor="black",
                                     facecolor="lightgray", alpha=0.6)
        elif axes == "yz":
            if x_plane is None or not (x1 <= x_plane <= x2): continue
            rect = patches.Rectangle((y1, z1), y2-y1, z2-z1,
                                     linewidth=0.6, edgecolor="black",
                                     facecolor="lightgray", alpha=0.6)
        else:
            continue
        ax.add_patch(rect)

    # 2) draw HOLE ∩ OBST intersections (true voids inside walls)
    def aabb_intersect(a, b):
        return [max(a[0], b[0]), min(a[1], b[1]),
                max(a[2], b[2]), min(a[3], b[3]),
                max(a[4], b[4]), min(a[5], b[5])]

    for h in holes:
        for o in obsts:
            inter = aabb_intersect(h, o)
            if inter[1] <= inter[0] or inter[3] <= inter[2] or inter[5] <= inter[4]:
                continue   # no real intersection
            ix1,ix2,iy1,iy2,iz1,iz2 = inter
            if axes == "xz":
                if y_plane is None or not (iy1 <= y_plane <= iy2): continue
                rect = patches.Rectangle((ix1, iz1), ix2-ix1, iz2-iz1,
                                         linewidth=0.8, edgecolor="green",
                                         facecolor="white", alpha=1.0,
                                         linestyle="--")
            else:
                if x_plane is None or not (ix1 <= x_plane <= ix2): continue
                rect = patches.Rectangle((iy1, iz1), iy2-iy1, iz2-iz1,
                                         linewidth=0.8, edgecolor="green",
                                         facecolor="white", alpha=1.0,
                                         linestyle="--")
            ax.add_patch(rect)


def overlay_vents(ax, vents, axes="xz", y_plane=None, x_plane=None):
    for xb, kind in vents:
        x1,x2,y1,y2,z1,z2 = xb
        color = {"vent_intake": "lime", "vent_exhaust": "red",
                 "fire": "orange"}[kind]
        if axes == "xz":
            if y_plane is None: continue
            if not (y1 <= y_plane <= y2 or y_plane <= y1 <= y_plane+0.05
                    or y_plane <= y2 <= y_plane+0.05): continue
            if abs(y2 - y1) < 1e-6 and abs(y1 - y_plane) > 0.3: continue
            rect = patches.Rectangle((x1, z1), x2-x1, max(z2-z1, 0.05),
                                     linewidth=2, edgecolor=color,
                                     facecolor="none")
        else:
            if x_plane is None: continue
            if not (x1 <= x_plane <= x2): continue
            rect = patches.Rectangle((y1, z1), y2-y1, max(z2-z1, 0.05),
                                     linewidth=2, edgecolor=color,
                                     facecolor="none")
        ax.add_patch(rect)


# ----- main ----------------------------------------------------------------
def main():
    smv = DIR / f"{JOB}.smv"
    inp = ROOT / "inputs" / f"{JOB}.fds"
    geom    = mesh_xyz(smv)
    slcfs   = smv_slices(smv)
    planes  = collect_planes(slcfs, DIR)
    obsts, holes = parse_obsts_and_holes(inp)
    vents   = parse_vents(inp)
    print(f"OBSTs={len(obsts)}  HOLEs={len(holes)}  VENTs={len(vents)}")

    # ------------------------------------------------------------------- #
    # 1) PBY = 1.450 — XZ plane through fire centroid, with (U, W) quiver  #
    # ------------------------------------------------------------------- #
    # find j_face nearest to y=1.45
    j_target = int(np.argmin(np.abs(geom["yf"] - 1.45)))
    y_actual = geom["yf"][j_target]
    print(f"\nXZ slice at y_face={y_actual:.3f}")

    keys_xz = [k for k in planes if k[1] == "y" and k[2] == j_target]
    print(f"  planes at this y-face: {keys_xz}")

    if ("TEMPERATURE", "y", j_target) in planes and \
       ("U-VELOCITY",  "y", j_target) in planes and \
       ("W-VELOCITY",  "y", j_target) in planes:
        path_T, _ = planes[("TEMPERATURE", "y", j_target)]
        path_U, _ = planes[("U-VELOCITY",  "y", j_target)]
        path_W, _ = planes[("W-VELOCITY",  "y", j_target)]
        _, ijk_T, t_T, T = read_sf(path_T)
        _, ijk_U, _,    U = read_sf(path_U)
        _, ijk_W, _,    W = read_sf(path_W)

        # squeeze ny=1 → (nt, nx, nz)
        Tn = T[:, :, 0, :]; Un = U[:, :, 0, :]; Wn = W[:, :, 0, :]
        i1,i2,_,_,k1,k2 = ijk_T
        xn = geom["xf"][i1:i2+1]
        zn = geom["zf"][k1:k2+1]
        i1u,i2u,_,_,k1u,k2u = ijk_U
        xu = geom["xf"][i1u:i2u+1]; zu = geom["zf"][k1u:k2u+1]

        # cell centres for plotting
        nx = min(Tn.shape[1]-1, Un.shape[1]-1)
        nz = min(Tn.shape[2]-1, Wn.shape[2]-1)
        xc = 0.5*(xn[:nx] + xn[1:nx+1])
        zc = 0.5*(zn[:nz] + zn[1:nz+1])

        # last frame
        T_inst = 0.25*(Tn[-1, :nx, :nz] + Tn[-1, 1:nx+1, :nz]
                       + Tn[-1, :nx, 1:nz+1] + Tn[-1, 1:nx+1, 1:nz+1])
        U_inst = 0.5*(Un[-1, :nx, :nz] + Un[-1, :nx, 1:nz+1])  # avg over k only
        W_inst = 0.5*(Wn[-1, :nx, :nz] + Wn[-1, 1:nx+1, :nz])
        t_last = float(t_T[-1])

        # mask velocity inside OBSTs that intersect the y=y_actual plane,
        # so streamlines don't propagate through solids (e.g. main_engine).
        Xc, Zc = np.meshgrid(xc, zc, indexing="ij")
        obst_mask = np.zeros_like(U_inst, dtype=bool)
        for ob in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = ob
            if not (oy1 <= y_actual <= oy2): continue
            obst_mask |= ((Xc >= ox1) & (Xc <= ox2) &
                          (Zc >= oz1) & (Zc <= oz2))
        # HOLEs carve voids through OBSTs at this y plane
        for h in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = h
            if not (hy1 <= y_actual <= hy2): continue
            obst_mask &= ~((Xc >= hx1) & (Xc <= hx2) &
                            (Zc >= hz1) & (Zc <= hz2))
        U_inst[obst_mask] = np.nan
        W_inst[obst_mask] = np.nan
        T_inst[obst_mask] = np.nan

        fig, ax = plt.subplots(figsize=(12, 4.5))
        Xg, Zg = np.meshgrid(xc, zc, indexing="ij")
        # T contour — clip to readable range
        cf = ax.contourf(Xg, Zg, np.clip(T_inst, 20, 600),
                         levels=20, cmap="hot")
        plt.colorbar(cf, ax=ax, label="T (°C)")
        # streamlines — NaN cells are skipped
        speed = np.sqrt(U_inst**2 + W_inst**2)
        ax.streamplot(xc, zc, U_inst.T, W_inst.T,
                      color=np.nan_to_num(speed.T), cmap="cool",
                      linewidth=1.0 + 1.5*np.nan_to_num(speed.T)/max(np.nanmax(speed), 1e-6),
                      density=2.2, arrowsize=1.1)
        overlay_solids(ax, obsts, holes, axes="xz", y_plane=y_actual)
        overlay_vents(ax, vents, axes="xz", y_plane=y_actual)
        ax.set_xlim(geom["xmin"], geom["xmax"])
        ax.set_ylim(geom["zmin"], geom["zmax"])
        ax.set_aspect("equal")
        ax.set_xlabel("x (m)"); ax.set_ylabel("z (m)")
        ax.set_title(f"{JOB} — XZ slice at y={y_actual:.2f} m  (fire-centroid y)\n"
                     f"T contour + (U,W) streamlines, t={t_last:.0f} s")
        out_png = OUT / f"{JOB}_xz_y{y_actual:.3f}.png"
        fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
        print(f"  wrote {out_png}")
        print(f"  T range [{np.nanmin(T_inst):.1f}, {np.nanmax(T_inst):.1f}] °C, "
              f"|U|max={np.nanmax(np.abs(U_inst)):.2f}, |W|max={np.nanmax(np.abs(W_inst)):.2f} m/s")
    else:
        print("  missing TEMP / U / W at this y-face")

    # ------------------------------------------------------------------- #
    # 2,3) PBX = 8.100, 8.400 — YZ planes                                  #
    #      TEMP contour underlay + (V, W) streamlines if available         #
    # ------------------------------------------------------------------- #
    for x_target_m in (8.100, 8.400):
        i_target = int(np.argmin(np.abs(geom["xf"] - x_target_m)))
        x_actual = geom["xf"][i_target]
        key_T = ("TEMPERATURE", "x", i_target)
        if key_T not in planes:
            print(f"\nYZ TEMP not found at x≈{x_target_m}")
            continue
        path_T, ijk_T = planes[key_T]
        _, _, t_T, T = read_sf(path_T)
        _,_,j1,j2,k1,k2 = ijk_T
        Tn = T[:, 0, :, :]                            # (nt, ny, nz)
        yn = geom["yf"][j1:j2+1]
        zn = geom["zf"][k1:k2+1]
        ny = Tn.shape[1]-1; nz = Tn.shape[2]-1
        yc = 0.5*(yn[:ny] + yn[1:ny+1])
        zc = 0.5*(zn[:nz] + zn[1:nz+1])
        T_inst = 0.25*(Tn[-1, :ny, :nz] + Tn[-1, 1:ny+1, :nz]
                       + Tn[-1, :ny, 1:nz+1] + Tn[-1, 1:ny+1, 1:nz+1])
        t_last = float(t_T[-1])

        # ---- in-plane velocity (V, W) — only if both present on this x-face
        key_V = ("V-VELOCITY", "x", i_target)
        key_W = ("W-VELOCITY", "x", i_target)
        have_uv = key_V in planes and key_W in planes
        if have_uv:
            path_V, _ = planes[key_V]
            path_W, _ = planes[key_W]
            _, _, _, Vraw = read_sf(path_V)
            _, _, _, Wraw = read_sf(path_W)
            Vn = Vraw[:, 0, :, :]; Wn = Wraw[:, 0, :, :]
            # average to T cell-centres: V is on y-face, W on z-face
            V_inst = 0.5*(Vn[-1, :ny, :nz] + Vn[-1, :ny, 1:nz+1])
            W_inst = 0.5*(Wn[-1, :ny, :nz] + Wn[-1, 1:ny+1, :nz])
            speed_yz = np.sqrt(V_inst**2 + W_inst**2)

        # mask OBSTs (and carve HOLEs) that intersect the x=x_actual plane
        Yc, Zc = np.meshgrid(yc, zc, indexing="ij")
        obst_mask = np.zeros_like(T_inst, dtype=bool)
        for ob in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = ob
            if not (ox1 <= x_actual <= ox2): continue
            obst_mask |= ((Yc >= oy1) & (Yc <= oy2) &
                          (Zc >= oz1) & (Zc <= oz2))
        for h in holes:
            hx1,hx2,hy1,hy2,hz1,hz2 = h
            if not (hx1 <= x_actual <= hx2): continue
            obst_mask &= ~((Yc >= hy1) & (Yc <= hy2) &
                            (Zc >= hz1) & (Zc <= hz2))
        T_inst[obst_mask] = np.nan
        if have_uv:
            V_inst[obst_mask] = np.nan
            W_inst[obst_mask] = np.nan
            speed_yz[obst_mask] = np.nan

        fig, ax = plt.subplots(figsize=(11, 4.5))
        Yg, Zg = np.meshgrid(yc, zc, indexing="ij")
        cf = ax.contourf(Yg, Zg, np.clip(T_inst, 20, 600),
                         levels=20, cmap="hot")
        plt.colorbar(cf, ax=ax, label="T (°C)")
        if have_uv:
            ax.streamplot(yc, zc, V_inst.T, W_inst.T,
                          color=np.nan_to_num(speed_yz.T), cmap="cool",
                          linewidth=1.0 + 1.5*np.nan_to_num(speed_yz.T)/max(np.nanmax(speed_yz), 1e-6),
                          density=2.0, arrowsize=1.1)
        overlay_solids(ax, obsts, holes, axes="yz", x_plane=x_actual)
        overlay_vents(ax, vents, axes="yz", x_plane=x_actual)
        ax.set_xlim(geom["ymin"], geom["ymax"])
        ax.set_ylim(geom["zmin"], geom["zmax"])
        ax.set_aspect("equal")
        ax.set_xlabel("y (m)"); ax.set_ylabel("z (m)")
        stream_tag = "T contour + (V,W) streamlines" if have_uv else "T contour"
        ax.set_title(f"{JOB} — YZ slice at x={x_actual:.2f} m\n"
                     f"{stream_tag}, t={t_last:.0f} s")
        out_png = OUT / f"{JOB}_yz_x{x_actual:.3f}.png"
        fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
        extra = (f"  |V|max={np.nanmax(np.abs(V_inst)):.2f}  "
                 f"|W|max={np.nanmax(np.abs(W_inst)):.2f} m/s" if have_uv else
                 "  (no V,W on this plane)")
        print(f"  wrote {out_png}  T range [{np.nanmin(T_inst):.1f}, "
              f"{np.nanmax(T_inst):.1f}] °C{extra}")


if __name__ == "__main__":
    main()
