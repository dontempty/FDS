# analysis/flame — Lan et al. 2023 Flame Geometry Reproduction

This directory holds the post-processing and plotting pipeline that reproduces
Figures 9, 10, and 12 of Lan et al. 2023 from the Engine_Room FDS cases:

- **Fig 9**: flame tilt angle `theta_y` vs ventilation velocity
- **Fig 10**: flame tilt angle `theta_z` vs ventilation velocity
- **Fig 12**: `tan(theta_z)` vs the dimensionless `X`-group (Lan eq 9), log-log

## Data flow

```
   gen_engine_room.py
          |
          | emits .fds with new SLCF + DEVC
          v
   inputs/engine_room_*.fds
          |
          | sbatch run_engine_room.sbatch
          v
   FDS run  ->  Results/<case>/CHID_devc.csv
                Results/<case>/CHID_hrr.csv
                Results/<case>/CHID_line.csv
                Results/<case>/CHID_*.sf   (HRRPUV / VELOCITY slices)
          |
          | extract.py  (fdsreader 1.11.7 primary,
          |              scipy.io.FortranFile fallback,
          |              numpy.genfromtxt CSV fallback)
          v
   analysis/flame_geom/flame_extent.csv
   analysis/flame_geom/flame_extent_sensitivity.csv
   analysis/flame_geom/tilt_correlation.csv
   analysis/flame_geom/centerline_TC.csv
          |
          | plot_fig9_10_12.py  (matplotlib)
          v
   analysis/flame_geom/figs/fig09_theta_y.png
   analysis/flame_geom/figs/fig10_theta_z.png
   analysis/flame_geom/figs/fig12_correlation.png
   analysis/flame_geom/summary.txt
```

## Design summary

### SLCF planes (added to `gen_engine_room.py`)

| Axis | Value | Quantity     | Purpose                                              |
|------|-------|--------------|------------------------------------------------------|
| PBY  | 1.5   | HRRPUV       | Fire-centerline x-z; Lx, Lz, theta_z centroid        |
| PBX  | 8.5   | HRRPUV       | Fire-centerline y-z; Ly, Lz cross-flow check         |
| PBZ  | 1.5   | HRRPUV       | Horizontal at z_max/2; flame-tip (x_c, y_c)          |
| PBY  | 1.5   | VELOCITY     | Vector (U,V,W) for in-flame v_y                      |
| PBX  | 0.5   | U-VELOCITY   | Upstream-inlet bulk ventilation v_y                  |
| PBY  | 1.5   | TEMPERATURE  | Existing; drop `VECTOR=.TRUE.` (now on VELOCITY)     |

### Key DEVCs (XB flame-box = `6.0,11.0,0.0,3.0,0.0,3.0`)

- **`flame_xmin`/`xmax`, `ymin`/`ymax`, `zmin`/`zmax`**: HRRPUV `MINLOC/MAXLOC X|Y|Z`
  over the flame box (per `dump.f90:6793-6807`). Lx = xmax-xmin, etc.
- **`flame_volume`**: HRRPUV `VOLUME` + `QUANTITY_RANGE=200,1e10` (kW/m^3).
- **`flame_hrr_in_box`**: HRRPUV `VOLUME INTEGRAL` + `QUANTITY_RANGE=200,1e10`.
- **`Hf_int` + `Hf_pctl` CTRL + `Hf_value`**: 30-slab `POINTS` array above the
  burner footprint, `FUNCTION_TYPE='PERCENTILE'`, `PERCENTILE=0.99` ->
  Heskestad 99 %-HRR flame height (User Guide:8620-8626).
- **`vy_inlet`**: U-VELOCITY at `XYZ=0.5,1.5,1.0` (below smoke layer).
- **`vy_flame_box`**: U-VELOCITY `VOLUME MEAN` over flame box (no
  `QUANTITY_RANGE` — MEAN does not support it; report as sensitivity).
- **`T_flame_box`**: TEMPERATURE `VOLUME MEAN` over flame box.
- **`T_tip`**: THERMOCOUPLE at `XYZ=8.5,1.5,1.5` ~ expected H_f.

Temporal averaging is done in Python so `t_steady` can be picked post hoc.

### Parser strategy

1. **Primary**: `fdsreader` 1.11.7 under Python 3.14.2.
   Required shell prelude in every sbatch/wrapper:
   ```
   export LD_LIBRARY_PATH=/apps/applications/PYTHON/3.14.2/lib:$LD_LIBRARY_PATH
   ```
   Use `sim = fdsreader.Simulation(case_dir)`, filter `sim.slices` by
   `slc.quantity.short_name in {HRRPUV, VELOCITY, U-VELOCITY, TEMPERATURE}`,
   handle tuple return of `slc.to_global()` for cell-centered slices, read
   `sim.hrr['Q_CONV']` and `sim.devices`.
2. **Fallback 1**: ~120-line `scipy.io.FortranFile` reader for `.sf` files
   (3 x S30 headers, int32x6 index, then float32 time + NX*NY*NZ Fortran-order
   data). Map quantity to `.sf` via `CHID.smv` SLCF/SLCC blocks.
3. **Fallback 2**: `numpy.genfromtxt(skip_header=2, delimiter=',')` for
   `*_hrr.csv`, `*_devc.csv`, `*_line.csv` (existing pattern in `extract.py`).

**Do not** use `fds2ascii` in the pipeline — it time-averages between TBEG/TEND
and drops the per-frame time axis needed for steady-state windowing.

### HRRPUV flame threshold

- **Primary**: `200 kW/m^3` (Smokeview convention `20/dx` with `dx = 0.10 m`).
- **Sensitivity sweep**: `{100, 200, 400} kW/m^3` plus the 500 C isotherm,
  written to `flame_extent_sensitivity.csv`.

## CLI examples

Regenerate an input with the flame-geom DEVC/SLCF additions:

```
python3 gen_engine_room.py --chid engine_room_flamegeom \
    > inputs/engine_room_flamegeom.fds
grep -E 'HRRPUV|MAXLOC|PERCENTILE|Hf_int' inputs/engine_room_flamegeom.fds
```

Run the extractor (must export `LD_LIBRARY_PATH` for `fdsreader`):

```
LD_LIBRARY_PATH=/apps/applications/PYTHON/3.14.2/lib:$LD_LIBRARY_PATH \
    /apps/applications/PYTHON/3.14.2/bin/python3.14 \
    analysis/flame_geom/extract.py
```

Sweep ventilation velocity (Step 12):

```
for v in 0.5 1.0 1.5 2.0 2.5 3.0; do
    python3 gen_engine_room.py --chid engine_room_vy${v} --vent_vy ${v} \
        > inputs/engine_room_vy${v}.fds
done
bash submit_flame_geom.sh
```

Plot Fig 9/10/12 after CSVs exist:

```
python3 analysis/flame_geom/plot_fig9_10_12.py
ls analysis/flame_geom/figs/
```

## Known limitations / TODO

- **matplotlib not yet installed** on the cluster Python 3.14.2 module.
  `extract.py` must fall back to writing CSVs only; plots can be generated
  offline from `tilt_correlation.csv` / `flame_extent.csv`.
- **Method 2 / Method 3 sweep runs not yet submitted.** Only the Step-5
  smoke-test single case has been run. The full 6-point `v_y` sweep
  (`{0.5, 1.0, 1.5, 2.0, 2.5, 3.0}` m/s) needs `submit_flame_geom.sh`.
- **`H_f` location of `T_tip` is provisional** (z = 1.5 m = z_max/2). If
  Phase 1 shows `H_f` deviates by >30 %, regenerate with `T_tip` `XYZ` set
  to the measured `H_f` and re-run.
- **`vy_flame_box` is not a true conditional in-flame mean** — `VOLUME MEAN`
  does not accept `QUANTITY_RANGE`. Reported only as a sensitivity to
  `vy_inlet`.
- **`sin(theta_y)` is clamped to `>= 0.05`** in the `X`-group to prevent
  blow-up for the centered cross-flow case where `theta_y ~ 0`.
- **FDS 6.10 GEOM bug** may force the scipy fallback if `fdsreader` chokes
  on cut cells; the path is implemented but not exercised yet.
