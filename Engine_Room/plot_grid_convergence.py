"""
Grid convergence plot: M1 (84k) vs M3 (390k) vs M5 (674k)
Reads fire run DEVC CSV from each mesh and plots:
  Fig 1 - Vertical temperature profile (z vs time-avg T) at fire centerline
  Fig 2 - HRR time series
  Fig 3 - Time series at selected z heights
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
BASE   = Path("/scratch/x3319a05/fds/Engine_Room/Results")
MESHES = {
    "M1 (84 k)"  : BASE / "coldflow_M1" / "coldflow_M1_devc.csv",
    "M3 (390 k)" : BASE / "coldflow_M3" / "coldflow_M3_devc.csv",
    "M5 (674 k)" : BASE / "coldflow_M5" / "coldflow_M5_devc.csv",
}
COLORS = {"M1 (84 k)": "#e74c3c", "M3 (390 k)": "#2980b9", "M5 (674 k)": "#27ae60"}
HRR_FILES = {
    "M1 (84 k)"  : BASE / "coldflow_M1" / "coldflow_M1_hrr.csv",
    "M3 (390 k)" : BASE / "coldflow_M3" / "coldflow_M3_hrr.csv",
    "M5 (674 k)" : BASE / "coldflow_M5" / "coldflow_M5_hrr.csv",
}

# z heights of centerline thermocouples (m)
Z_HEIGHTS = [0.05, 0.38, 0.71, 1.03, 1.36, 1.69, 2.02, 2.34, 2.67, 3.00]
Z_LABELS  = ["z0p05","z0p38","z0p71","z1p03","z1p36","z1p69","z2p02","z2p34","z2p67","z3p00"]

# ── load DEVC ──────────────────────────────────────────────────────────────
def load_devc(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=1)
    df.columns = df.columns.str.strip()
    return df

dfs = {}
for label, path in MESHES.items():
    if path.exists():
        dfs[label] = load_devc(path)
        t_max = dfs[label]["Time"].max()
        print(f"  {label}: loaded, t_max={t_max:.1f} s, rows={len(dfs[label])}")
    else:
        print(f"  {label}: NOT FOUND – skipping")

if not dfs:
    raise SystemExit("No DEVC files found.")

# Common time window: use overlap across loaded meshes
T_START = 550.0   # skip ramp-up transient (fire fully on by ~530s)
t_max_common = min(df["Time"].max() for df in dfs.values())
T_END = t_max_common
print(f"\nAveraging window: {T_START:.0f} – {T_END:.1f} s")

# ── Fig 1: vertical temperature profile ───────────────────────────────────
fig1, ax1 = plt.subplots(figsize=(5, 6))
ax1.set_title("Grid convergence — temperature profile\n(fire centerline, time-avg)", fontsize=11)

for label, df in dfs.items():
    mask = (df["Time"] >= T_START) & (df["Time"] <= T_END)
    sub  = df.loc[mask]
    T_avg = []
    for zl in Z_LABELS:
        col = f"pt_thermocouple_{zl}"
        if col in sub.columns:
            T_avg.append(sub[col].mean())
        else:
            T_avg.append(np.nan)
    ax1.plot(T_avg, Z_HEIGHTS, "o-", color=COLORS[label], label=label, linewidth=1.8, markersize=5)

ax1.set_xlabel("Temperature (°C)")
ax1.set_ylabel("Height z (m)")
ax1.legend(fontsize=9)
ax1.grid(True, linestyle="--", alpha=0.5)
ax1.set_ylim(0, 3.2)
fig1.tight_layout()
fig1.savefig(BASE.parent / "Results" / "grid_conv_temperature_profile.png", dpi=150)
print("Saved: grid_conv_temperature_profile.png")

# ── Fig 2: HRR time series ─────────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(7, 4))
ax2.set_title("Grid convergence — HRR time series", fontsize=11)

for label, path in HRR_FILES.items():
    if not path.exists():
        continue
    hrr = pd.read_csv(path, skiprows=1)
    hrr.columns = hrr.columns.str.strip()
    tcol = hrr.columns[0]
    # find HRR column (usually "HRR")
    hrr_col = [c for c in hrr.columns if "HRR" in c.upper() and "DHRR" not in c.upper()]
    if not hrr_col:
        continue
    ax2.plot(hrr[tcol].to_numpy(), hrr[hrr_col[0]].to_numpy(), color=COLORS[label], label=label, linewidth=1.5)

ax2.set_xlabel("Time (s)")
ax2.set_ylabel("HRR (kW)")
ax2.legend(fontsize=9)
ax2.grid(True, linestyle="--", alpha=0.5)
ax2.set_xlim(500, None)
fig2.tight_layout()
fig2.savefig(BASE.parent / "Results" / "grid_conv_hrr.png", dpi=150)
print("Saved: grid_conv_hrr.png")

# ── Fig 3: time series at selected z heights ───────────────────────────────
SELECTED_Z = [("z0p71", 0.71), ("z1p69", 1.69), ("z2p67", 2.67)]
fig3, axes = plt.subplots(len(SELECTED_Z), 1, figsize=(8, 8), sharex=True)
fig3.suptitle("Grid convergence — temperature time series at selected heights", fontsize=11)

for ax, (zl, zh) in zip(axes, SELECTED_Z):
    col = f"pt_thermocouple_{zl}"
    for label, df in dfs.items():
        if col in df.columns:
            ax.plot(df["Time"].to_numpy(), df[col].to_numpy(), color=COLORS[label], label=label,
                    linewidth=1.2, alpha=0.85)
    ax.set_ylabel(f"T (°C)\nz={zh:.2f} m", fontsize=9)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_xlim(500, None)

axes[-1].set_xlabel("Time (s)")
fig3.tight_layout()
fig3.savefig(BASE.parent / "Results" / "grid_conv_timeseries.png", dpi=150)
print("Saved: grid_conv_timeseries.png")

plt.show()
print("\nDone.")
