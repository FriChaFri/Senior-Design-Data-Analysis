#!/usr/bin/env python3
"""Run a spreadsheet-faithful analysis path using the gameplay data."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from imu_pipeline.battery_sizing import SignalProcessingAssumptions  # noqa: E402
from imu_pipeline.game_processing import build_clean_games_dataset  # noqa: E402
from imu_pipeline.spreadsheet_style import (  # noqa: E402
    SpreadsheetStyleAssumptions,
    run_spreadsheet_style_pipeline,
)


INPUT_DIR = Path("data/processed/clean_games")
OUTPUT_DIR = Path("data/processed/spreadsheet_style")
REPO_SUMMARY_PATH = Path("data/processed/motor_requirements/motor_requirement_summary.csv")

SIGNAL = SignalProcessingAssumptions(
    resample_hz=100.0,
    winsor_percentile=99.5,
    lowpass_cutoff_hz=0.5,
    lowpass_order=4,
    linear_lowpass_cutoff_hz=1.25,
    yaw_lowpass_cutoff_hz=1.5,
    bias_window_s=8.0,
    v_max_m_s=11.0 * 0.44704,
    representative_minutes=60.0,
    session_hours=2.0,
    max_realistic_accel_m_s2=2.85,
    impact_accel_threshold_m_s2=25.0,
    impact_jerk_threshold_m_s3=120.0,
    impact_padding_s=0.35,
    stationary_accel_threshold_m_s2=0.2,
    stationary_yaw_rate_threshold_rad_s=0.2,
    stationary_hold_s=0.35,
    velocity_decay_tau_s=8.0,
)

SPREADSHEET = SpreadsheetStyleAssumptions(
    rated_speed_rpm=3000.0,
    rated_motor_torque_nm=1.43,
    peak_motor_torque_nm=4.3,
    motor_efficiency=0.85,
    wheel_radius_m=0.3048,
    system_mass_kg=105.0,
    driven_wheels=2,
    session_hours=2.0,
    lead_acid_usable_fraction=0.50,
    lithium_usable_fraction=0.80,
    gear_ratios=(20.0, 16.0, 25.0),
    voltage_candidates_v=(12.0, 24.0, 36.0, 48.0),
)


def main() -> None:
    build_clean_games_dataset(processed_dir=INPUT_DIR)
    results = run_spreadsheet_style_pipeline(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        signal=SIGNAL,
        assumptions=SPREADSHEET,
        repo_summary_path=REPO_SUMMARY_PATH,
    )

    print("Spreadsheet-style motor power requirements")
    print(results["motor_power"].to_string(index=False))
    if not results["comparison"].empty:
        print("\nComparison to motion-integrated motor summary")
        print(results["comparison"].to_string(index=False))
    print(f"\nWrote spreadsheet-style outputs to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
