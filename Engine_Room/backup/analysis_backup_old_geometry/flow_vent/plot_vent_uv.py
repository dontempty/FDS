#!/usr/bin/env python3
"""
Plot instantaneous (U, V) horizontal velocity field at the two vent z-midplane
slices (z=0.333 m and z=2.667 m) for a single Method-2 run.  Visualises
inlet/outlet flow direction.

Usage:  python3 plot_vent_uv.py [<JOBID>]
        (default = grid_mesh1_756471)
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

# ---------------------------------------------------------------- .sf reader
def read_sf(path: Path):
    """Parse FDS sequential-unformatted slice file.
    Returns (quantity, short, units, ijk_bounds, times[T], data[T, NX, NY, NZ])."""
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
        n = nx*ny*nz
        ts, ds = [], []
        while True:
            head = f.read(4)
            if not head: break
            assert struct.unpack("<i", head)[0] == 4
            t = struct.unpack("<f", f.read(4))[0]
            assert struct.unpack("<i", f.read(4))[0] == 4
            # data record
            sz = struct.unpack("<i", f.read(4))[0]
            buf = f.read(sz)
            assert struct.unpack("<i", f.read(4))[0] == sz
            arr = np.frombuffer(buf, dtype="<f4").reshape((nx, ny, nz), order="F")
            ts.append(t); ds.append(arr)
    return qty, short, units, ijk, np.array(ts), np.stack(ds, axis=0)


# ---------------------------------------------------------------- .smv parse
def smv_slices(smv: Path):
    """Yield (file_index, qty_name, ijk_smv, orient) per SLCF record in .smv."""
    txt = smv.read_text().splitlines()
    out = []
    for i, line in enumerate(txt):
        if not line.startswith("SLCF"):
            continue
        # next line is filename "<chid>_1_<N>.sf"
        fn = txt[i+1].strip()
        qty = txt[i+2].strip()
        m   = re.match(r".*_1_(\d+)\.sf$", fn)
        if not m: continue
        out.append((int(m.group(1)), qty, fn))
    return out


# ---------------------------------------------------------------- mesh extents
def mesh_xyz(smv: Path):
    """Extract first mesh GRID and TRNX/TRNY/TRNZ to build cell-centre coords."""
    lines = smv.read_text().splitlines()
    # find GRID line
    for i, l in enumerate(lines):
        if l.strip().startswith("GRID"):
            ijk = lines[i+1].split()
            nx, ny, nz = int(ijk[0]), int(ijk[1]), int(ijk[2])
        if l.strip().startswith("PDIM"):
            d = lines[i+1].split()
            xmin, xmax = float(d[0]), float(d[1])
            ymin, ymax = float(d[2]), float(d[3])
            zmin, zmax = float(d[4]), float(d[5])
    # cell-centre vectors (nx cells)
    dx = (xmax-xmin)/nx; dy = (ymax-ymin)/ny; dz = (zmax-zmin)/nz
    xc = xmin + (np.arange(nx)+0.5)*dx
    yc = ymin + (np.arange(ny)+0.5)*dy
    zc = zmin + (np.arange(nz)+0.5)*dz
    # face coords
    xf = xmin + np.arange(nx+1)*dx
    yf = ymin + np.arange(ny+1)*dy
    zf = zmin + np.arange(nz+1)*dz
    return dict(xc=xc, yc=yc, zc=zc, xf=xf, yf=yf, zf=zf,
                xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, zmin=zmin, zmax=zmax)


# ---------------------------------------------------------------- vent list
def parse_vents(inp: Path):
    """Pull HVAC vent XB rectangles + SURF id from the .fds input."""
    txt = inp.read_text()
    pat = re.compile(
        r"&VENT\s+XB=\s*([\d.,\s\-+eE]+?),\s+SURF_ID='(vent_intake|vent_exhaust)'",
        re.IGNORECASE)
    out = []
    for m in pat.finditer(txt):
        xb = [float(v) for v in m.group(1).replace(",", " ").split()]
        kind = "HVAC_INLET" if m.group(2) == "vent_intake" else "HVAC_OUTLET"
        out.append((xb, kind))
    return out


def parse_obsts(inp: Path):
    """Pull OBST XB rectangles from the .fds input (used for masking and overlay)."""
    txt = inp.read_text()
    out = []
    for m in re.finditer(r"&OBST\s+XB=\s*([\d.,\s\-+eE]+?)\s*,\s*SURF_ID", txt):
        out.append([float(v) for v in m.group(1).replace(",", " ").split()])
    return out


# ---------------------------------------------------------------- main
def main():
    smv = DIR / f"{JOB}.smv"
    inp = ROOT / "inputs" / f"{JOB}.fds"
    if not smv.exists():
        sys.exit(f"missing {smv}")

    geom  = mesh_xyz(smv)
    vents = parse_vents(inp) if inp.exists() else []
    obsts = parse_obsts(inp) if inp.exists() else []
    print(f"Found {len(vents)} HVAC vents and {len(obsts)} OBSTs in {inp.name}")

    slcfs = smv_slices(smv)
    # group by qty + z (rounded)
    wanted = {}  # (qty, z_round) -> filename
    for idx, qty, fn in slcfs:
        # find sf file and peek ijk to determine plane height
        path = DIR / fn
        try:
            q, _, _, ijk, _, _ = read_sf(path)
        except Exception as e:
            print(f"skip {fn}: {e}")
            continue
        i1,i2,j1,j2,k1,k2 = ijk
        # z plane <=> k1 == k2 (constant z)
        if k1 != k2:
            continue
        z_val = geom["zf"][k1]    # face position (slice is on a face)
        key = (q.upper(), round(z_val, 3))
        wanted[key] = (path, ijk)

    # extract U, V at each z target
    targets = sorted({z for (_, z) in wanted.keys()})
    print(f"available z-planes: {targets}")

    for z_target in targets:
        u_key = ("U-VELOCITY", z_target)
        v_key = ("V-VELOCITY", z_target)
        if u_key not in wanted or v_key not in wanted:
            print(f"z={z_target}: missing U or V — keys present: "
                  f"{[k for k in wanted if k[1]==z_target]}")
            continue
        path_u, ijk_u = wanted[u_key]
        path_v, ijk_v = wanted[v_key]
        _, _, _, _, t_u, u = read_sf(path_u)
        _, _, _, _, t_v, v = read_sf(path_v)
        # squeeze the singleton z axis
        u2 = u[:, :, :, 0]   # (nt, nx, ny)
        v2 = v[:, :, :, 0]

        # face-grid x,y for U: x is face (nx+1 size? actually nx given i1..i2)
        # FDS slice nodes are face nodes when CELL_CENTERED=.FALSE.
        i1,i2,j1,j2,k1,k2 = ijk_u
        x_u = geom["xf"][i1:i2+1]
        y_u = geom["yf"][j1:j2+1]
        i1,i2,j1,j2,k1,k2 = ijk_v
        x_v = geom["xf"][i1:i2+1]
        y_v = geom["yf"][j1:j2+1]

        # interpolate to common grid: cell centres
        # U lives on x-faces, V on y-faces — average neighbours to centres
        nx = min(u2.shape[1]-1, v2.shape[1]-1)
        ny = min(u2.shape[2]-1, v2.shape[2]-1)
        u_c = 0.5*(u2[:, :nx, :ny] + u2[:, 1:nx+1, :ny])  # but U is on x-face only
        v_c = 0.5*(v2[:, :nx, :ny] + v2[:, :nx, 1:ny+1])
        # NOTE: simplified — for visual quiver this is fine
        xc = 0.5*(x_u[:nx] + x_u[1:nx+1])
        yc = 0.5*(y_v[:ny] + y_v[1:ny+1])

        # last available timestep ≈ t=300 s
        t_last = float(t_u[-1])
        u_inst = u_c[-1]   # (nx, ny)
        v_inst = v_c[-1]

        speed = np.sqrt(u_inst**2 + v_inst**2)
        print(f"\nz={z_target} m, t={t_last:.1f} s:")
        print(f"  U range: [{u_inst.min():+.3f}, {u_inst.max():+.3f}] m/s")
        print(f"  V range: [{v_inst.min():+.3f}, {v_inst.max():+.3f}] m/s")
        print(f"  |u| max: {speed.max():.3f}  mean: {speed.mean():.3f} m/s")

        # ---- mask velocity inside OBST cells that intersect this z-plane
        # so streamlines don't propagate through solids (e.g. main_engine).
        u_plot = u_inst.copy()
        v_plot = v_inst.copy()
        sp_plot = speed.copy()
        Xc, Yc = np.meshgrid(xc, yc, indexing="ij")
        obst_mask = np.zeros_like(u_plot, dtype=bool)
        for ob in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = ob
            if not (oz1 <= z_target <= oz2): continue
            obst_mask |= ((Xc >= ox1) & (Xc <= ox2) &
                          (Yc >= oy1) & (Yc <= oy2))
        u_plot[obst_mask] = np.nan
        v_plot[obst_mask] = np.nan
        sp_plot[obst_mask] = np.nan

        # ---- plot
        fig, ax = plt.subplots(figsize=(11, 8.5))
        X, Y = np.meshgrid(xc, yc, indexing="ij")
        cf = ax.contourf(X, Y, sp_plot, levels=20, cmap="viridis")
        plt.colorbar(cf, ax=ax, label="|u_h| (m/s)")
        # streamlines — matplotlib needs (ny, nx) shape arrays; NaN cells skipped
        ax.streamplot(xc, yc, u_plot.T, v_plot.T,
                      color="white",
                      linewidth=0.6 + 2.0*np.nan_to_num(sp_plot.T)/max(np.nanmax(sp_plot), 1e-6),
                      density=2.0, arrowsize=1.2)

        # overlay OBSTs (solid gray over masked area)
        for ob in obsts:
            ox1,ox2,oy1,oy2,oz1,oz2 = ob
            if not (oz1 <= z_target <= oz2): continue
            ax.add_patch(patches.Rectangle((ox1, oy1), ox2-ox1, oy2-oy1,
                                           lw=0.6, edgecolor="black",
                                           facecolor="lightgray", alpha=0.95))

        # overlay vents -- determine ACTUAL flow direction from the local
        # velocity field rather than the SURF_ID label (sign-flip tests can
        # invert behaviour without renaming the SURF).
        def sample_normal(x1, x2, y1, y2, normal):
            """Average velocity component normal to vent face over its cells."""
            ix_lo = int(np.searchsorted(xc, x1)); ix_hi = int(np.searchsorted(xc, x2))
            iy_lo = int(np.searchsorted(yc, y1)); iy_hi = int(np.searchsorted(yc, y2))
            ix_lo, ix_hi = max(ix_lo, 0), max(ix_hi, ix_lo+1)
            iy_lo, iy_hi = max(iy_lo, 0), max(iy_hi, iy_lo+1)
            if normal == "+y" or normal == "-y":
                val = np.nanmean(v_inst[ix_lo:ix_hi, iy_lo:iy_hi])
                return val if normal == "+y" else -val
            else:  # +x / -x
                val = np.nanmean(u_inst[ix_lo:ix_hi, iy_lo:iy_hi])
                return val if normal == "+x" else -val

        for xb, kind in vents:
            x1,x2,y1,y2,z1,z2 = xb
            if not (z1 <= z_target <= z2): continue
            # determine vent wall orientation -- which face it's on and the
            # outward (room→solid) normal direction
            if   abs(y1 - 0.2) < 1e-3:  normal = "-y"     # outer_south (room at y>0.2)
            elif abs(y1 - 2.8) < 1e-3:  normal = "+y"     # osr_north OSR side (OSR at y<2.8)
            elif abs(y1 - 3.0) < 1e-3:  normal = "-y"     # osr_north MER side (MER at y>3.0)
            elif abs(y1 - 9.8) < 1e-3:  normal = "+y"     # outer_north (MER at y<9.8)
            else:                       normal = None
            v_normal = sample_normal(x1, x2, y1, y2, normal) if normal else float("nan")
            # v_normal > 0 → gas flows OUT of room into solid (exhaust behaviour)
            # v_normal < 0 → gas flows OUT of solid into room (supply behaviour)
            if np.isnan(v_normal):
                tag, color = "?", "gray"
            elif v_normal > 0:                  # gas → wall (exhaust)
                tag, color = f"OUT {abs(v_normal):.1f}", "red"
            else:                               # gas ← wall (supply)
                tag, color = f"IN {abs(v_normal):.1f}",  "lime"
            rect = patches.Rectangle((x1, y1), x2-x1, y2-y1,
                                     linewidth=2.5, edgecolor=color,
                                     facecolor="none")
            ax.add_patch(rect)
            # arrow in actual flow direction
            cx, cy0 = (x1+x2)/2, (y1+y2)/2
            if normal in ("+y", "-y"):
                # vent is on a y-wall; arrow in y direction
                sign = -1 if (v_normal < 0 and normal == "-y") or \
                              (v_normal > 0 and normal == "+y") else 1
                # sign=+1 means arrow in +y (into +y region), but we want flow direction.
                # Compute flow vector: if IN (v_normal<0), flow goes -normal direction.
                if normal == "-y":  flow_dy = -np.sign(v_normal)  # outward normal -y, v_normal<0 → +y flow
                else:               flow_dy = +np.sign(v_normal)  # outward normal +y, v_normal<0 → -y flow … wait
                # simpler:
                #   v_normal>0 = OUT of room = into solid
                #   For outer_south (y=0.2, OUT means -y direction)
                #   For osr_north OSR side (y=2.8, OUT means +y direction)
                if normal == "-y":  flow_dy = -1 if v_normal > 0 else +1
                else:               flow_dy = +1 if v_normal > 0 else -1
                ax.annotate("", xy=(cx, cy0 + flow_dy*0.5), xytext=(cx, cy0 - flow_dy*0.5),
                            arrowprops=dict(arrowstyle="->,head_width=0.5",
                                            color=color, lw=3))
            ax.text(cx, cy0 + (0.7 if cy0 < 5 else -0.7), tag, color=color,
                    fontsize=9, ha="center", va="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                              edgecolor=color, alpha=0.9))

        ax.set_xlim(geom["xmin"], geom["xmax"])
        ax.set_ylim(geom["ymin"], geom["ymax"])
        ax.set_aspect("equal")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        ax.set_title(f"{JOB} — instantaneous (U,V) at z={z_target:.3f} m, t={t_last:.1f} s\n"
                     f"green = HVAC_INLET, red = HVAC_OUTLET")
        out_png = OUT / f"{JOB}_uv_z{z_target:.3f}.png"
        fig.tight_layout()
        fig.savefig(out_png, dpi=140)
        plt.close(fig)
        print(f"  wrote {out_png}")


if __name__ == "__main__":
    main()
