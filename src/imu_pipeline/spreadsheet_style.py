"""Spreadsheet-faithful motor and battery sizing driven by gameplay data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from imu_pipeline.battery_sizing import (
    ProcessedGameSignal,
    SignalProcessingAssumptions,
    build_representative_session,
    preprocess_game_csv,
)


MPS_TO_MPH = 2.236936


@dataclass(frozen=True)
class SpreadsheetStyleAssumptions:
    """Constants copied from the workbook unless data adaptation is required."""

    rated_speed_rpm: float = 3000.0
    rated_motor_torque_nm: float = 1.43
    peak_motor_torque_nm: float = 4.3
    motor_efficiency: float = 0.85
    wheel_radius_m: float = 0.3048
    system_mass_kg: float = 105.0
    driven_wheels: int = 2
    session_hours: float = 2.0
    lead_acid_usable_fraction: float = 0.50
    lithium_usable_fraction: float = 0.80
    gear_ratios: tuple[float, ...] = (20.0, 16.0, 25.0)
    voltage_candidates_v: tuple[float, ...] = (12.0, 24.0, 36.0, 48.0)


@dataclass(frozen=True)
class SpreadsheetDriveInput:
    """Data-adapted inputs required by the workbook formulas."""

    game_name: str
    gear_ratio: float
    observed_peak_speed_m_s: float
    observed_peak_output_rpm: float
    needed_motor_rpm_max: float
    continuous_motor_torque_nm: float
    positive_accel_sample_count: int

    def to_row(self) -> dict[str, float | int | str]:
        return asdict(self)


def _output_rpm_from_speed(speed_m_s: float, wheel_radius_m: float) -> float:
    return speed_m_s * 60.0 / (2.0 * math.pi * wheel_radius_m)


def _angular_velocity_from_rpm(rpm: float) -> float:
    return ((2.0 * math.pi) / 60.0) * rpm


def _require_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def extract_spreadsheet_drive_inputs(
    processed_signal: ProcessedGameSignal,
    session_frame: pd.DataFrame,
    assumptions: SpreadsheetStyleAssumptions,
) -> list[SpreadsheetDriveInput]:
    """Collapse a gameplay trace into the workbook's speed and torque inputs.

    The workbook cannot consume raw IMU data directly. The minimal adaptation is:
    - use the clipped gameplay trace's peak surrogate speed as the required wheel speed
    - use the mean positive inertial motor torque as the workbook's continuous torque input
    """

    _require_columns(session_frame, ("forward_accel_m_s2", "surrogate_speed_m_s"))

    peak_speed_m_s = float(session_frame["surrogate_speed_m_s"].max())
    observed_peak_output_rpm = _output_rpm_from_speed(peak_speed_m_s, assumptions.wheel_radius_m)
    positive_accel = np.clip(session_frame["forward_accel_m_s2"].to_numpy(dtype=float), 0.0, None)
    wheel_torque_total_nm = positive_accel * assumptions.system_mass_kg * assumptions.wheel_radius_m
    positive_sample_count = int(np.count_nonzero(positive_accel > 0.0))

    rows: list[SpreadsheetDriveInput] = []
    for gear_ratio in assumptions.gear_ratios:
        motor_torque_samples = wheel_torque_total_nm / (assumptions.driven_wheels * gear_ratio)
        positive_torque = motor_torque_samples[motor_torque_samples > 0.0]
        continuous_torque_nm = float(positive_torque.mean()) if positive_torque.size else 0.0
        needed_motor_rpm_max = min(
            assumptions.rated_speed_rpm,
            observed_peak_output_rpm * gear_ratio,
        )
        rows.append(
            SpreadsheetDriveInput(
                game_name=processed_signal.game_name,
                gear_ratio=gear_ratio,
                observed_peak_speed_m_s=peak_speed_m_s,
                observed_peak_output_rpm=observed_peak_output_rpm,
                needed_motor_rpm_max=needed_motor_rpm_max,
                continuous_motor_torque_nm=continuous_torque_nm,
                positive_accel_sample_count=positive_sample_count,
            )
        )
    return rows


def build_motor_capability_table(assumptions: SpreadsheetStyleAssumptions) -> pd.DataFrame:
    """Return sheet 1: motor max speed and torque."""

    rows = []
    for gear_ratio in assumptions.gear_ratios:
        expected_output_rpm = assumptions.rated_speed_rpm / gear_ratio
        max_velocity_m_s = expected_output_rpm * 2.0 * math.pi * assumptions.wheel_radius_m / 60.0
        rows.append(
            {
                "RPM Max": assumptions.rated_speed_rpm,
                "Gear Ratio": gear_ratio,
                "Expected RPM Output": expected_output_rpm,
                "Max Velocity (m/s)": max_velocity_m_s,
                "Max Velocity (mph)": max_velocity_m_s * MPS_TO_MPH,
                "Max regular torque (Nm)": assumptions.rated_motor_torque_nm * gear_ratio,
                "Max Peak Torque (Nm)": assumptions.peak_motor_torque_nm * gear_ratio,
                "Max Acceleration": np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_motor_power_requirements_table(
    drive_inputs: list[SpreadsheetDriveInput],
    assumptions: SpreadsheetStyleAssumptions,
) -> pd.DataFrame:
    """Return the normalized version of sheet 2."""

    rows = []
    for drive_input in drive_inputs:
        expected_output_rpm = assumptions.rated_speed_rpm / drive_input.gear_ratio
        angular_velocity_rad_s = _angular_velocity_from_rpm(drive_input.needed_motor_rpm_max)
        mechanical_power_w = drive_input.continuous_motor_torque_nm * angular_velocity_rad_s
        rated_power_electrical_w = (
            mechanical_power_w / assumptions.motor_efficiency if assumptions.motor_efficiency else np.nan
        )
        peak_power_electrical_w = (
            assumptions.peak_motor_torque_nm * angular_velocity_rad_s / assumptions.motor_efficiency
            if assumptions.motor_efficiency
            else np.nan
        )
        rows.append(
            {
                "game_name": drive_input.game_name,
                "RPM Max": assumptions.rated_speed_rpm,
                "Gear Ratio": drive_input.gear_ratio,
                "Expected RPM Output": expected_output_rpm,
                "Needed RPM max": drive_input.needed_motor_rpm_max,
                "radius (m)": assumptions.wheel_radius_m,
                "Torque": drive_input.continuous_motor_torque_nm,
                "Angular Velocity": angular_velocity_rad_s,
                "Power Mechanical (W)": mechanical_power_w,
                "Motor Efficiency": assumptions.motor_efficiency,
                "Rated Power Electrical": rated_power_electrical_w,
                "Peak Power Electrical": peak_power_electrical_w,
                "Observed Peak Speed (m/s)": drive_input.observed_peak_speed_m_s,
                "Observed Peak Output RPM": drive_input.observed_peak_output_rpm,
                "Positive Accel Samples": drive_input.positive_accel_sample_count,
            }
        )
    return pd.DataFrame(rows)


def build_battery_power_requirements_table(
    motor_power_table: pd.DataFrame,
    assumptions: SpreadsheetStyleAssumptions,
) -> pd.DataFrame:
    """Return the normalized version of sheet 3."""

    rows = []
    for row in motor_power_table.to_dict(orient="records"):
        peak_power_both_w = 2.0 * row["Peak Power Electrical"]
        rated_power_both_w = 2.0 * row["Rated Power Electrical"]
        expected_watt_hours = rated_power_both_w * assumptions.session_hours
        for voltage_v in assumptions.voltage_candidates_v:
            expected_cold_crank_current_a = peak_power_both_w / voltage_v
            expected_rated_current_a = rated_power_both_w / voltage_v
            rows.append(
                {
                    "game_name": row["game_name"],
                    "Gear Ratio": row["Gear Ratio"],
                    "Voltage": voltage_v,
                    "Peak Power Electrical (both motor)": peak_power_both_w,
                    "Power Electrical Rated (both motor)": rated_power_both_w,
                    "Expected Cold Crank Current": expected_cold_crank_current_a,
                    "Expected Rated Current": expected_rated_current_a,
                    "Ah needed lead acid battery (50%)": (
                        expected_rated_current_a
                        * assumptions.session_hours
                        / assumptions.lead_acid_usable_fraction
                    ),
                    "Ah needed lithium ion battery (80%)": (
                        expected_rated_current_a
                        * assumptions.session_hours
                        / assumptions.lithium_usable_fraction
                    ),
                    "Expected Watt Hours": expected_watt_hours,
                    "Expected Ah From Wh (100%)": expected_watt_hours / voltage_v,
                }
            )
    return pd.DataFrame(rows)


def build_comparison_to_repo_table(
    battery_power_table: pd.DataFrame,
    repo_summary: pd.DataFrame,
    selected_gear_ratio: float = 16.0,
    lithium_usable_fraction: float = 0.80,
) -> pd.DataFrame:
    """Compare the spreadsheet-style output against the existing repo summary."""

    spreadsheet_subset = battery_power_table.loc[
        battery_power_table["Gear Ratio"] == selected_gear_ratio
    ].copy()
    repo_subset = repo_summary.rename(
        columns={
            "voltage_v": "Voltage",
            "session_energy_wh": "repo_session_energy_wh",
            "average_electrical_power_w": "repo_average_electrical_power_w",
            "peak_pack_current_a": "repo_peak_pack_current_a",
            "peak_electrical_power_w": "repo_peak_electrical_power_w",
        }
    )[
        [
            "game_name",
            "Voltage",
            "repo_session_energy_wh",
            "repo_average_electrical_power_w",
            "repo_peak_pack_current_a",
            "repo_peak_electrical_power_w",
        ]
    ]
    comparison = spreadsheet_subset.merge(repo_subset, on=["game_name", "Voltage"], how="inner")
    comparison["spreadsheet_expected_wh_2h"] = comparison["Expected Watt Hours"]
    comparison["repo_lithium_ah_80pct"] = (
        comparison["repo_session_energy_wh"] / comparison["Voltage"] / lithium_usable_fraction
    )
    comparison["repo_average_pack_current_a"] = (
        comparison["repo_average_electrical_power_w"] / comparison["Voltage"]
    )
    comparison["energy_ratio_spreadsheet_to_repo"] = (
        comparison["spreadsheet_expected_wh_2h"] / comparison["repo_session_energy_wh"]
    )
    comparison["peak_current_ratio_spreadsheet_to_repo"] = (
        comparison["Expected Cold Crank Current"] / comparison["repo_peak_pack_current_a"]
    )
    comparison["rated_current_ratio_spreadsheet_to_repo_average"] = (
        comparison["Expected Rated Current"] / comparison["repo_average_pack_current_a"]
    )
    return comparison.sort_values(["game_name", "Voltage"]).reset_index(drop=True)


def _sheet_slug(label: str) -> str:
    return label.replace(" ", "_").replace("/", "_").lower()


def _write_workbook_like_csvs(
    output_dir: Path,
    capability_table: pd.DataFrame,
    motor_power_table: pd.DataFrame,
    battery_power_table: pd.DataFrame,
) -> None:
    workbook_dir = output_dir / "workbook_like"
    workbook_dir.mkdir(parents=True, exist_ok=True)

    capability_table.to_csv(workbook_dir / "sheet1_motor_max_speed_and_torque.csv", index=False)

    for game_name, game_motor in motor_power_table.groupby("game_name"):
        game_battery = battery_power_table.loc[battery_power_table["game_name"] == game_name].copy()

        game_motor.to_csv(
            workbook_dir / f"{_sheet_slug(game_name)}_sheet2_motor_power_requirements.csv",
            index=False,
        )
        game_battery.to_csv(
            workbook_dir / f"{_sheet_slug(game_name)}_sheet3_battery_power_requirements.csv",
            index=False,
        )


def _write_summary_payload(
    output_dir: Path,
    assumptions: SpreadsheetStyleAssumptions,
    drive_inputs: list[SpreadsheetDriveInput],
    capability_table: pd.DataFrame,
    motor_power_table: pd.DataFrame,
    battery_power_table: pd.DataFrame,
    comparison_table: pd.DataFrame,
) -> None:
    payload = {
        "assumptions": asdict(assumptions),
        "adapter_notes": [
            "The workbook is copied as-is once it has a continuous torque input and a required max wheel RPM.",
            "Observed peak wheel RPM comes from the clipped surrogate speed trace.",
            "Continuous torque comes from the mean positive inertial motor torque implied by the gameplay trace.",
            "Battery sizing follows the workbook's constant-power-for-two-hours method rather than time-series integration.",
        ],
        "drive_inputs": [input_row.to_row() for input_row in drive_inputs],
        "motor_capability": capability_table.to_dict(orient="records"),
        "motor_power_requirements": motor_power_table.to_dict(orient="records"),
        "battery_power_requirements": battery_power_table.to_dict(orient="records"),
        "comparison_to_repo": comparison_table.to_dict(orient="records"),
    }
    (output_dir / "spreadsheet_style_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _write_report(output_dir: Path, comparison_table: pd.DataFrame) -> None:
    lines = [
        "# Spreadsheet-Style Data-Driven Comparison",
        "",
        "This report copies the workbook's solution path and only adapts the inputs needed to",
        "feed it from the gameplay data.",
        "",
        "## Adapter Rules",
        "",
        "- Peak wheel speed comes from the clipped surrogate-speed trace.",
        "- Continuous torque is the mean positive inertial motor torque per motor.",
        "- Peak current uses the workbook's separate peak-torque check.",
        "- Battery sizing stays constant-power for 2 hours, matching the workbook.",
        "",
        "## Key Comparison Against The Motion-Integrated Sizing Model",
        "",
    ]

    for row in comparison_table.to_dict(orient="records"):
        lines.extend(
            [
                f"### {row['game_name']} at {int(row['Voltage'])} V",
                "",
                f"- Spreadsheet-style expected energy: `{row['spreadsheet_expected_wh_2h']:.2f} Wh`",
                f"- Repo motion-integrated energy: `{row['repo_session_energy_wh']:.2f} Wh`",
                f"- Energy ratio: `{row['energy_ratio_spreadsheet_to_repo']:.2f}x`",
                f"- Spreadsheet peak current: `{row['Expected Cold Crank Current']:.2f} A`",
                f"- Repo peak current: `{row['repo_peak_pack_current_a']:.2f} A`",
                f"- Spreadsheet rated current: `{row['Expected Rated Current']:.2f} A`",
                f"- Repo average pack current: `{row['repo_average_pack_current_a']:.2f} A`",
                "",
            ]
        )

    (output_dir / "comparison_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_spreadsheet_style_pipeline(
    input_dir: str | Path,
    output_dir: str | Path,
    signal: SignalProcessingAssumptions,
    assumptions: SpreadsheetStyleAssumptions,
    repo_summary_path: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the workbook-faithful pipeline across all cleaned games."""

    input_root = Path(input_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    drive_inputs: list[SpreadsheetDriveInput] = []
    for csv_path in sorted(input_root.glob("*.csv")):
        processed = preprocess_game_csv(csv_path, signal)
        session_frame = build_representative_session(processed, signal)
        drive_inputs.extend(extract_spreadsheet_drive_inputs(processed, session_frame, assumptions))

    capability_table = build_motor_capability_table(assumptions)
    drive_input_table = pd.DataFrame([row.to_row() for row in drive_inputs]).sort_values(
        ["game_name", "gear_ratio"]
    )
    motor_power_table = build_motor_power_requirements_table(drive_inputs, assumptions).sort_values(
        ["game_name", "Gear Ratio"]
    )
    battery_power_table = build_battery_power_requirements_table(
        motor_power_table,
        assumptions,
    ).sort_values(["game_name", "Gear Ratio", "Voltage"])

    drive_input_table.to_csv(output_root / "drive_inputs.csv", index=False)
    capability_table.to_csv(output_root / "motor_max_speed_and_torque.csv", index=False)
    motor_power_table.to_csv(output_root / "motor_power_requirements.csv", index=False)
    battery_power_table.to_csv(output_root / "battery_power_requirements.csv", index=False)
    _write_workbook_like_csvs(output_root, capability_table, motor_power_table, battery_power_table)

    comparison_table = pd.DataFrame()
    if repo_summary_path is not None and Path(repo_summary_path).exists():
        repo_summary = pd.read_csv(repo_summary_path)
        comparison_table = build_comparison_to_repo_table(
            battery_power_table,
            repo_summary,
            selected_gear_ratio=16.0,
            lithium_usable_fraction=assumptions.lithium_usable_fraction,
        )
        comparison_table.to_csv(output_root / "comparison_to_repo.csv", index=False)
        _write_report(output_root, comparison_table)

    _write_summary_payload(
        output_root,
        assumptions,
        drive_inputs,
        capability_table,
        motor_power_table,
        battery_power_table,
        comparison_table,
    )

    return {
        "drive_inputs": drive_input_table,
        "motor_capability": capability_table,
        "motor_power": motor_power_table,
        "battery_power": battery_power_table,
        "comparison": comparison_table,
    }
