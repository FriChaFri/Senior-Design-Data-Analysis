#!/usr/bin/env python3
"""Build a self-contained LaTeX report for the official gameplay battery workflow."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys
from typing import Iterable

import matplotlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import run_battery_sizing as official_workflow  # noqa: E402
import generate_acceleration_processing_review as accel_review  # noqa: E402

from imu_pipeline.battery_sizing import _scenario_slug, run_battery_sizing_pipeline  # noqa: E402
from imu_pipeline.game_processing import build_clean_games_dataset  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402


REPORT_ROOT = Path("reports/official_gameplay_battery_report")
FIGURES_DIR = REPORT_ROOT / "figures"
TABLES_DIR = REPORT_ROOT / "tables"
ARTIFACTS_DIR = REPORT_ROOT / "artifacts"

WORKED_GAME = "Game1CharlesPhone"
WORKED_VOLTAGE_V = 48.0
WORKED_BATTERY = "nmc_high_rate"
MPS_TO_MPH = 2.2369362920544


def _ensure_output_dirs() -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _format_removed_windows(windows: list[dict[str, float]]) -> str:
    if not windows:
        return "None"
    return ", ".join(f"{window['start']:.1f}-{window['end']:.1f} min" for window in windows)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _build_official_outputs() -> pd.DataFrame:
    build_clean_games_dataset(processed_dir=official_workflow.INPUT_DIR)
    results = run_battery_sizing_pipeline(
        input_dir=official_workflow.INPUT_DIR,
        output_dir=official_workflow.OUTPUT_DIR,
        vehicle=official_workflow.VEHICLE,
        signal=official_workflow.SIGNAL,
        motor=official_workflow.MOTOR,
        voltage_candidates_v=official_workflow.VOLTAGE_CANDIDATES_V,
        batteries=official_workflow.BATTERIES,
        write_timeseries=True,
        write_plots=True,
    )
    return pd.DataFrame([result.to_summary_row() for result in results])


def _load_cleaning_manifest() -> dict[str, dict[str, object]]:
    path = official_workflow.INPUT_DIR / "cleaning_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_worked_trace() -> pd.DataFrame:
    slug = _scenario_slug(
        WORKED_GAME,
        official_workflow.MOTOR.name,
        WORKED_BATTERY,
        WORKED_VOLTAGE_V,
    )
    trace_path = official_workflow.OUTPUT_DIR / "timeseries" / f"{slug}.parquet"
    return pd.read_parquet(trace_path)


def _bool_to_yes_no(values: Iterable[bool]) -> list[str]:
    return ["Yes" if bool(value) else "No" for value in values]


def _latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _write_table(frame: pd.DataFrame, path: Path, *, longtable: bool = False) -> None:
    columns = list(frame.columns)
    column_format = "l" * len(columns)
    env = "longtable" if longtable else "tabular"
    lines = [fr"\begin{{{env}}}{{{column_format}}}", r"\toprule"]
    lines.append(" & ".join(_latex_escape(column) for column in columns) + r" \\")
    lines.append(r"\midrule")
    for _, row in frame.iterrows():
        lines.append(" & ".join(_latex_escape(value) for value in row.tolist()) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(fr"\end{{{env}}}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_assumptions_table() -> None:
    signal = asdict(official_workflow.SIGNAL)
    vehicle = asdict(official_workflow.VEHICLE)
    motor = asdict(official_workflow.MOTOR)

    rows: list[dict[str, str]] = []
    for key, value in signal.items():
        rows.append({"Group": "Signal", "Parameter": key, "Value": str(value)})
    for key, value in vehicle.items():
        rows.append({"Group": "Vehicle", "Parameter": key, "Value": str(value)})
    for key, value in motor.items():
        rows.append({"Group": "Motor", "Parameter": key, "Value": str(value)})
    for battery in official_workflow.BATTERIES:
        rows.append(
            {
                "Group": f"Battery {battery.name}",
                "Parameter": "specific_energy_wh_per_kg / usable_fraction / continuous_c / peak_c",
                "Value": (
                    f"{battery.specific_energy_wh_per_kg}, {battery.usable_fraction}, "
                    f"{battery.continuous_c}, {battery.peak_c}"
                ),
            }
        )

    _write_table(pd.DataFrame(rows), TABLES_DIR / "assumptions.tex", longtable=True)


def _write_data_provenance_table(cleaning_manifest: dict[str, dict[str, object]]) -> None:
    rows = []
    for game_name in sorted(cleaning_manifest):
        entry = cleaning_manifest[game_name]
        rows.append(
            {
                "Game": game_name,
                "Keep Start (min)": f"{entry['kept_window_minutes']['start']:.1f}",
                "Keep End (min)": f"{entry['kept_window_minutes']['end']:.1f}",
                "Removed Windows": _format_removed_windows(entry["removed_windows_minutes"]),
                "Raw Rows": f"{entry['raw_rows']:,}",
                "Cleaned Rows": f"{entry['cleaned_rows']:,}",
                "Rows Removed": f"{entry['rows_removed']:,}",
            }
        )
    _write_table(pd.DataFrame(rows), TABLES_DIR / "data_provenance.tex")


def _write_worked_example_table(worked_row: pd.Series, peak_row: pd.Series) -> None:
    rows = [
        {"Quantity": "Worked example game", "Value": WORKED_GAME, "Unit": ""},
        {"Quantity": "Battery chemistry", "Value": WORKED_BATTERY, "Unit": ""},
        {"Quantity": "Pack voltage", "Value": f"{WORKED_VOLTAGE_V:.0f}", "Unit": "V"},
        {"Quantity": "Cleaned gameplay energy", "Value": f"{worked_row.cleaned_gameplay_energy_wh:.2f}", "Unit": "Wh"},
        {"Quantity": "Battery usable fraction", "Value": "0.90", "Unit": "-"},
        {"Quantity": "Nominal battery energy", "Value": f"{worked_row.nominal_energy_wh:.2f}", "Unit": "Wh"},
        {"Quantity": "Required nominal capacity", "Value": f"{worked_row.nominal_capacity_ah:.3f}", "Unit": "Ah"},
        {"Quantity": "Battery mass", "Value": f"{worked_row.battery_mass_kg:.3f}", "Unit": "kg"},
        {"Quantity": "Peak battery power sample time", "Value": f"{peak_row['profile_elapsed_min']:.2f}", "Unit": "min"},
        {"Quantity": "Peak traction force", "Value": f"{peak_row['traction_force_n']:.2f}", "Unit": "N"},
        {"Quantity": "Peak wheel torque", "Value": f"{peak_row['wheel_torque_total_nm']:.2f}", "Unit": "N m"},
        {"Quantity": "Peak motor torque", "Value": f"{peak_row['motor_torque_nm']:.3f}", "Unit": "N m"},
        {"Quantity": "Peak motor current", "Value": f"{peak_row['motor_current_a']:.3f}", "Unit": "A"},
        {"Quantity": "Peak battery power", "Value": f"{peak_row['battery_power_w']:.2f}", "Unit": "W"},
        {"Quantity": "Peak battery current", "Value": f"{peak_row['battery_current_a']:.3f}", "Unit": "A"},
    ]
    _write_table(pd.DataFrame(rows), TABLES_DIR / "worked_example.tex")


def _write_results_table(summary: pd.DataFrame) -> None:
    results = summary[
        [
            "game_name",
            "voltage_v",
            "battery_name",
            "cleaned_gameplay_energy_wh",
            "nominal_capacity_ah",
            "battery_mass_kg",
            "peak_battery_current_a",
            "peak_battery_c_rate",
            "motor_peak_current_violation",
            "battery_peak_c_violation",
        ]
    ].copy()
    results.columns = [
        "Game",
        "Voltage (V)",
        "Battery",
        "Gameplay Energy (Wh)",
        "Capacity (Ah)",
        "Battery Mass (kg)",
        "Peak Pack Current (A)",
        "Peak C-Rate",
        "Motor Peak Violation",
        "Battery Peak Violation",
    ]
    for column in ("Gameplay Energy (Wh)", "Capacity (Ah)", "Battery Mass (kg)", "Peak Pack Current (A)", "Peak C-Rate"):
        results[column] = results[column].map(lambda value: f"{value:.2f}")
    results["Voltage (V)"] = results["Voltage (V)"].map(lambda value: f"{value:.0f}")
    results["Motor Peak Violation"] = _bool_to_yes_no(results["Motor Peak Violation"])
    results["Battery Peak Violation"] = _bool_to_yes_no(results["Battery Peak Violation"])
    _write_table(results, TABLES_DIR / "results_overview.tex", longtable=True)


def _write_findings_table(summary: pd.DataFrame) -> None:
    findings = summary.loc[summary["voltage_v"] == 48.0, [
        "game_name",
        "battery_name",
        "peak_motor_current_a",
        "peak_battery_current_a",
        "peak_battery_c_rate",
        "motor_peak_current_violation",
        "battery_peak_c_violation",
    ]].copy()
    findings.columns = [
        "Game",
        "Battery",
        "Peak Motor Current (A)",
        "Peak Pack Current (A) at 48 V",
        "Peak C-Rate",
        "Motor Peak Violation",
        "Battery Peak Violation",
    ]
    for column in ("Peak Motor Current (A)", "Peak Pack Current (A) at 48 V", "Peak C-Rate"):
        findings[column] = findings[column].map(lambda value: f"{value:.2f}")
    findings["Motor Peak Violation"] = _bool_to_yes_no(findings["Motor Peak Violation"])
    findings["Battery Peak Violation"] = _bool_to_yes_no(findings["Battery Peak Violation"])
    _write_table(findings, TABLES_DIR / "verification_findings.tex")


def _generate_workflow_figure(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 3.5))
    ax.axis("off")

    labels = [
        "Raw IMU CSVs",
        "Trim to gameplay windows",
        "Interpolate collisions\n+ clip acceleration\n+ cap speed",
        "Yaw-aware dynamics",
        "Battery Wh / Ah / current",
    ]
    x_positions = [0.06, 0.27, 0.52, 0.75, 0.94]
    width = 0.16
    height = 0.34
    for x, label in zip(x_positions, labels):
        box = FancyBboxPatch(
            (x - (width / 2.0), 0.33),
            width,
            height,
            boxstyle="round,pad=0.02",
            facecolor="#f6f3eb",
            edgecolor="#3b4b59",
            linewidth=1.5,
        )
        ax.add_patch(box)
        ax.text(x, 0.5, label, ha="center", va="center", fontsize=11, weight="bold")

    for index in range(len(x_positions) - 1):
        arrow = FancyArrowPatch(
            (x_positions[index] + (width / 2.0) - 0.01, 0.5),
            (x_positions[index + 1] - (width / 2.0) + 0.01, 0.5),
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=1.6,
            color="#3b4b59",
        )
        ax.add_patch(arrow)

    ax.text(0.5, 0.87, "Official gameplay-driven battery-sizing workflow", ha="center", va="center", fontsize=16, weight="bold")
    ax.text(0.5, 0.16, "Source of truth: scripts/run_battery_sizing.py", ha="center", va="center", fontsize=11)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _generate_data_provenance_figure(cleaning_manifest: dict[str, dict[str, object]], path: Path) -> None:
    games = sorted(cleaning_manifest)
    raw_rows = [cleaning_manifest[game]["raw_rows"] for game in games]
    cleaned_rows = [cleaning_manifest[game]["cleaned_rows"] for game in games]
    removed_rows = [cleaning_manifest[game]["rows_removed"] for game in games]

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    x = np.arange(len(games))
    width = 0.35

    axes[0].bar(x - (width / 2.0), raw_rows, width=width, color="#9ecae9", label="Raw rows")
    axes[0].bar(x + (width / 2.0), cleaned_rows, width=width, color="#54a24b", label="Cleaned rows")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(games)
    axes[0].set_ylabel("Rows")
    axes[0].set_title("Raw versus cleaned gameplay rows")
    axes[0].legend(loc="upper right")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(x, removed_rows, color="#e45756")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(games)
    axes[1].set_ylabel("Rows removed")
    axes[1].set_title("Rows removed by manual gameplay trimming")
    axes[1].grid(axis="y", alpha=0.25)

    for idx, game in enumerate(games):
        entry = cleaning_manifest[game]
        keep = entry["kept_window_minutes"]
        removed_windows = _format_removed_windows(entry["removed_windows_minutes"])
        axes[1].text(
            idx,
            removed_rows[idx] * 1.02 if removed_rows[idx] else 1.0,
            f"keep {keep['start']:.1f}-{keep['end']:.1f} min\nremove {removed_windows}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _shade_regions(ax: plt.Axes, elapsed: np.ndarray, impact_mask: np.ndarray) -> None:
    if not np.any(impact_mask):
        return
    starts = np.flatnonzero(impact_mask & ~np.concatenate(([False], impact_mask[:-1])))
    ends = np.flatnonzero(impact_mask & ~np.concatenate((impact_mask[1:], [False])))
    for start, end in zip(starts, ends):
        ax.axvspan(float(elapsed[start]), float(elapsed[end]), color="#e45756", alpha=0.12)


def _generate_signal_cleaning_figure(path: Path) -> None:
    source_path = official_workflow.INPUT_DIR / f"{WORKED_GAME}_clean.csv"
    frame, metadata = accel_review.compute_review_frame(
        source_path,
        official_workflow.SIGNAL,
        official_workflow.VEHICLE,
    )

    elapsed = frame["elapsed_min"].to_numpy(dtype=float)
    impact_mask = frame["impact_mask"].to_numpy(dtype=bool)

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True, constrained_layout=True)

    axes[0].plot(elapsed, frame["raw_planar_mag_m_s2"], color="#9ecae9", linewidth=0.8, alpha=0.55, label="Raw planar magnitude")
    axes[0].plot(
        elapsed,
        np.linalg.norm(frame[["planar_repaired_x_m_s2", "planar_repaired_y_m_s2"]].to_numpy(dtype=float), axis=1),
        color="#4c78a8",
        linewidth=0.9,
        label="After collision interpolation",
    )
    axes[0].plot(
        elapsed,
        np.linalg.norm(frame[["planar_clipped_x_m_s2", "planar_clipped_y_m_s2"]].to_numpy(dtype=float), axis=1),
        color="#54a24b",
        linewidth=1.1,
        label="Final clipped planar magnitude",
    )
    _shade_regions(axes[0], elapsed, impact_mask)
    axes[0].set_title(f"{WORKED_GAME}: signal cleaning before dynamics")
    axes[0].set_ylabel("Acceleration (m/s^2)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.25)

    axes[1].plot(elapsed, frame["unclipped_propulsion_m_s2"], color="#e45756", linewidth=0.8, label="Unclipped propulsion")
    axes[1].plot(elapsed, frame["clipped_propulsion_m_s2"], color="#54a24b", linewidth=1.0, label="Final propulsion")
    axes[1].axhline(official_workflow.SIGNAL.max_realistic_accel_m_s2, color="#666666", linestyle="--", linewidth=1.0)
    axes[1].axhline(-official_workflow.SIGNAL.max_realistic_accel_m_s2, color="#666666", linestyle="--", linewidth=1.0)
    _shade_regions(axes[1], elapsed, impact_mask)
    axes[1].set_ylabel("Acceleration (m/s^2)")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.25)

    axes[2].plot(elapsed, frame["surrogate_speed_m_s"], color="#f58518", linewidth=1.0, label="Surrogate speed")
    axes[2].axhline(official_workflow.SIGNAL.v_max_m_s, color="#444444", linestyle="--", linewidth=1.0, label="11 mph cap")
    axes[2].set_xlabel("Elapsed time (min)")
    axes[2].set_ylabel("Speed (m/s)")
    axes[2].legend(loc="upper right")
    axes[2].grid(alpha=0.25)

    fig.text(
        0.99,
        0.02,
        (
            f"Detected collision windows: {metadata['impact_window_count']}    "
            f"Acceleration clip: {official_workflow.SIGNAL.max_realistic_accel_m_s2:.2f} m/s^2    "
            f"Speed cap: {official_workflow.SIGNAL.v_max_m_s:.3f} m/s"
        ),
        ha="right",
        va="bottom",
        fontsize=10,
    )
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _generate_worked_example_figure(trace: pd.DataFrame, path: Path) -> pd.Series:
    dt_s = float(np.median(np.diff(trace["time_s"].to_numpy(dtype=float))))
    cumulative_energy_wh = np.cumsum(trace["battery_power_w"].to_numpy(dtype=float) * dt_s) / 3600.0
    peak_index = int(trace["battery_power_w"].idxmax())
    peak_row = trace.loc[peak_index]
    plot_step = 10

    fig, axes = plt.subplots(4, 1, figsize=(15, 12), sharex=True, constrained_layout=True)
    axes[0].plot(trace["profile_elapsed_min"].iloc[::plot_step], trace["forward_accel_m_s2"].iloc[::plot_step], color="#54a24b")
    axes[0].set_ylabel("m/s^2")
    axes[0].set_title("Worked example: Game1 + 48 V + NMC")
    axes[0].grid(alpha=0.25)

    axes[1].plot(trace["profile_elapsed_min"].iloc[::plot_step], trace["surrogate_speed_m_s"].iloc[::plot_step], color="#f58518")
    axes[1].axhline(official_workflow.SIGNAL.v_max_m_s, color="#444444", linestyle="--", linewidth=1.0)
    axes[1].set_ylabel("m/s")
    axes[1].grid(alpha=0.25)

    axes[2].plot(trace["profile_elapsed_min"].iloc[::plot_step], trace["battery_power_w"].iloc[::plot_step], color="#4c78a8")
    axes[2].scatter([peak_row["profile_elapsed_min"]], [peak_row["battery_power_w"]], color="#e45756", zorder=3)
    axes[2].set_ylabel("W")
    axes[2].grid(alpha=0.25)

    axes[3].plot(trace["profile_elapsed_min"].iloc[::plot_step], cumulative_energy_wh[::plot_step], color="#222222")
    axes[3].set_xlabel("Session time (min)")
    axes[3].set_ylabel("Wh")
    axes[3].grid(alpha=0.25)

    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    peak_row = peak_row.copy()
    peak_row["cumulative_energy_wh"] = cumulative_energy_wh[peak_index]
    return peak_row


def _generate_voltage_sweep_figure(summary: pd.DataFrame, path: Path) -> None:
    nmc = summary.loc[summary["battery_name"] == "nmc_high_rate"].copy()
    games = sorted(nmc["game_name"].unique())

    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True, constrained_layout=True)
    for game_name in games:
        game = nmc.loc[nmc["game_name"] == game_name].sort_values("voltage_v")
        axes[0].plot(game["voltage_v"], game["cleaned_gameplay_energy_wh"], marker="o", linewidth=2.0, label=game_name)
        axes[1].plot(game["voltage_v"], game["peak_battery_current_a"], marker="o", linewidth=2.0, label=game_name)
        axes[2].plot(game["voltage_v"], game["nominal_capacity_ah"], marker="o", linewidth=2.0, label=game_name)

    axes[0].set_title("Voltage sweep on the same cleaned gameplay demand")
    axes[0].set_ylabel("Gameplay Energy (Wh)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.25)

    axes[1].set_ylabel("Peak Pack Current (A)")
    axes[1].grid(alpha=0.25)

    axes[2].set_ylabel("Required Capacity (Ah)")
    axes[2].set_xlabel("Pack voltage (V)")
    axes[2].grid(alpha=0.25)

    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _generate_chemistry_comparison_figure(summary: pd.DataFrame, path: Path) -> None:
    selected = summary.loc[summary["voltage_v"] == WORKED_VOLTAGE_V].copy()
    selected["label"] = selected["game_name"].str.replace("CharlesPhone", "", regex=False) + "\n" + selected["battery_name"]
    colors = ["#4c78a8", "#54a24b", "#f58518", "#4c78a8", "#54a24b", "#f58518"]

    fig, axes = plt.subplots(3, 1, figsize=(12, 12), constrained_layout=True)
    axes[0].bar(selected["label"], selected["nominal_capacity_ah"], color=colors)
    axes[0].set_ylabel("Ah")
    axes[0].set_title("48 V chemistry comparison")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(selected["label"], selected["battery_mass_kg"], color=colors)
    axes[1].set_ylabel("kg")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].bar(selected["label"], selected["peak_battery_c_rate"], color=colors)
    axes[2].set_ylabel("Peak C-rate")
    axes[2].grid(axis="y", alpha=0.25)

    for axis in axes:
        axis.tick_params(axis="x", rotation=0)

    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _copy_existing_official_plots() -> None:
    for source in sorted((official_workflow.OUTPUT_DIR / "plots").glob("*.png")):
        destination = FIGURES_DIR / source.name
        _copy_file(source, destination)


def _write_readme() -> None:
    lines = [
        "# Official Gameplay Battery Report",
        "",
        "This folder is self-contained and intended to be copied into Overleaf.",
        "",
        "## Files",
        "",
        "- `main.tex`: primary LaTeX source",
        "- `figures/`: local PNG figures used by the report",
        "- `tables/`: local LaTeX tables included by `main.tex`",
        "- `artifacts/`: copied CSV and JSON inputs used for audit/reference",
        "",
        "## Compile",
        "",
        "Use pdfLaTeX in Overleaf. No external files outside this folder are required.",
    ]
    (REPORT_ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_main_tex(summary: pd.DataFrame, worked_row: pd.Series, cleaning_manifest: dict[str, dict[str, object]]) -> None:
    game_energy = (
        summary[["game_name", "cleaned_gameplay_energy_wh"]]
        .drop_duplicates()
        .sort_values("cleaned_gameplay_energy_wh", ascending=False)
        .reset_index(drop=True)
    )
    game1_energy = float(game_energy.loc[game_energy["game_name"] == "Game1CharlesPhone", "cleaned_gameplay_energy_wh"].iloc[0])
    game2_energy = float(game_energy.loc[game_energy["game_name"] == "Game2CharlesPhone", "cleaned_gameplay_energy_wh"].iloc[0])
    usable_fraction = next(battery.usable_fraction for battery in official_workflow.BATTERIES if battery.name == WORKED_BATTERY)
    specific_energy = next(battery.specific_energy_wh_per_kg for battery in official_workflow.BATTERIES if battery.name == WORKED_BATTERY)
    game1_removed = cleaning_manifest["Game1CharlesPhone"]["rows_removed"]
    game2_removed = cleaning_manifest["Game2CharlesPhone"]["rows_removed"]

    report_text = f"""\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{booktabs}}
\\usepackage{{longtable}}
\\usepackage{{amsmath}}
\\usepackage{{float}}
\\usepackage{{hyperref}}
\\setlength{{\\parskip}}{{0.6em}}
\\setlength{{\\parindent}}{{0pt}}

\\title{{Official Gameplay-Driven Battery Sizing Report}}
\\author{{Senior Design Data Analysis Repository}}
\\date{{April 7, 2026}}

\\begin{{document}}
\\maketitle

\\section*{{Purpose}}
This report explains the official battery-sizing workflow in this repository. The final battery answer comes from cleaned gameplay IMU data only. The project specifications are used to bound the gameplay demand during cleaning, not to create a second battery-sizing branch.

The current official workflow uses:
\\begin{{itemize}}
  \\item gameplay trimming from the raw phone exports,
  \\item in-place interpolation across collision-like spikes,
  \\item acceleration clipping at {official_workflow.SIGNAL.max_realistic_accel_m_s2:.2f} \\(\\mathrm{{m/s^2}}\\),
  \\item surrogate speed capping at {official_workflow.SIGNAL.v_max_m_s:.5f} \\(\\mathrm{{m/s}}\\) ({official_workflow.SIGNAL.v_max_m_s * MPS_TO_MPH:.2f} mph),
  \\item yaw-aware wheel and motor dynamics,
  \\item battery sizing across {", ".join(str(int(value)) for value in official_workflow.VOLTAGE_CANDIDATES_V)} V and the configured chemistries.
\\end{{itemize}}

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/workflow_diagram.png}}
  \\caption{{Official gameplay-driven battery-sizing workflow used in this repository.}}
\\end{{figure}}

\\section{{Data Provenance}}
Two cleaned gameplay sessions are used. Game 1 is the higher-energy session at {game1_energy:.2f} Wh. Game 2 integrates to {game2_energy:.2f} Wh. The manual trimming step removes {game1_removed:,} rows from Game 1 and {game2_removed:,} rows from Game 2 before the signal-cleaning stage begins.

\\input{{tables/data_provenance.tex}}

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/data_provenance.png}}
  \\caption{{Raw versus cleaned gameplay rows after the repository's trim windows are applied.}}
\\end{{figure}}

\\section{{Signal Cleaning Math}}
The phone exports provide user acceleration, gravity, and motion-rotation channels. The repository converts those into a bounded planar propulsion signal.

\\textbf{{Unit conversion}}
\\begin{{equation}}
a_{{\\mathrm{{user}},m/s^2}} = a_{{\\mathrm{{user}},g}} \\times 9.80665
\\end{{equation}}

\\textbf{{Planar projection after gravity alignment}}
\\begin{{equation}}
\\mathbf{{a}}_{{\\mathrm{{planar}}}} = \\mathbf{{a}}_{{\\mathrm{{aligned}}}} - \\left(\\mathbf{{a}}_{{\\mathrm{{aligned}}}} \\cdot \\hat{{g}}\\right)\\hat{{g}}
\\end{{equation}}

\\textbf{{Collision detection and interpolation}}
Samples are marked when either planar acceleration magnitude or planar jerk exceeds the official thresholds:
\\begin{{equation}}
\\|\\mathbf{{a}}_{{\\mathrm{{planar}}}}\\| \\ge {official_workflow.SIGNAL.impact_accel_threshold_m_s2:.0f}
\\quad \\text{{or}} \\quad
\\left\\|\\frac{{d\\mathbf{{a}}_{{\\mathrm{{planar}}}}}}{{dt}}\\right\\| \\ge {official_workflow.SIGNAL.impact_jerk_threshold_m_s3:.0f}
\\end{{equation}}
Those windows are padded by {official_workflow.SIGNAL.impact_padding_s:.2f} s and linearly interpolated in place.

\\textbf{{Filtering and clipping}}
Each planar axis is winsorized at the {official_workflow.SIGNAL.winsor_percentile:.1f}th percentile, low-pass filtered, detrended with an {official_workflow.SIGNAL.bias_window_s:.1f} s rolling median, and clipped to:
\\begin{{equation}}
\\|\\mathbf{{a}}_{{\\mathrm{{final}}}}\\| \\le {official_workflow.SIGNAL.max_realistic_accel_m_s2:.2f}\\,\\mathrm{{m/s^2}}
\\end{{equation}}

\\textbf{{Surrogate speed integration}}
The planar acceleration is integrated to a surrogate speed state with zero-velocity resets during stationary periods and a hard cap:
\\begin{{equation}}
\\|\\mathbf{{v}}\\| \\le {official_workflow.SIGNAL.v_max_m_s:.5f}\\,\\mathrm{{m/s}}
\\end{{equation}}

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/signal_cleaning.png}}
  \\caption{{How Game 1 is cleaned before the battery model is applied.}}
\\end{{figure}}

\\section{{Dynamics And Battery Math}}
With the cleaned gameplay demand in hand, the repository computes wheel load, motor load, and battery load.

The current official workflow fixes total system mass at {official_workflow.VEHICLE.system_mass_kg:.0f} kg. That means the cleaned gameplay energy is the same across voltages and chemistries. Voltage changes pack current and required amp-hours. Chemistry changes usable fraction, nominal energy, mass, and C-rate checks.

The main force terms are:
\\begin{{align}}
F_{{\\mathrm{{roll}}}} &= c_{{rr}} m g \\cos(\\theta) \\\\
F_{{\\mathrm{{aero}}}} &= \\frac{{1}}{{2}} \\rho C_dA v^2 \\\\
F_{{\\mathrm{{grade}}}} &= m g \\sin(\\theta)
\\end{{align}}

For turning, the left and right wheel speeds are:
\\begin{{align}}
v_L &= v - \\frac{{b}}{{2}}\\omega \\\\
v_R &= v + \\frac{{b}}{{2}}\\omega
\\end{{align}}
with yaw torque:
\\begin{{equation}}
\\tau_{{\\mathrm{{yaw}}}} = I_{{\\mathrm{{yaw}}}}\\alpha_{{\\mathrm{{yaw}}}}
\\end{{equation}}

Wheel torque, motor torque, and current are:
\\begin{{align}}
\\tau_{{\\mathrm{{wheel}}}} &= rF + I_{{\\mathrm{{wheel}}}}\\frac{{a_{{\\mathrm{{wheel}}}}}}{{r}} \\\\
\\tau_{{\\mathrm{{motor}}}} &= \\frac{{\\tau_{{\\mathrm{{wheel,per\\ motor}}}}}}{{G\\eta_{{gear}}}} \\\\
I_{{\\mathrm{{motor}}}} &= \\frac{{\\tau_{{\\mathrm{{motor}}}}}}{{K_t}}
\\end{{align}}

No regenerative braking is credited. Battery power is:
\\begin{{equation}}
P_{{\\mathrm{{battery}}}} =
\\begin{{cases}}
\\dfrac{{P_{{\\mathrm{{wheel}}}}}}{{\\eta_{{drive}}}} + P_{{\\mathrm{{aux}}}}, & P_{{\\mathrm{{wheel}}}} > 0 \\\\
P_{{\\mathrm{{aux}}}}, & P_{{\\mathrm{{wheel}}}} \\le 0
\\end{{cases}}
\\end{{equation}}

The final battery equations are:
\\begin{{align}}
E_{{\\mathrm{{usable}}}} &= \\sum P_{{\\mathrm{{battery}}}}\\,\\Delta t / 3600 \\\\
E_{{\\mathrm{{nom}}}} &= E_{{\\mathrm{{usable}}}} / f_{{\\mathrm{{usable}}}} \\\\
C_{{\\mathrm{{nom}}}} &= E_{{\\mathrm{{nom}}}} / V_{{pack}} \\\\
m_{{\\mathrm{{battery}}}} &= E_{{\\mathrm{{nom}}}} / e_{{\\mathrm{{specific}}}}
\\end{{align}}

\\section{{Worked Example: Game 1 at 48 V with NMC}}
This report uses the hardest gameplay session and the common 48 V design point as the worked example.

\\input{{tables/worked_example.tex}}

The core battery arithmetic for the worked example is:
\\begin{{align}}
E_{{\\mathrm{{usable}}}} &= {worked_row.cleaned_gameplay_energy_wh:.2f}\\,\\mathrm{{Wh}} \\\\
E_{{\\mathrm{{nom}}}} &= \\frac{{{worked_row.cleaned_gameplay_energy_wh:.2f}}}{{{usable_fraction:.2f}}}
= {worked_row.nominal_energy_wh:.2f}\\,\\mathrm{{Wh}} \\\\
C_{{\\mathrm{{nom}}}} &= \\frac{{{worked_row.nominal_energy_wh:.2f}}}{{{WORKED_VOLTAGE_V:.0f}}}
= {worked_row.nominal_capacity_ah:.3f}\\,\\mathrm{{Ah}} \\\\
m_{{\\mathrm{{battery}}}} &= \\frac{{{worked_row.nominal_energy_wh:.2f}}}{{{specific_energy:.0f}}}
= {worked_row.battery_mass_kg:.3f}\\,\\mathrm{{kg}}
\\end{{align}}

The peak-power sample gives:
\\begin{{equation}}
I_{{\\mathrm{{battery,peak}}}} = \\frac{{{worked_row.peak_battery_power_w:.2f}}}{{{WORKED_VOLTAGE_V:.0f}}}
= {worked_row.peak_battery_current_a:.3f}\\,\\mathrm{{A}}
\\end{{equation}}

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/worked_example.png}}
  \\caption{{Worked-example time history. The final cumulative energy equals the usable gameplay energy in the official summary.}}
\\end{{figure}}

\\section{{Voltage And Chemistry Results}}
For a fixed game, the cleaned gameplay energy is constant across voltage because the mechanical demand is unchanged. Higher voltage lowers pack current and required amp-hours. Chemistry changes nominal energy, mass, and C-rate checks.

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/voltage_sweep.png}}
  \\caption{{Voltage sweep of the official gameplay-driven battery result.}}
\\end{{figure}}

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/chemistry_comparison_48v.png}}
  \\caption{{Chemistry comparison at the 48 V design point.}}
\\end{{figure}}

\\input{{tables/results_overview.tex}}

\\section{{Verification Findings}}
The main finding is that the current scenarios are not yet electrically comfortable under the present assumptions. The official summary still shows motor peak-current and battery peak C-rate violations.

That is a useful engineering result, not a reporting problem. It means the workflow is exposing the consequence of the current drivetrain and chemistry assumptions in a way a reviewer can check directly.

\\input{{tables/verification_findings.tex}}

\\section{{Assumptions Used}}
The official assumptions used to generate this report are listed below.

\\input{{tables/assumptions.tex}}

\\appendix
\\section{{Official Plot Bundles}}
For convenience, the report also includes the existing official summary plots generated by the battery-sizing script.

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/Game1CharlesPhone_battery_sizing.png}}
  \\caption{{Official battery-sizing plot bundle for Game 1.}}
\\end{{figure}}

\\begin{{figure}}[H]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/Game2CharlesPhone_battery_sizing.png}}
  \\caption{{Official battery-sizing plot bundle for Game 2.}}
\\end{{figure}}

\\end{{document}}
"""
    (REPORT_ROOT / "main.tex").write_text(report_text, encoding="utf-8")


def build_report() -> None:
    _ensure_output_dirs()
    summary = _build_official_outputs()
    cleaning_manifest = _load_cleaning_manifest()
    worked_trace = _load_worked_trace()
    worked_row = summary.loc[
        (summary["game_name"] == WORKED_GAME)
        & (summary["voltage_v"] == WORKED_VOLTAGE_V)
        & (summary["battery_name"] == WORKED_BATTERY)
    ].iloc[0]

    _copy_file(official_workflow.OUTPUT_DIR / "scenario_summary.csv", ARTIFACTS_DIR / "official_scenario_summary.csv")
    _copy_file(official_workflow.OUTPUT_DIR / "scenario_summary.json", ARTIFACTS_DIR / "official_scenario_summary.json")
    _copy_file(official_workflow.INPUT_DIR / "cleaning_manifest.json", ARTIFACTS_DIR / "cleaning_manifest.json")

    _generate_workflow_figure(FIGURES_DIR / "workflow_diagram.png")
    _generate_data_provenance_figure(cleaning_manifest, FIGURES_DIR / "data_provenance.png")
    _generate_signal_cleaning_figure(FIGURES_DIR / "signal_cleaning.png")
    peak_row = _generate_worked_example_figure(worked_trace, FIGURES_DIR / "worked_example.png")
    _generate_voltage_sweep_figure(summary, FIGURES_DIR / "voltage_sweep.png")
    _generate_chemistry_comparison_figure(summary, FIGURES_DIR / "chemistry_comparison_48v.png")
    _copy_existing_official_plots()

    _write_data_provenance_table(cleaning_manifest)
    _write_assumptions_table()
    _write_worked_example_table(worked_row, peak_row)
    _write_results_table(summary)
    _write_findings_table(summary)
    _write_main_tex(summary, worked_row, cleaning_manifest)
    _write_readme()


def main() -> None:
    build_report()
    print(f"Wrote self-contained report package to {REPORT_ROOT.resolve()}")


if __name__ == "__main__":
    main()
