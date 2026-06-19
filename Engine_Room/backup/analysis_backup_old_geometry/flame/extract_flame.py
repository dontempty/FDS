#!/usr/bin/env python3
"""
extract_flame.py
================
Post-processor for Lan et al. 2023 (Fire Safety Journal) Figures 9, 10, 12 —
flame geometry (Lx, Ly, Lz), Heskestad-style flame height Hf, flame tilt
angles (theta_y, theta_z), and the dimensionless tilt correlation group X.

The Engine_Room input deck adds the following sensors (see DESIGN doc):
    * Slice files (binary .sf):
        - PBY = y_fire_centre, QUANTITY = HRRPUV     (x-z plane, gives Lx, Lz)
        - PBX = x_fire_centre, QUANTITY = HRRPUV     (y-z plane, gives Ly, Lz)
        - PBZ = z_max / 2,     QUANTITY = HRRPUV     (x-y plane, gives Lx, Ly)
        - PBY = y_fire_centre, QUANTITY = VELOCITY   (vector slice)
        - PBX = 0.5,           QUANTITY = U-VELOCITY (inlet ventilation v_y)
        - Pre-existing PBY/PBX/PBZ TEMPERATURE slices
    * DEVCs in CHID_devc.csv:
        - flame_xmin/xmax/ymin/ymax/zmin/zmax (HRRPUV SPATIAL_STATISTIC
          MINLOC/MAXLOC X/Y/Z, restricted to XB = flame box)
        - flame_volume (HRRPUV VOLUME, QUANTITY_RANGE=200..1e10)
        - flame_hrr_in_box (HRRPUV VOLUME INTEGRAL, QUANTITY_RANGE)
        - Hf_value (CONTROL VALUE of Hf_pctl: PERCENTILE 0.99 of stratified
          HRRPUV VOLUME INTEGRAL array)
        - vy_inlet (U-VELOCITY point at upstream inlet centerline)
        - vy_flame_box (U-VELOCITY VOLUME MEAN over flame box)
        - T_flame_box (TEMPERATURE VOLUME MEAN over flame box)
        - T_tip (THERMOCOUPLE near expected flame tip)
    * HRR columns (CHID_hrr.csv): Time, HRR, Q_CONV, Q_RADI, ...

OUTPUT CSVs (under --out-dir, default /scratch/x3319a05/fds/Engine_Room/
analysis/flame/):

  <run>_flame_timeseries.csv
      Per-timestep series for one run.  Columns:
          time_s, Lx_m, Ly_m, Lz_m, Hf_m, theta_y_deg, theta_z_deg,
          vy_flame_m_s, T_flame_C, Q_conv_kW, Q_total_kW
      Lx/Ly/Lz come from DEVC MAXLOC-MINLOC pairs when present, otherwise
      from the SLCF binary reader bounding box.  Hf from Hf_value DEVC if
      present, else from interpolating the centerline TC line at 500 C.

  fig9_data.csv
      Long format, columns: run, method, time_s, Lx_m, Ly_m, theta_y_deg
      Used to reproduce paper Fig 9 (theta_y vs ventilation velocity).

  fig10_data.csv
      Long format, columns: run, method, time_s, Hf_m, theta_z_deg
      Used to reproduce paper Fig 10 (theta_z vs ventilation velocity).

  fig12_data.csv
      One row per Method-1 run with steady-state averaged columns
          run, vy_m_s, theta_y_deg, theta_z_deg, Q_conv_kW, T_f_K,
          dT_f_K, sin_theta_y, tan_theta_z_meas, X_dimensionless,
          tan_theta_z_lan2023, residual
      Used to reproduce Fig 12 (tan(theta_z) vs X log-log scatter +
      Lan eq. 9 curve overlay).

  cases_index.txt
      Plain-text listing of result directories considered + skip reason.

Run name / method convention:
    The Fig 9/10/12 sweep uses run-dir names of the form
        method{1|2}_v{vy_inlet*100:03d}_<jobid>
    e.g.  method1_v100_756123  →  Method 1, v_y = 1.00 m/s.
    The default CLI glob is "method*_v*_*"; for the smoke-test single case
    (gen_engine_room.py --chid engine_room_flamegeom) pass --glob
    "engine_room_flamegeom_*" or use the explicit --run-dirs option.

CLI:
    python3 extract_flame.py
        [--results-dir /scratch/x3319a05/fds/Engine_Room/Results]
        [--out-dir analysis/flame]
        [--threshold-hrrpuv 200.0]   # kW/m^3, design default
        [--glob 'method*_v*_*']      # pattern under results-dir
        [--run-dirs DIR [DIR ...]]   # override --glob with an explicit list
        [--steady-frac 0.5]          # last-N fraction used for averaging
        [--no-slcf]                  # skip slice files, DEVCs only
        [--verbose]

Constants (Lan 2023 Table 3):
    rho_inf = 1.205 kg/m^3
    Cp      = 1.005 kJ/(kg.K)
    T_inf   = 293 K
    g       = 9.81 m/s^2

The script is stdlib + numpy.  Plotting is delegated to a separate script.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
import struct
import sys
from pathlib import Path
from typing import Iterable

import numpy as np


# --------------------------------------------------------------------------- #
# Constants from Lan et al. 2023 Table 3
# --------------------------------------------------------------------------- #
RHO_INF = 1.205     # kg/m^3
CP      = 1.005     # kJ/(kg.K)   (we'll convert as needed in the X-group)
T_INF   = 293.0     # K
G       = 9.81      # m/s^2

# Flame box used in gen_engine_room.py for all flame-region DEVCs.
FLAME_BOX_XB = (6.0, 11.0, 0.0, 3.0, 0.0, 3.0)

# Heskestad 99% percentile flame tip placeholder if Hf_value DEVC missing.
HF_TC_THRESHOLD_C = 500.0   # 500 C isotherm criterion

# Default flame threshold (matches DESIGN flame_threshold_kw_per_m3).
DEFAULT_THRESHOLD = 200.0   # kW/m^3

# Steady-window default (last fraction of the time axis used for averages).
DEFAULT_STEADY_FRAC = 0.5


# --------------------------------------------------------------------------- #
# CSV helpers
# --------------------------------------------------------------------------- #
def read_fds_csv(path: Path) -> tuple[list[str], list[str], np.ndarray]:
    """Read an FDS-style CSV (line 1 = units, line 2 = column names,
    line 3+ = data).  Returns (units, names, data: ndarray shape (Nt, Ncol))."""
    with open(path) as f:
        rows = list(csv.reader(f))
    if len(rows) < 3:
        raise RuntimeError(f"{path}: only {len(rows)} rows, expected ≥3")
    units = [c.strip() for c in rows[0]]
    names = [c.strip() for c in rows[1]]
    data = np.full((len(rows) - 2, len(names)), np.nan, dtype=np.float64)
    for i, r in enumerate(rows[2:]):
        for j in range(min(len(r), len(names))):
            try:
                data[i, j] = float(r[j].strip())
            except (ValueError, IndexError):
                pass
    return units, names, data


def col_by_name(names: list[str], name: str) -> int | None:
    """Case-sensitive exact match; returns column index or None."""
    try:
        return names.index(name)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# .smv parser — minimum required to map SLCF → physical coords
# --------------------------------------------------------------------------- #
class SmvIndex:
    """Parses a CHID.smv file to extract per-slice metadata and per-mesh
    coordinate axes (TRNX/TRNY/TRNZ).  We only support single-mesh runs for
    SLCF reading; with multi-mesh runs the same logic applies per mesh but
    we keep it simple here."""

    def __init__(self, smv_path: Path) -> None:
        self.path = smv_path
        # Per-mesh grids: mesh_idx (1-based) → {'x':array, 'y':array, 'z':array}
        self.meshes: dict[int, dict[str, np.ndarray]] = {}
        # SLCF records: list of dicts with keys
        #   file, quantity, label, unit, mesh, ijk (i1,i2,j1,j2,k1,k2)
        self.slices: list[dict] = []
        self._parse()

    def _parse(self) -> None:
        lines = self.path.read_text(errors="replace").splitlines()
        i = 0
        n = len(lines)
        mesh_idx = 0
        trn_axis = None
        trn_remaining = 0
        trn_buffer: list[float] = []
        while i < n:
            ln = lines[i]
            head = ln.split()
            if head and head[0] == "GRID":
                # next line: NX NY NZ ...
                mesh_idx += 1
                vals = lines[i + 1].split()
                nx, ny, nz = int(vals[0]), int(vals[1]), int(vals[2])
                self.meshes[mesh_idx] = {
                    "nx": nx, "ny": ny, "nz": nz,
                    "x": np.zeros(nx + 1), "y": np.zeros(ny + 1),
                    "z": np.zeros(nz + 1),
                }
                i += 2
                continue
            if head and head[0] in ("TRNX", "TRNY", "TRNZ"):
                trn_axis = head[0][-1].lower()
                # next line: "0" (number of skips); skip 0 lines (FDS default)
                # then (N+1) entries of "idx coord"
                axis_len = self.meshes[mesh_idx][trn_axis].size
                trn_remaining = axis_len
                trn_buffer = []
                i += 2   # skip header + the "0" line
                continue
            if trn_remaining > 0:
                parts = ln.split()
                if len(parts) >= 2:
                    try:
                        trn_buffer.append(float(parts[1]))
                        trn_remaining -= 1
                        if trn_remaining == 0:
                            arr = np.array(trn_buffer)
                            self.meshes[mesh_idx][trn_axis] = arr
                            trn_axis = None
                        i += 1
                        continue
                    except ValueError:
                        pass
            if head and head[0] in ("SLCF", "SLCC", "SLCT"):
                # SLCF <mesh> # <kind> & i1 i2 j1 j2 k1 k2 ! ...
                cell_centered = (head[0] in ("SLCC", "SLCT"))
                # Find the index range after the '&'
                try:
                    amp = ln.index("&")
                    after = ln[amp + 1:]
                    bang = after.index("!") if "!" in after else len(after)
                    nums = after[:bang].split()
                    i1, i2, j1, j2, k1, k2 = (int(x) for x in nums[:6])
                except (ValueError, IndexError):
                    i += 1
                    continue
                # mesh number is field after SLCF
                try:
                    smesh = int(head[1])
                except (IndexError, ValueError):
                    smesh = 1
                # next 4 lines: file, quantity, label, unit  (each leading space)
                fname = lines[i + 1].strip()
                quant = lines[i + 2].strip()
                label = lines[i + 3].strip()
                unit  = lines[i + 4].strip()
                self.slices.append({
                    "file": fname, "quantity": quant, "label": label,
                    "unit": unit, "mesh": smesh, "ijk": (i1, i2, j1, j2, k1, k2),
                    "cell_centered": cell_centered,
                })
                i += 5
                continue
            i += 1

    def slice_axes(self, slc: dict) -> dict[str, np.ndarray]:
        """Return the physical coord arrays (x,y,z) for the slice in its
        own bounding box, cell-centered if needed."""
        m = self.meshes[slc["mesh"]]
        i1, i2, j1, j2, k1, k2 = slc["ijk"]
        x_node = m["x"][i1:i2 + 1]
        y_node = m["y"][j1:j2 + 1]
        z_node = m["z"][k1:k2 + 1]
        if slc["cell_centered"]:
            x = 0.5 * (x_node[:-1] + x_node[1:]) if x_node.size > 1 else x_node
            y = 0.5 * (y_node[:-1] + y_node[1:]) if y_node.size > 1 else y_node
            z = 0.5 * (z_node[:-1] + z_node[1:]) if z_node.size > 1 else z_node
        else:
            x, y, z = x_node, y_node, z_node
        return {"x": x, "y": y, "z": z}


# --------------------------------------------------------------------------- #
# SLCF binary reader — Fortran sequential, 3 S30 headers + ijk + (time + data)
# --------------------------------------------------------------------------- #
def _read_record(f) -> bytes:
    """Read one Fortran-sequential record (4-byte length, payload, 4-byte
    length).  Returns the payload bytes, or b'' at EOF."""
    hdr = f.read(4)
    if len(hdr) < 4:
        return b""
    (n,) = struct.unpack("<i", hdr)
    payload = f.read(n)
    tail = f.read(4)
    if len(tail) < 4:
        return b""
    return payload


def read_slice_binary(sf_path: Path) -> tuple[np.ndarray, np.ndarray,
                                              tuple[int, int, int, int, int, int]]:
    """Read an FDS .sf file.  Returns (times, data, ijk).

        times : (Nt,) float32
        data  : (Nt, NI, NJ, NK) float32  — singleton dims preserved
        ijk   : (i1, i2, j1, j2, k1, k2) cell-index bounds from the file
    """
    with open(sf_path, "rb") as f:
        # 3 character headers (S30 each) — quantity / short label / unit
        for _ in range(3):
            _ = _read_record(f)
        # 6 int32 index bounds
        idx_bytes = _read_record(f)
        if len(idx_bytes) < 24:
            raise RuntimeError(f"{sf_path}: truncated index record")
        i1, i2, j1, j2, k1, k2 = struct.unpack("<6i", idx_bytes[:24])
        ni, nj, nk = i2 - i1 + 1, j2 - j1 + 1, k2 - k1 + 1
        nvox = ni * nj * nk

        times: list[float] = []
        frames: list[np.ndarray] = []
        while True:
            t_rec = _read_record(f)
            if not t_rec:
                break
            (t,) = struct.unpack("<f", t_rec[:4])
            d_rec = _read_record(f)
            if len(d_rec) < nvox * 4:
                break
            arr = np.frombuffer(d_rec[:nvox * 4], dtype=np.float32)
            # FDS writes Fortran order over (i, j, k)
            arr = arr.reshape((ni, nj, nk), order="F")
            times.append(t)
            frames.append(arr)
        if not frames:
            return (np.zeros(0, dtype=np.float32),
                    np.zeros((0, ni, nj, nk), dtype=np.float32),
                    (i1, i2, j1, j2, k1, k2))
        return (np.array(times, dtype=np.float32),
                np.stack(frames, axis=0),
                (i1, i2, j1, j2, k1, k2))


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def steady_window(t: np.ndarray, steady_frac: float) -> np.ndarray:
    """Boolean mask selecting the last `steady_frac` of the time series."""
    if t.size == 0:
        return np.zeros(0, dtype=bool)
    t0 = t[-1] - steady_frac * (t[-1] - t[0])
    return t >= t0


def angle_deg(opposite: float, adjacent: float) -> float:
    """atan2 in degrees; NaN-safe."""
    if not (np.isfinite(opposite) and np.isfinite(adjacent)):
        return float("nan")
    return math.degrees(math.atan2(opposite, adjacent))


def bbox_from_mask(mask: np.ndarray, axis_coords: dict[str, np.ndarray]) \
        -> dict[str, tuple[float, float]]:
    """Given a 3-D bool mask of shape (NI, NJ, NK) over coords x,y,z, return
    {axis: (min, max)} of the True-cells; NaNs if no True cell."""
    if not mask.any():
        return {a: (float("nan"), float("nan")) for a in "xyz"}
    out: dict[str, tuple[float, float]] = {}
    for ax, idx in zip("xyz", (0, 1, 2)):
        coord = axis_coords[ax]
        if coord.size == 0:
            out[ax] = (float("nan"), float("nan"))
            continue
        # Marginal: collapse the other axes
        collapse_axes = tuple(i for i in (0, 1, 2) if i != idx)
        marg = mask.any(axis=collapse_axes)
        # Align coord length with marg length (cell-centered coords)
        n = min(coord.size, marg.size)
        marg = marg[:n]
        coord = coord[:n]
        where = np.where(marg)[0]
        if where.size == 0:
            out[ax] = (float("nan"), float("nan"))
        else:
            out[ax] = (float(coord[where[0]]), float(coord[where[-1]]))
    return out


def interp_height_at_threshold(z: np.ndarray, T_K: np.ndarray,
                               thresh_K: float) -> float:
    """Return the highest z where T crosses `thresh_K` going downward (i.e.
    the flame-top height).  NaN if T never reaches thresh."""
    if z.size == 0 or T_K.size == 0 or z.size != T_K.size:
        return float("nan")
    above = T_K >= thresh_K
    if not above.any():
        return float("nan")
    top_idx = int(np.where(above)[0][-1])
    if top_idx == z.size - 1:
        return float(z[top_idx])
    z0, z1 = z[top_idx], z[top_idx + 1]
    T0, T1 = T_K[top_idx], T_K[top_idx + 1]
    if T1 == T0:
        return float(z0)
    frac = (thresh_K - T0) / (T1 - T0)
    return float(z0 + frac * (z1 - z0))


# --------------------------------------------------------------------------- #
# Per-run extraction
# --------------------------------------------------------------------------- #
def find_chid(run_dir: Path) -> str | None:
    """Return CHID by locating CHID.smv inside run_dir."""
    smv = list(run_dir.glob("*.smv"))
    if not smv:
        return None
    return smv[0].stem


def run_is_finished(hrr_csv: Path, expected_t_end: float | None) -> bool:
    """Heuristic completeness check.  If expected_t_end is None, only
    require that the file has ≥2 data rows."""
    try:
        _, _, data = read_fds_csv(hrr_csv)
    except Exception:
        return False
    if data.shape[0] < 2:
        return False
    if expected_t_end is not None and data[-1, 0] < 0.9 * expected_t_end:
        return False
    return True


def parse_method(run_name: str) -> str:
    """Extract 'method1'/'method2'/etc. from a run-dir name; 'unknown' if
    pattern absent."""
    m = re.match(r"(method\d+)_v(\d+)_", run_name)
    if not m:
        return "unknown"
    return m.group(1)


def parse_vy_from_name(run_name: str) -> float:
    """Pattern method{N}_v{vy*100}_ → vy in m/s; NaN if absent."""
    m = re.match(r"method\d+_v(\d+)_", run_name)
    if not m:
        return float("nan")
    return int(m.group(1)) / 100.0


def extract_devc_geometry(t_devc: np.ndarray, names: list[str],
                          data: np.ndarray) -> dict[str, np.ndarray]:
    """Return per-timestep arrays for Lx, Ly, Lz, Hf, V, HRR_in, vy_box,
    vy_inlet, T_box, T_tip — NaN where the column is missing."""
    cols = {
        "flame_xmin": None, "flame_xmax": None,
        "flame_ymin": None, "flame_ymax": None,
        "flame_zmin": None, "flame_zmax": None,
        "flame_volume": None, "flame_hrr_in_box": None,
        "Hf_value": None,
        "vy_inlet": None, "vy_flame_box": None,
        "T_flame_box": None, "T_tip": None,
    }
    for k in list(cols):
        j = col_by_name(names, k)
        if j is not None:
            cols[k] = data[:, j]

    def col_or_nan(key: str) -> np.ndarray:
        v = cols[key]
        return v if v is not None else np.full(t_devc.size, np.nan)

    def diff_or_nan(a: str, b: str) -> np.ndarray:
        va, vb = cols[a], cols[b]
        if va is None or vb is None:
            return np.full(t_devc.size, np.nan)
        return va - vb

    return {
        "Lx": diff_or_nan("flame_xmax", "flame_xmin"),
        "Ly": diff_or_nan("flame_ymax", "flame_ymin"),
        "Lz": diff_or_nan("flame_zmax", "flame_zmin"),
        "Hf": col_or_nan("Hf_value"),
        "V_flame": col_or_nan("flame_volume"),
        "HRR_in_box": col_or_nan("flame_hrr_in_box"),
        "vy_inlet": col_or_nan("vy_inlet"),
        "vy_flame_box": col_or_nan("vy_flame_box"),
        "T_flame_box": col_or_nan("T_flame_box"),
        "T_tip": col_or_nan("T_tip"),
    }


def extract_slcf_geometry(run_dir: Path, chid: str, threshold: float,
                          verbose: bool) -> dict | None:
    """Use SLCF binary reader to compute (Lx, Ly, Lz, theta_y, theta_z)
    time-series from the HRRPUV slices.  Returns dict of arrays or None
    if no usable slice found."""
    smv_path = run_dir / f"{chid}.smv"
    if not smv_path.exists():
        if verbose:
            print(f"  [slcf] no {smv_path.name} → skip slice reader")
        return None
    try:
        smv = SmvIndex(smv_path)
    except Exception as e:
        print(f"  [slcf] {smv_path.name}: parse failed → {e}")
        return None

    # Collect HRRPUV slices in three orthogonal orientations.
    pby_slc, pbx_slc, pbz_slc = None, None, None
    for s in smv.slices:
        q = s["quantity"].upper().strip()
        if q != "HRRPUV":
            continue
        i1, i2, j1, j2, k1, k2 = s["ijk"]
        ni, nj, nk = i2 - i1 + 1, j2 - j1 + 1, k2 - k1 + 1
        # Orientation: which index range is singleton
        if nj == 1 and ni > 1 and nk > 1 and pby_slc is None:
            pby_slc = s
        elif ni == 1 and nj > 1 and nk > 1 and pbx_slc is None:
            pbx_slc = s
        elif nk == 1 and ni > 1 and nj > 1 and pbz_slc is None:
            pbz_slc = s

    if pby_slc is None and pbx_slc is None and pbz_slc is None:
        if verbose:
            print("  [slcf] no HRRPUV slice found in .smv")
        return None

    # Read each slice; build per-timestep envelope.
    times_ref: np.ndarray | None = None
    x_extent = (None, None)   # (min(t), max(t))
    y_extent = (None, None)
    z_extent = (None, None)

    def union_extent(prev: tuple, new: tuple) -> tuple:
        a_lo, a_hi = prev
        b_lo, b_hi = new
        lo = b_lo if a_lo is None else np.fmin(a_lo, b_lo)
        hi = b_hi if a_hi is None else np.fmax(a_hi, b_hi)
        return lo, hi

    for slc in (pby_slc, pbx_slc, pbz_slc):
        if slc is None:
            continue
        sf_path = run_dir / slc["file"]
        if not sf_path.exists():
            if verbose:
                print(f"  [slcf] missing {sf_path.name}")
            continue
        try:
            times, data, _ = read_slice_binary(sf_path)
        except Exception as e:
            print(f"  [slcf] read {sf_path.name} failed: {e}")
            continue
        if times.size == 0:
            continue
        axes = smv.slice_axes(slc)
        # Squeeze singleton dim but keep 3 coords for bbox helper.
        # data is (Nt, NI, NJ, NK).
        nt, ni, nj, nk = data.shape
        if times_ref is None:
            times_ref = times.astype(np.float64)
        # Align other slices to ref by simple length match; tolerate ±1.
        n = min(times_ref.size, times.size)
        masks = data[:n] >= threshold      # (n, ni, nj, nk)
        # Compute per-time bbox along each axis present in the slice.
        x_min = np.full(n, np.nan); x_max = np.full(n, np.nan)
        y_min = np.full(n, np.nan); y_max = np.full(n, np.nan)
        z_min = np.full(n, np.nan); z_max = np.full(n, np.nan)
        xc, yc, zc = axes["x"], axes["y"], axes["z"]
        for it in range(n):
            m3 = masks[it]
            if not m3.any():
                continue
            if ni > 1 and xc.size >= ni:
                marg = m3.any(axis=(1, 2))[:xc.size]
                w = np.where(marg)[0]
                if w.size:
                    x_min[it] = xc[w[0]]; x_max[it] = xc[w[-1]]
            if nj > 1 and yc.size >= nj:
                marg = m3.any(axis=(0, 2))[:yc.size]
                w = np.where(marg)[0]
                if w.size:
                    y_min[it] = yc[w[0]]; y_max[it] = yc[w[-1]]
            if nk > 1 and zc.size >= nk:
                marg = m3.any(axis=(0, 1))[:zc.size]
                w = np.where(marg)[0]
                if w.size:
                    z_min[it] = zc[w[0]]; z_max[it] = zc[w[-1]]
        if ni > 1:
            x_extent = union_extent(
                (x_extent[0][:n] if x_extent[0] is not None else None,
                 x_extent[1][:n] if x_extent[1] is not None else None),
                (x_min, x_max),
            )
        if nj > 1:
            y_extent = union_extent(
                (y_extent[0][:n] if y_extent[0] is not None else None,
                 y_extent[1][:n] if y_extent[1] is not None else None),
                (y_min, y_max),
            )
        if nk > 1:
            z_extent = union_extent(
                (z_extent[0][:n] if z_extent[0] is not None else None,
                 z_extent[1][:n] if z_extent[1] is not None else None),
                (z_min, z_max),
            )
        # Truncate times_ref to n if needed
        if times_ref.size > n:
            times_ref = times_ref[:n]

    if times_ref is None:
        return None

    def safe_diff(extent: tuple) -> np.ndarray:
        lo, hi = extent
        if lo is None or hi is None:
            return np.full(times_ref.size, np.nan)
        n = min(lo.size, hi.size, times_ref.size)
        return hi[:n] - lo[:n]

    Lx_s = safe_diff(x_extent)
    Ly_s = safe_diff(y_extent)
    Lz_s = safe_diff(z_extent)
    return {
        "time": times_ref,
        "Lx_slc": Lx_s,
        "Ly_slc": Ly_s,
        "Lz_slc": Lz_s,
    }


def extract_run(run_dir: Path, threshold: float, steady_frac: float,
                use_slcf: bool, verbose: bool) -> dict | None:
    """Extract everything needed for the figs from a single run dir.
    Returns a dict (or None to skip)."""
    chid = find_chid(run_dir)
    if chid is None:
        if verbose:
            print(f"{run_dir.name}: no .smv → skip")
        return None
    hrr_path  = run_dir / f"{chid}_hrr.csv"
    devc_path = run_dir / f"{chid}_devc.csv"
    line_path = run_dir / f"{chid}_line.csv"

    if not hrr_path.exists():
        if verbose:
            print(f"{run_dir.name}: no _hrr.csv → skip")
        return None
    if not run_is_finished(hrr_path, expected_t_end=None):
        if verbose:
            print(f"{run_dir.name}: _hrr.csv too short → skip")
        return None

    # HRR series
    _, hrr_names, hrr_data = read_fds_csv(hrr_path)
    t_hrr = hrr_data[:, 0]
    j_hrr = col_by_name(hrr_names, "HRR")
    j_qc  = col_by_name(hrr_names, "Q_CONV")
    Q_tot = hrr_data[:, j_hrr] if j_hrr is not None else np.full(t_hrr.size, np.nan)
    Q_c   = hrr_data[:, j_qc]  if j_qc  is not None else np.full(t_hrr.size, np.nan)

    # DEVC series
    devc_geom: dict[str, np.ndarray] = {}
    t_devc = np.array([], dtype=np.float64)
    if devc_path.exists():
        _, devc_names, devc_data = read_fds_csv(devc_path)
        t_devc = devc_data[:, 0]
        devc_geom = extract_devc_geometry(t_devc, devc_names, devc_data)
    else:
        if verbose:
            print(f"{run_dir.name}: no _devc.csv → using NaN DEVC columns")
        # build empty per-key arrays sized to HRR time grid
        for k in ("Lx", "Ly", "Lz", "Hf", "V_flame", "HRR_in_box",
                  "vy_inlet", "vy_flame_box", "T_flame_box", "T_tip"):
            devc_geom[k] = np.full(t_hrr.size, np.nan)
        t_devc = t_hrr

    # SLCF series (fallback for L's if DEVC missing, sanity check otherwise)
    slcf = None
    if use_slcf:
        try:
            slcf = extract_slcf_geometry(run_dir, chid, threshold, verbose)
        except Exception as e:
            print(f"{run_dir.name}: SLCF extraction errored: {e}")
            slcf = None
    else:
        if verbose:
            print(f"{run_dir.name}: --no-slcf, skipping slice reader")

    # Time base: align everything to the DEVC time grid (highest cadence).
    t_master = t_devc if t_devc.size > 0 else t_hrr

    # Interpolate HRR onto t_master.
    def interp_to(t_src: np.ndarray, y_src: np.ndarray) -> np.ndarray:
        if t_src.size == 0 or y_src.size == 0:
            return np.full(t_master.size, np.nan)
        mask = np.isfinite(y_src)
        if mask.sum() < 2:
            return np.full(t_master.size, np.nan)
        return np.interp(t_master, t_src[mask], y_src[mask],
                         left=np.nan, right=np.nan)

    Q_tot_m = interp_to(t_hrr, Q_tot)
    Q_c_m   = interp_to(t_hrr, Q_c)

    Lx = devc_geom["Lx"]
    Ly = devc_geom["Ly"]
    Lz = devc_geom["Lz"]
    Hf = devc_geom["Hf"]
    vy_box = devc_geom["vy_flame_box"]
    vy_inl = devc_geom["vy_inlet"]
    T_box  = devc_geom["T_flame_box"]
    T_tip  = devc_geom["T_tip"]

    # Fallback Lx/Ly/Lz from SLCF if DEVC NaN.
    if slcf is not None:
        Lx_s = interp_to(slcf["time"], slcf["Lx_slc"])
        Ly_s = interp_to(slcf["time"], slcf["Ly_slc"])
        Lz_s = interp_to(slcf["time"], slcf["Lz_slc"])
        Lx = np.where(np.isfinite(Lx), Lx, Lx_s)
        Ly = np.where(np.isfinite(Ly), Ly, Ly_s)
        Lz = np.where(np.isfinite(Lz), Lz, Lz_s)

    # Fallback Hf from centerline thermocouple line at 500 C.
    Hf_500C = float("nan")
    if (line_path.exists()
            and not np.isfinite(np.nanmean(Hf))):
        try:
            _, lnames, ldata = read_fds_csv(line_path)
            # heuristic: any thermocouple-like column with z in label
            zs: list[float] = []
            Ts: list[float] = []
            for j, nm in enumerate(lnames):
                m = re.search(r"thermocouple_z(\d+)p(\d+)", nm)
                if not m:
                    continue
                z = float(f"{m.group(1)}.{m.group(2)}")
                # Steady-window time-mean
                t_l = ldata[:, 0]
                mask = steady_window(t_l, steady_frac)
                if mask.sum() < 2:
                    continue
                Tm = np.nanmean(ldata[mask, j])
                zs.append(z); Ts.append(Tm + 273.15)
            if zs:
                z_arr = np.array(zs)
                T_arr = np.array(Ts)
                order = np.argsort(z_arr)
                Hf_500C = interp_height_at_threshold(
                    z_arr[order], T_arr[order],
                    HF_TC_THRESHOLD_C + 273.15)
        except Exception as e:
            if verbose:
                print(f"{run_dir.name}: Hf-from-line fallback failed: {e}")

    Hf = np.where(np.isfinite(Hf), Hf, Hf_500C)

    # Per-timestep theta_y, theta_z (degrees).
    # theta_y: tilt about y-axis (cross-wind), arctan(Ly/Lx)
    # theta_z: tilt from vertical, arctan(sqrt(Lx^2+Ly^2)/Lz)
    # NOTE: paper convention identifies theta_y with downstream centroid
    # offset; bbox-based geometric proxy is acceptable here.
    theta_y = np.array([angle_deg(ly, lx) for lx, ly in zip(Lx, Ly)])
    horiz = np.sqrt(np.where(np.isfinite(Lx), Lx, 0.0) ** 2
                    + np.where(np.isfinite(Ly), Ly, 0.0) ** 2)
    horiz = np.where(np.isfinite(Lx) | np.isfinite(Ly), horiz, np.nan)
    theta_z = np.array([angle_deg(h, lz) for h, lz in zip(horiz, Lz)])

    method = parse_method(run_dir.name)
    vy_name = parse_vy_from_name(run_dir.name)
    return {
        "run": run_dir.name,
        "chid": chid,
        "method": method,
        "vy_from_name": vy_name,
        "t": t_master,
        "Lx": Lx, "Ly": Ly, "Lz": Lz, "Hf": Hf,
        "theta_y": theta_y, "theta_z": theta_z,
        "vy_inlet": vy_inl, "vy_flame_box": vy_box,
        "T_flame_box": T_box, "T_tip": T_tip,
        "Q_tot": Q_tot_m, "Q_conv": Q_c_m,
        "Hf_500C_steady": Hf_500C,
    }


# --------------------------------------------------------------------------- #
# Aggregation / output
# --------------------------------------------------------------------------- #
def write_timeseries_csv(out_dir: Path, run: dict) -> Path:
    """One CSV per run: time, Lx, Ly, Lz, Hf, theta_y, theta_z, vy_flame,
    T_flame, Q_conv, Q_total."""
    path = out_dir / f"{run['run']}_flame_timeseries.csv"
    n = run["t"].size
    header = ("time_s,Lx_m,Ly_m,Lz_m,Hf_m,theta_y_deg,theta_z_deg,"
              "vy_flame_m_s,T_flame_C,Q_conv_kW,Q_total_kW")
    with open(path, "w") as f:
        f.write(header + "\n")
        for i in range(n):
            row = [
                f"{run['t'][i]:.4f}",
                f"{run['Lx'][i]:.4f}",
                f"{run['Ly'][i]:.4f}",
                f"{run['Lz'][i]:.4f}",
                f"{run['Hf'][i]:.4f}",
                f"{run['theta_y'][i]:.4f}",
                f"{run['theta_z'][i]:.4f}",
                f"{run['vy_flame_box'][i]:.4f}",
                f"{run['T_flame_box'][i]:.4f}",
                f"{run['Q_conv'][i]:.4f}",
                f"{run['Q_tot'][i]:.4f}",
            ]
            f.write(",".join(row) + "\n")
    return path


def write_fig9_data(out_dir: Path, runs: list[dict]) -> Path:
    """Long format: run, method, time_s, Lx_m, Ly_m, theta_y_deg."""
    path = out_dir / "fig9_data.csv"
    with open(path, "w") as f:
        f.write("run,method,time_s,Lx_m,Ly_m,theta_y_deg\n")
        for r in runs:
            n = r["t"].size
            for i in range(n):
                f.write(f"{r['run']},{r['method']},"
                        f"{r['t'][i]:.4f},{r['Lx'][i]:.4f},"
                        f"{r['Ly'][i]:.4f},{r['theta_y'][i]:.4f}\n")
    return path


def write_fig10_data(out_dir: Path, runs: list[dict]) -> Path:
    """Long format: run, method, time_s, Hf_m, theta_z_deg."""
    path = out_dir / "fig10_data.csv"
    with open(path, "w") as f:
        f.write("run,method,time_s,Hf_m,theta_z_deg\n")
        for r in runs:
            n = r["t"].size
            for i in range(n):
                f.write(f"{r['run']},{r['method']},"
                        f"{r['t'][i]:.4f},{r['Hf'][i]:.4f},"
                        f"{r['theta_z'][i]:.4f}\n")
    return path


def nanmean_in_window(t: np.ndarray, y: np.ndarray,
                      steady_frac: float) -> float:
    mask = steady_window(t, steady_frac) & np.isfinite(y)
    if mask.sum() == 0:
        return float("nan")
    return float(np.nanmean(y[mask]))


def write_fig12_data(out_dir: Path, runs: list[dict],
                     steady_frac: float) -> Path:
    """Per-run scatter row for Fig 12 (Method 1 only).  Constants per
    paper Table 3.  X = (v_y / sin(theta_y))^5 * rho_inf * Cp /
    (Q_conv * dT_f) * (T_inf / g)^2 — dimensionless when Cp in kJ/(kg·K)
    and Q_conv in kW, both divided yield K^-1 consistent with the paper's
    eq. 9 group.  We clamp sin(theta_y) ≥ 0.05 to avoid blow-up at theta_y
    ≈ 0 (centered-burner case)."""
    path = out_dir / "fig12_data.csv"
    cols = ["run", "vy_m_s", "theta_y_deg", "theta_z_deg",
            "Q_conv_kW", "T_f_K", "dT_f_K", "sin_theta_y",
            "tan_theta_z_meas", "X_dimensionless",
            "tan_theta_z_lan2023", "residual"]
    with open(path, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in runs:
            if r["method"] != "method1":
                continue
            t = r["t"]
            vy = nanmean_in_window(t, r["vy_inlet"], steady_frac)
            if not np.isfinite(vy):
                vy = r["vy_from_name"]
            th_y = nanmean_in_window(t, r["theta_y"], steady_frac)
            th_z = nanmean_in_window(t, r["theta_z"], steady_frac)
            Qc   = nanmean_in_window(t, r["Q_conv"], steady_frac)
            T_tc = nanmean_in_window(t, r["T_tip"], steady_frac)
            T_f_K = T_tc + 273.15 if np.isfinite(T_tc) else float("nan")
            dT   = T_f_K - T_INF if np.isfinite(T_f_K) else float("nan")
            sin_y = math.sin(math.radians(th_y)) if np.isfinite(th_y) \
                else float("nan")
            sin_y_clamped = max(abs(sin_y), 0.05) if np.isfinite(sin_y) \
                else float("nan")
            tan_z_meas = math.tan(math.radians(th_z)) \
                if np.isfinite(th_z) else float("nan")
            # X-group — see docstring above for derivation
            try:
                X = ((vy / sin_y_clamped) ** 5
                     * RHO_INF * CP
                     / (Qc * dT)
                     * (T_INF / G) ** 2)
            except (TypeError, ZeroDivisionError):
                X = float("nan")
            if not np.isfinite(X) or X <= 0:
                tan_z_lan = float("nan")
            else:
                tan_z_lan = -0.00895 * X ** 0.2 + 0.13365
            resid = (tan_z_meas - tan_z_lan) \
                if (np.isfinite(tan_z_meas) and np.isfinite(tan_z_lan)) \
                else float("nan")
            f.write(f"{r['run']},{vy:.4f},{th_y:.4f},{th_z:.4f},"
                    f"{Qc:.4f},{T_f_K:.4f},{dT:.4f},{sin_y:.4f},"
                    f"{tan_z_meas:.6f},{X:.6e},{tan_z_lan:.6f},"
                    f"{resid:.6f}\n")
    return path


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def discover_runs(results_dir: Path, glob_pat: str,
                  explicit: list[Path] | None) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    return sorted([d for d in results_dir.glob(glob_pat) if d.is_dir()])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract Lan et al. 2023 Fig 9/10/12 flame-geometry "
                    "data from FDS Engine_Room results.")
    ap.add_argument("--results-dir", type=Path,
                    default=Path("/scratch/x3319a05/fds/Engine_Room/Results"),
                    help="Root containing per-run sub-directories.")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("analysis/flame"),
                    help="Output directory for CSVs (created if missing).")
    ap.add_argument("--threshold-hrrpuv", type=float,
                    default=DEFAULT_THRESHOLD,
                    help=f"HRRPUV cutoff (kW/m^3) for flame envelope "
                         f"(default {DEFAULT_THRESHOLD}).")
    ap.add_argument("--glob", default="method*_v*_*",
                    help="Glob under --results-dir for run dirs "
                         "(default 'method*_v*_*').")
    ap.add_argument("--run-dirs", nargs="*", default=None,
                    help="Explicit run-dir paths (overrides --glob).")
    ap.add_argument("--steady-frac", type=float,
                    default=DEFAULT_STEADY_FRAC,
                    help="Fraction of the run used as the steady window "
                         f"(default {DEFAULT_STEADY_FRAC}).")
    ap.add_argument("--no-slcf", action="store_true",
                    help="Skip binary SLCF reader; rely on DEVCs only.")
    ap.add_argument("--verbose", action="store_true",
                    help="Print per-case progress and reasons for skips.")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = discover_runs(args.results_dir, args.glob, args.run_dirs)
    if not run_dirs:
        print(f"ERROR: no run dirs matched glob={args.glob!r} under "
              f"{args.results_dir}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Discovered {len(run_dirs)} candidate run dir(s).")

    runs: list[dict] = []
    cases_log: list[str] = []
    for d in run_dirs:
        try:
            res = extract_run(d, args.threshold_hrrpuv,
                              args.steady_frac,
                              use_slcf=not args.no_slcf,
                              verbose=args.verbose)
        except Exception as e:
            print(f"{d.name}: extraction FAILED: {e}", file=sys.stderr)
            cases_log.append(f"{d.name}: FAILED ({e})")
            continue
        if res is None:
            cases_log.append(f"{d.name}: skipped (no data)")
            continue
        out_path = write_timeseries_csv(args.out_dir, res)
        if args.verbose:
            print(f"{d.name}: wrote {out_path.name}")
        runs.append(res)
        cases_log.append(f"{d.name}: kept "
                         f"(method={res['method']}, vy_name={res['vy_from_name']})")

    if not runs:
        print("ERROR: no usable runs after extraction.", file=sys.stderr)
        (args.out_dir / "cases_index.txt").write_text(
            "\n".join(cases_log) + "\n")
        return 1

    f9  = write_fig9_data(args.out_dir, runs)
    f10 = write_fig10_data(args.out_dir, runs)
    f12 = write_fig12_data(args.out_dir, runs, args.steady_frac)
    print(f"wrote {f9}")
    print(f"wrote {f10}")
    print(f"wrote {f12}")

    (args.out_dir / "cases_index.txt").write_text(
        "Lan et al. 2023 Fig 9/10/12 — extracted cases\n"
        f"results_dir = {args.results_dir}\n"
        f"glob        = {args.glob}\n"
        f"threshold_hrrpuv = {args.threshold_hrrpuv} kW/m^3\n"
        f"steady_frac = {args.steady_frac}\n\n"
        + "\n".join(cases_log) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
