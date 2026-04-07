#!/usr/bin/env python3
"""Generate a reference-only spec-first report tied to the Needs+Specs workbook."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from imu_pipeline.battery_sizing import MotorOption, SignalProcessingAssumptions, VehicleAssumptions  # noqa: E402
from imu_pipeline.game_processing import build_clean_games_dataset  # noqa: E402
from imu_pipeline.gameplay_dataset import derive_gameplay_dataset  # noqa: E402
from imu_pipeline.spec_report import run_spec_report_pipeline  # noqa: E402
from imu_pipeline.spreadsheet_style import SpreadsheetStyleAssumptions  # noqa: E402


INPUT_DIR = Path("data/processed/clean_games_gameplay")
OUTPUT_DIR = Path("data/processed/spec_report")
WORKBOOK_PATH = Path("Needs+Specs.xlsx")
COLLISION_MANIFEST_PATH = Path("data/processed/clean_games_gameplay/collision_manifest.json")

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

VEHICLE = VehicleAssumptions(
    system_mass_kg=105.0,
    pack_voltage_v=48.0,
    c_rr=0.002,
    air_density_kg_m3=1.225,
    cd_area_m2=0.45,
    grade_rad=0.0,
    aux_power_w=40.0,
    wheel_rotational_inertia_kg_m2_per_wheel=0.2,
    wheel_track_m=0.68,
    yaw_inertia_kg_m2=10.0,
)

SELECTED_MOTOR = MotorOption(
    name="450w_bldc_planetary_16to1",
    motor_mass_kg=3.5,
    driven_wheels=2,
    wheel_radius_m=11.75 * 0.0254,
    gear_ratio=16.0,
    gear_efficiency=0.90,
    torque_constant_nm_per_a=1.43 / 11.72,
    continuous_current_a=11.72,
    peak_current_a=4.30 / (1.43 / 11.72),
    motor_efficiency=0.85,
    rated_torque_nm=1.43,
    peak_torque_nm=4.30,
    rated_speed_rpm=3000.0,
)

WORKBOOK_ASSUMPTIONS = SpreadsheetStyleAssumptions(
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
    gear_ratios=(16.0,),
    voltage_candidates_v=(24.0, 36.0, 48.0, 60.0, 72.0),
)


def main() -> None:
    build_clean_games_dataset(processed_dir=Path("data/processed/clean_games"))
    derive_gameplay_dataset(
        input_dir=Path("data/processed/clean_games"),
        output_dir=INPUT_DIR,
        magnitude_threshold_m_s2=40.0,
        cluster_gap_s=0.5,
        padding_s=0.75,
    )
    results = run_spec_report_pipeline(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        workbook_path=WORKBOOK_PATH,
        collision_manifest_path=COLLISION_MANIFEST_PATH,
        signal=SIGNAL,
        vehicle=VEHICLE,
        motor=SELECTED_MOTOR,
        workbook_assumptions=WORKBOOK_ASSUMPTIONS,
        voltage_candidates_v=[24.0, 36.0, 48.0, 60.0, 72.0],
        selected_voltage_v=48.0,
    )

    print("Hardest gameplay session ranking")
    print(results["session_ranking"].to_string(index=False))
    print("\nSpec compliance summary")
    print(results["spec_compliance"].to_string(index=False))
    print(f"\nWrote reference-only spec-first outputs to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
