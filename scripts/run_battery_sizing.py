#!/usr/bin/env python3
"""Run the official gameplay-driven battery sizing workflow."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from imu_pipeline.battery_sizing import (
    BatteryOption,
    MotorOption,
    SignalProcessingAssumptions,
    VehicleAssumptions,
    print_console_summary,
    run_battery_sizing_pipeline,
)
from imu_pipeline.game_processing import build_clean_games_dataset


INPUT_DIR = Path("data/processed/clean_games")
OUTPUT_DIR = Path("data/processed/battery_sizing")
VOLTAGE_CANDIDATES_V = [24.0, 36.0, 48.0, 60.0, 72.0]

VEHICLE = VehicleAssumptions(
    system_mass_kg=105.0,
    pack_voltage_v=48.0,
    c_rr=0.002,
    air_density_kg_m3=1.225,
    cd_area_m2=0.45,
    grade_rad=0.0,
    aux_power_w=40.0,
    equiv_rotational_inertia_kg_m2=0.0,
    wheel_rotational_inertia_kg_m2_per_wheel=0.2,
    wheel_track_m=0.68,
    yaw_inertia_kg_m2=10.0,
    initial_battery_mass_guess_kg=5.0,
    convergence_tol_kg=0.05,
    max_iterations=20,
)

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

MOTOR = MotorOption(
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

BATTERIES = [
    BatteryOption(
        name="nmc_high_rate",
        specific_energy_wh_per_kg=160.0,
        usable_fraction=0.90,
        continuous_c=3.0,
        peak_c=5.0,
    ),
    BatteryOption(
        name="lifepo4_high_rate",
        specific_energy_wh_per_kg=110.0,
        usable_fraction=0.85,
        continuous_c=2.0,
        peak_c=3.0,
    ),
    BatteryOption(
        name="sla_baseline",
        specific_energy_wh_per_kg=35.0,
        usable_fraction=0.60,
        continuous_c=0.5,
        peak_c=1.0,
    ),
]


def main() -> None:
    build_clean_games_dataset(processed_dir=INPUT_DIR)
    results = run_battery_sizing_pipeline(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        vehicle=VEHICLE,
        signal=SIGNAL,
        motor=MOTOR,
        voltage_candidates_v=VOLTAGE_CANDIDATES_V,
        batteries=BATTERIES,
        write_timeseries=True,
        write_plots=True,
    )
    print_console_summary(results)
    print(f"\nOfficial gameplay battery sizing outputs written to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
