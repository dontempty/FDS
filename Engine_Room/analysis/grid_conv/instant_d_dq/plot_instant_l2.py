#!/usr/bin/env python3
"""
Instantaneous d_M5 / dq_M5 temperature z-profile comparison to ref_Mesh5.

For each target time 0, 10, ..., 300 s, the nearest saved SLCF frame is used.
Outputs under dy00, dy01, ..., dy14:
  - instant_l2_errors.csv
  - instant_l2_vs_time.png
  - best_profile.png
  - best_profile_by_case.png
Summary outputs in this directory:
  - instant_l2_best_summary.csv
  - best_time_vs_y.png
  - best_profiles_all_y.png
  - best_l2_by_y.png
"""
from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import fdsreader

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

ROOT = Path("/scratch/x3319a05/fds/Engine_Room")
RES = ROOT / "Results"
OUT = ROOT / "analysis" / "grid_conv" / "instant_d_dq"
REF_M5 = ROOT / "analysis" / "grid_conv" / "ref_Mesh5.csv"

OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(OUT / ".mplconfig"))

import matplotlib.pyplot as plt

CASES = [
    ("d_M5", "d_M5", "#1f77b4"),
    ("dq_M5", "dq_M5", "#d62728"),
]

SLICE_X = 8.1
FIRE_CENTER_Y = 1.45
DY_VALUES = np.round(np.arange(15) * 0.1, 1)
TARGET_TIMES = np.arange(0.0, 300.0 + 1.0e-9, 10.0)


def load_ref(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(path, delimiter=",")
    return data[:, 0], data[:, 1]


def load_temp_slice(case_dir: str):
    sim_path = RES / case_dir
    if not (sim_path / f"{case_dir}.smv").exists():
        raise FileNotFoundError(f"Missing SMV file for {case_dir}: {sim_path}")

    sim = fdsreader.Simulation(str(sim_path))
    candidates = [
        (abs(s.extent.x_start - SLICE_X), s)
        for s in sim.slices
        if s.orientation == 1 and "TEMP" in s.quantity.name.upper()
    ]
    if not candidates:
        raise RuntimeError(f"No YZ TEMPERATURE slice found for {case_dir}")

    return min(candidates, key=lambda item: item[0])[1]


def extract_profiles(
    case_dir: str,
    sl,
    z_ref: np.ndarray,
    dy_tag: str,
    dy_m: float,
    y_target: float,
) -> tuple[list[dict], dict[float, np.ndarray]]:
    times = np.asarray(sl.times, dtype=float)
    T_all = sl.to_global(masked=True, fill=np.nan)

    ext = sl.extent
    y_arr = np.linspace(ext.y_start, ext.y_end, T_all.shape[1])
    z_arr = np.linspace(ext.z_start, ext.z_end, T_all.shape[2])
    iy = int(np.argmin(np.abs(y_arr - y_target)))

    rows: list[dict] = []
    profiles: dict[float, np.ndarray] = {}
    used_indices: set[int] = set()

    for target_t in TARGET_TIMES:
        it = int(np.argmin(np.abs(times - target_t)))
        actual_t = float(times[it])
        profile_native = T_all[it, iy, :]
        profile_ref_z = np.interp(z_ref, z_arr, profile_native)
        profiles[target_t] = profile_ref_z

        used_indices.add(it)
        rows.append(
            {
                "case": case_dir,
                "dy_tag": dy_tag,
                "dy_m": dy_m,
                "target_time_s": target_t,
                "actual_time_s": actual_t,
                "time_delta_s": actual_t - target_t,
                "slice_x_m": float(sl.extent.x_start),
                "target_y_m": y_target,
                "actual_y_m": float(y_arr[iy]),
            }
        )

    if len(used_indices) != len(TARGET_TIMES):
        print(f"WARNING: {case_dir} reused one or more saved frames for target times.")

    return rows, profiles


def add_errors(rows: list[dict], profiles: dict[tuple[str, float], np.ndarray], T_ref: np.ndarray) -> None:
    for row in rows:
        key = (row["case"], row["target_time_s"])
        diff = profiles[key] - T_ref
        valid = np.isfinite(diff)
        row["n_points"] = int(valid.sum())
        row["l2_norm_C"] = float(np.sqrt(np.sum(diff[valid] ** 2)))
        row["rmse_C"] = float(np.sqrt(np.mean(diff[valid] ** 2)))
        row["max_abs_error_C"] = float(np.max(np.abs(diff[valid])))


def plot_l2(df: pd.DataFrame, out_path: Path, y_target: float, dy_tag: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for case, label, color in CASES:
        sub = df[df["case"] == case].sort_values("target_time_s")
        ax.plot(
            sub["target_time_s"],
            sub["l2_norm_C"],
            "o-",
            color=color,
            lw=2.0,
            ms=4,
            label=label,
        )

        best = sub.loc[sub["l2_norm_C"].idxmin()]
        ax.scatter(
            [best["target_time_s"]],
            [best["l2_norm_C"]],
            s=70,
            color=color,
            edgecolor="k",
            zorder=5,
        )

    overall = df.loc[df["l2_norm_C"].idxmin()]
    ax.axvline(overall["target_time_s"], color="0.4", ls=":", lw=1.2)
    ax.set_xlabel("Target time (s)")
    ax.set_ylabel("L2 norm vs ref_Mesh5 (C)")
    ax.set_title(
        "Instantaneous T(z) L2 error vs ref_Mesh5\n"
        f"{dy_tag}: nearest SLCF frame, YZ slice x={SLICE_X:.1f} m, y={y_target:.2f} m"
    )
    ax.grid(alpha=0.3)
    ax.legend(framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_best_profile(
    df: pd.DataFrame,
    profiles: dict[tuple[str, float], np.ndarray],
    z_ref: np.ndarray,
    T_ref: np.ndarray,
    out_path: Path,
    y_target: float,
    dy_tag: str,
) -> None:
    best = df.loc[df["l2_norm_C"].idxmin()]
    profile = profiles[(best["case"], best["target_time_s"])]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(z_ref, T_ref, "k--o", lw=1.8, ms=4, mfc="white", label="ref_Mesh5")
    ax.plot(
        z_ref,
        profile,
        "o-",
        lw=2.0,
        ms=4,
        label=(
            f"{best['case']} target {best['target_time_s']:.0f}s "
            f"(actual {best['actual_time_s']:.2f}s)"
        ),
    )
    ax.set_xlabel("Height z (m)")
    ax.set_ylabel("Temperature (C)")
    ax.set_title(
        "Minimum-error instantaneous z-profile\n"
        f"{dy_tag}, y={y_target:.2f} m, L2={best['l2_norm_C']:.2f} C, RMSE={best['rmse_C']:.2f} C"
    )
    ax.grid(alpha=0.3)
    ax.legend(framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_best_profile_by_case(
    df: pd.DataFrame,
    profiles: dict[tuple[str, float], np.ndarray],
    z_ref: np.ndarray,
    T_ref: np.ndarray,
    out_path: Path,
    y_target: float,
    dy_tag: str,
) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(z_ref, T_ref, "k--o", lw=1.8, ms=4, mfc="white", label="ref_Mesh5")

    for case, label, color in CASES:
        sub = df[df["case"] == case]
        best = sub.loc[sub["l2_norm_C"].idxmin()]
        profile = profiles[(case, best["target_time_s"])]
        ax.plot(
            z_ref,
            profile,
            "o-",
            color=color,
            lw=2.0,
            ms=4,
            label=(
                f"{label} best {best['target_time_s']:.0f}s "
                f"(L2={best['l2_norm_C']:.1f})"
            ),
        )

    ax.set_xlabel("Height z (m)")
    ax.set_ylabel("Temperature (C)")
    ax.set_title(f"Best instantaneous z-profile by case\n{dy_tag}, y={y_target:.2f} m")
    ax.grid(alpha=0.3)
    ax.legend(framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_best_time_vs_y(summary: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(8, 8), sharex=True)

    for case, label, color in CASES:
        sub = summary[summary["case"] == case].sort_values("target_y_m")
        axes[0].plot(
            sub["target_y_m"],
            sub["best_target_time_s"],
            "o-",
            color=color,
            lw=2.0,
            ms=4,
            label=label,
        )
        axes[1].plot(
            sub["target_y_m"],
            sub["best_l2_norm_C"],
            "o-",
            color=color,
            lw=2.0,
            ms=4,
            label=label,
        )

    axes[0].set_ylabel("Best target time (s)")
    axes[0].set_title("Best instantaneous match to ref_Mesh5 by y")
    axes[0].grid(alpha=0.3)
    axes[0].legend(framealpha=0.95)

    axes[1].set_xlabel("Target y (m)")
    axes[1].set_ylabel("Minimum L2 norm (C)")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_best_profiles_all_y(
    best_profiles: list[dict],
    z_ref: np.ndarray,
    T_ref: np.ndarray,
    out_path: Path,
) -> None:
    cmap = plt.get_cmap("viridis")
    norm = plt.Normalize(
        min(item["target_y_m"] for item in best_profiles),
        max(item["target_y_m"] for item in best_profiles),
    )
    global_best = min(best_profiles, key=lambda item: item["l2_norm_C"])

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(z_ref, T_ref, "k--o", lw=2.2, ms=4, mfc="white", label="ref_Mesh5", zorder=20)

    for item in best_profiles:
        color = cmap(norm(item["target_y_m"]))
        is_global = item is global_best
        ax.plot(
            z_ref,
            item["profile"],
            "o-",
            color=color,
            lw=2.6 if is_global else 1.3,
            ms=4 if is_global else 2,
            alpha=1.0 if is_global else 0.55,
            label=(
                f"BEST {item['dy_tag']} y={item['target_y_m']:.2f} "
                f"{item['case']} {item['target_time_s']:.0f}s L2={item['l2_norm_C']:.1f}"
                if is_global
                else None
            ),
            zorder=10 if is_global else 3,
        )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label("Best-profile y location (m)")

    ax.set_xlabel("Height z (m)")
    ax.set_ylabel("Temperature (C)")
    ax.set_title(
        "Best instantaneous z-profile from each dy\n"
        "thick line = global best among dy best profiles"
    )
    ax.grid(alpha=0.3)
    ax.legend(framealpha=0.95, loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_best_l2_by_y(best_profiles: list[dict], out_path: Path) -> None:
    ordered = sorted(best_profiles, key=lambda item: item["target_y_m"])
    colors = ["#1f77b4" if item["case"] == "d_M5" else "#d62728" for item in ordered]
    labels = [
        f"{item['dy_tag']}\n{item['case']}\n{item['target_time_s']:.0f}s"
        for item in ordered
    ]
    l2 = [item["l2_norm_C"] for item in ordered]
    global_idx = int(np.argmin(l2))

    fig, ax = plt.subplots(figsize=(11, 5))
    bars = ax.bar(labels, l2, color=colors, alpha=0.8)
    bars[global_idx].set_edgecolor("k")
    bars[global_idx].set_linewidth(2.0)

    ax.set_ylabel("Best L2 norm vs ref_Mesh5 (C)")
    ax.set_title("Best case/time at each dy, compared by L2 error")
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> None:
    z_ref, T_ref = load_ref(REF_M5)
    slices = {}

    for case, _, _ in CASES:
        print(f"Loading {case}...")
        slices[case] = load_temp_slice(case)

    summary_rows: list[dict] = []
    all_rows: list[pd.DataFrame] = []
    best_profiles: list[dict] = []

    for idx, dy_m in enumerate(DY_VALUES):
        dy_tag = f"dy{idx:02d}"
        y_target = round(FIRE_CENTER_Y + float(dy_m), 3)
        out_dir = OUT / dy_tag
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"Processing {dy_tag}: y={y_target:.2f} m...")
        rows: list[dict] = []
        profiles: dict[tuple[str, float], np.ndarray] = {}

        for case, _, _ in CASES:
            case_rows, case_profiles = extract_profiles(case, slices[case], z_ref, dy_tag, float(dy_m), y_target)
            rows.extend(case_rows)
            for target_t, profile in case_profiles.items():
                profiles[(case, target_t)] = profile

        add_errors(rows, profiles, T_ref)
        df = pd.DataFrame(rows).sort_values(["case", "target_time_s"])
        all_rows.append(df)

        csv_path = out_dir / "instant_l2_errors.csv"
        df.to_csv(csv_path, index=False)

        plot_l2(df, out_dir / "instant_l2_vs_time.png", y_target, dy_tag)
        plot_best_profile(df, profiles, z_ref, T_ref, out_dir / "best_profile.png", y_target, dy_tag)
        plot_best_profile_by_case(
            df,
            profiles,
            z_ref,
            T_ref,
            out_dir / "best_profile_by_case.png",
            y_target,
            dy_tag,
        )

        overall = df.loc[df["l2_norm_C"].idxmin()]
        best_profiles.append(
            {
                "dy_tag": dy_tag,
                "dy_m": float(dy_m),
                "target_y_m": y_target,
                "case": overall["case"],
                "target_time_s": overall["target_time_s"],
                "actual_time_s": overall["actual_time_s"],
                "l2_norm_C": overall["l2_norm_C"],
                "rmse_C": overall["rmse_C"],
                "profile": profiles[(overall["case"], overall["target_time_s"])],
            }
        )
        summary_rows.append(
            {
                "dy_tag": dy_tag,
                "dy_m": float(dy_m),
                "target_y_m": y_target,
                "case": "overall",
                "best_case": overall["case"],
                "best_target_time_s": overall["target_time_s"],
                "best_actual_time_s": overall["actual_time_s"],
                "best_l2_norm_C": overall["l2_norm_C"],
                "best_rmse_C": overall["rmse_C"],
                "best_max_abs_error_C": overall["max_abs_error_C"],
            }
        )

        for case, _, _ in CASES:
            sub = df[df["case"] == case]
            best = sub.loc[sub["l2_norm_C"].idxmin()]
            summary_rows.append(
                {
                    "dy_tag": dy_tag,
                    "dy_m": float(dy_m),
                    "target_y_m": y_target,
                    "case": case,
                    "best_case": case,
                    "best_target_time_s": best["target_time_s"],
                    "best_actual_time_s": best["actual_time_s"],
                    "best_l2_norm_C": best["l2_norm_C"],
                    "best_rmse_C": best["rmse_C"],
                    "best_max_abs_error_C": best["max_abs_error_C"],
                }
            )

    all_df = pd.concat(all_rows, ignore_index=True)
    all_df.to_csv(OUT / "instant_l2_errors_all_y.csv", index=False)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "instant_l2_best_summary.csv", index=False)
    plot_best_time_vs_y(summary[summary["case"] != "overall"], OUT / "best_time_vs_y.png")
    plot_best_profiles_all_y(best_profiles, z_ref, T_ref, OUT / "best_profiles_all_y.png")
    plot_best_l2_by_y(best_profiles, OUT / "best_l2_by_y.png")

    best_overall = summary[summary["case"] == "overall"].loc[
        summary[summary["case"] == "overall"]["best_l2_norm_C"].idxmin()
    ]
    print(f"Wrote per-y outputs under {OUT / 'dyXX'}")
    print(f"Wrote {OUT / 'instant_l2_errors_all_y.csv'}")
    print(f"Wrote {OUT / 'instant_l2_best_summary.csv'}")
    print(f"Wrote {OUT / 'best_time_vs_y.png'}")
    print(f"Wrote {OUT / 'best_profiles_all_y.png'}")
    print(f"Wrote {OUT / 'best_l2_by_y.png'}")
    print(
        "Best across all y: "
        f"{best_overall['dy_tag']} y={best_overall['target_y_m']:.2f} m "
        f"{best_overall['best_case']} target={best_overall['best_target_time_s']:.0f}s "
        f"actual={best_overall['best_actual_time_s']:.2f}s "
        f"L2={best_overall['best_l2_norm_C']:.3f} C "
        f"RMSE={best_overall['best_rmse_C']:.3f} C"
    )


if __name__ == "__main__":
    main()
