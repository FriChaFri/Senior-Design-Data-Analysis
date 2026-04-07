"""Tools for loading, organizing, and analyzing phone IMU datasets."""

from imu_pipeline.battery_sizing import (
    BatteryOption,
    BatterySizingResult,
    MotorOption,
    MotorRequirementResult,
    SignalProcessingAssumptions,
    VehicleAssumptions,
    build_representative_session,
    compute_longitudinal_dynamics,
    integrate_energy_wh,
    integrate_speed,
    iterate_battery_mass,
    preprocess_game_csv,
    print_console_summary,
    run_battery_sizing_pipeline,
    summarize_motor_requirements,
)
from imu_pipeline.gameplay_dataset import (
    CollisionWindowSummary,
    build_collision_trimmed_game,
    derive_gameplay_dataset,
    detect_collision_windows,
)
from imu_pipeline.requirements import RequirementSpec, load_requirement_specs
from imu_pipeline.spec_report import run_spec_report_pipeline
from imu_pipeline.spreadsheet_style import (
    SpreadsheetDriveInput,
    SpreadsheetStyleAssumptions,
    run_spreadsheet_style_pipeline,
)

__all__ = [
    "BatteryOption",
    "BatterySizingResult",
    "CollisionWindowSummary",
    "MotorOption",
    "MotorRequirementResult",
    "RequirementSpec",
    "SignalProcessingAssumptions",
    "SpreadsheetDriveInput",
    "SpreadsheetStyleAssumptions",
    "VehicleAssumptions",
    "build_collision_trimmed_game",
    "build_representative_session",
    "compute_longitudinal_dynamics",
    "derive_gameplay_dataset",
    "detect_collision_windows",
    "integrate_energy_wh",
    "integrate_speed",
    "iterate_battery_mass",
    "load_requirement_specs",
    "preprocess_game_csv",
    "print_console_summary",
    "run_battery_sizing_pipeline",
    "run_spec_report_pipeline",
    "run_spreadsheet_style_pipeline",
    "summarize_motor_requirements",
]
