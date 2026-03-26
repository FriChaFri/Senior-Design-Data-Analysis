import math

import pandas as pd
import pytest

from imu_pipeline.spreadsheet_style import (
    SpreadsheetDriveInput,
    SpreadsheetStyleAssumptions,
    build_battery_power_requirements_table,
    build_motor_power_requirements_table,
    extract_spreadsheet_drive_inputs,
)


def test_workbook_16_to_1_formulas_match_original_sheet_values() -> None:
    assumptions = SpreadsheetStyleAssumptions(gear_ratios=(16.0,), voltage_candidates_v=(12.0, 24.0, 36.0, 48.0))
    drive_inputs = [
        SpreadsheetDriveInput(
            game_name="Workbook",
            gear_ratio=16.0,
            observed_peak_speed_m_s=4.95,
            observed_peak_output_rpm=155.0,
            needed_motor_rpm_max=2480.0,
            continuous_motor_torque_nm=0.8125,
            positive_accel_sample_count=1,
        )
    ]

    motor_power = build_motor_power_requirements_table(drive_inputs, assumptions)
    battery = build_battery_power_requirements_table(motor_power, assumptions)

    motor_row = motor_power.iloc[0]
    battery_48v = battery.loc[battery["Voltage"] == 48.0].iloc[0]

    assert motor_row["Angular Velocity"] == pytest.approx(259.7049927, rel=1e-7)
    assert motor_row["Power Mechanical (W)"] == pytest.approx(211.0103066, rel=1e-7)
    assert motor_row["Rated Power Electrical"] == pytest.approx(248.2474195, rel=1e-7)
    assert motor_row["Peak Power Electrical"] == pytest.approx(1313.8017278, rel=1e-7)
    assert battery_48v["Expected Cold Crank Current"] == pytest.approx(54.74173866, rel=1e-7)
    assert battery_48v["Expected Rated Current"] == pytest.approx(10.34364248, rel=1e-7)
    assert battery_48v["Ah needed lithium ion battery (80%)"] == pytest.approx(25.8591062, rel=1e-7)
    assert battery_48v["Expected Watt Hours"] == pytest.approx(992.989678, rel=1e-7)


def test_data_adapter_uses_mean_positive_inertial_torque_and_caps_rpm() -> None:
    assumptions = SpreadsheetStyleAssumptions(gear_ratios=(20.0,))
    session = pd.DataFrame(
        {
            "forward_accel_m_s2": [1.0, 2.0, -1.0, 0.0],
            "surrogate_speed_m_s": [0.0, 3.0, 5.0, 4.0],
        }
    )

    processed = type("Processed", (), {"game_name": "Synthetic"})()
    drive_input = extract_spreadsheet_drive_inputs(processed, session, assumptions)[0]

    expected_peak_output_rpm = 5.0 * 60.0 / (2.0 * math.pi * assumptions.wheel_radius_m)
    expected_mean_torque = (
        ((1.0 * assumptions.system_mass_kg * assumptions.wheel_radius_m) / (assumptions.driven_wheels * 20.0))
        + ((2.0 * assumptions.system_mass_kg * assumptions.wheel_radius_m) / (assumptions.driven_wheels * 20.0))
    ) / 2.0

    assert drive_input.observed_peak_output_rpm == pytest.approx(expected_peak_output_rpm)
    assert drive_input.continuous_motor_torque_nm == pytest.approx(expected_mean_torque)
    assert drive_input.needed_motor_rpm_max == pytest.approx(3000.0)
    assert drive_input.positive_accel_sample_count == 2
