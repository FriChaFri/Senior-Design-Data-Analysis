"""Spec-first analysis derived from gameplay IMU data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import pandas as pd

from imu_pipeline.battery_sizing import (
    MotorOption,
    SignalProcessingAssumptions,
    VehicleAssumptions,
    build_representative_session,
    preprocess_game_csv,
    summarize_motor_requirements,
)
from imu_pipeline.requirements import RequirementSpec, load_requirement_specs
from imu_pipeline.spreadsheet_style import (
    SpreadsheetStyleAssumptions,
    build_battery_power_requirements_table,
    build_motor_power_requirements_table,
    extract_spreadsheet_drive_inputs,
)


@dataclass(frozen=True)
class SpecEvaluation:
    """One spec-row evaluation in the generated report."""

    spec_id: str
    requirement: str
    status: str
    metric_name: str
    target: str
    observed_or_modeled_value: str
    evidence_source: str
    notes: str


def _find_spec(specs: list[RequirementSpec], spec_id: str) -> RequirementSpec:
    for spec in specs:
        if spec.spec_id == spec_id:
            return spec
    raise KeyError(f"Missing spec {spec_id!r} in requirement workbook.")


def _evaluate_specs(
    specs: list[RequirementSpec],
    hardest_game: str,
    motor_rows: pd.DataFrame,
    endurance_rows: pd.DataFrame,
    signal: SignalProcessingAssumptions,
    selected_voltage_v: float,
) -> list[SpecEvaluation]:
    spec_f = _find_spec(specs, "F")
    spec_g = _find_spec(specs, "G")
    spec_h = _find_spec(specs, "H")
    spec_o = _find_spec(specs, "O")

    selected_motor = motor_rows.loc[motor_rows["voltage_v"] == selected_voltage_v].iloc[0]
    battery_48 = endurance_rows.loc[endurance_rows["Voltage"] == selected_voltage_v].iloc[0]

    return [
        SpecEvaluation(
            spec_id="F",
            requirement=spec_f.description,
            status="partial-pass" if selected_motor["peak_acceleration_m_s2"] >= 2.85 else "not-demonstrated",
            metric_name="Peak clipped gameplay acceleration",
            target=">= 2.85 m/s^2 average from rest over first 5 m",
            observed_or_modeled_value=f"{selected_motor['peak_acceleration_m_s2']:.2f} m/s^2",
            evidence_source=hardest_game,
            notes=(
                "Current IMU workflow demonstrates the target acceleration magnitude is present in gameplay, "
                "but it does not reconstruct a standardized rest-to-5 m sprint. Treat this as lower-bound evidence."
            ),
        ),
        SpecEvaluation(
            spec_id="G",
            requirement=spec_g.description,
            status="modeled-pass" if selected_motor["rated_output_speed_mph"] >= 11.0 else "modeled-fail",
            metric_name="Rated motor output speed",
            target=">= 11.0 mph",
            observed_or_modeled_value=(
                f"rated={selected_motor['rated_output_speed_mph']:.2f} mph; "
                f"observed_trace_cap={selected_motor['peak_speed_mph']:.2f} mph"
            ),
            evidence_source=hardest_game,
            notes=(
                "Rated speed comes from the selected motor/gearing model. "
                "Observed gameplay speed is capped by the analysis v_max setting, so it is not independent proof."
            ),
        ),
        SpecEvaluation(
            spec_id="H",
            requirement=spec_h.description,
            status="not-evaluated",
            metric_name="Turning-rate evidence",
            target=">= 200 deg/s within 0.50 s",
            observed_or_modeled_value="Not currently derived from the existing IMU pipeline",
            evidence_source="Needs+Specs workbook",
            notes=(
                "The current repo infers forward motion well enough for longitudinal sizing, "
                "but it does not yet compute court-valid yaw-rate compliance for this spec."
            ),
        ),
        SpecEvaluation(
            spec_id="O",
            requirement=spec_o.description,
            status="design-input",
            metric_name="2-hour endurance requirement",
            target="Operate for >= 2.0 h",
            observed_or_modeled_value=(
                f"{battery_48['Required energy (Wh)']:.2f} Wh worst-case energy, "
                f"{battery_48['Required lithium capacity @ 80% usable (Ah)']:.2f} Ah at {int(selected_voltage_v)} V"
            ),
            evidence_source=hardest_game,
            notes=(
                "This row translates the hardest non-collision gameplay trace into a 2-hour battery requirement. "
                "It is a sizing target, not a pass/fail result against a built battery pack."
            ),
        ),
    ]


def _write_markdown_report(
    output_dir: Path,
    specs: list[RequirementSpec],
    evaluations: list[SpecEvaluation],
    hardest_game: str,
    hardest_energy_wh: float,
    selected_voltage_v: float,
    battery_table: pd.DataFrame,
    collision_manifest: dict[str, dict],
) -> None:
    game_manifest = collision_manifest.get(hardest_game, {})
    lines = [
        "# Spec-First Gameplay Battery Analysis",
        "",
        f"- Authoritative workbook: `Needs+Specs.xlsx`",
        f"- Hardest gameplay-sizing session: `{hardest_game}`",
        f"- Worst-case 2-hour energy basis: `{hardest_energy_wh:.2f} Wh`",
        f"- Primary design voltage shown below: `{int(selected_voltage_v)} V`",
        "",
        "## Collision-Trimmed Gameplay Basis",
        "",
        f"- Baseline cleaned files in `data/processed/clean_games` remain unchanged.",
        f"- Gameplay sizing files are derived in `data/processed/clean_games_gameplay`.",
        f"- Collision windows removed for `{hardest_game}`: `{len(game_manifest.get('collision_windows', []))}`",
        "",
        "## Spec Coverage",
        "",
        "| Spec | Status | Metric | Target | Observed / modeled | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for evaluation in evaluations:
        lines.append(
            f"| {evaluation.spec_id} | {evaluation.status} | {evaluation.metric_name} | "
            f"{evaluation.target} | {evaluation.observed_or_modeled_value} | {evaluation.notes} |"
        )

    lines.extend(
        [
            "",
            "## Endurance Translation",
            "",
            "| Voltage | Worst-case energy (Wh) | Lithium 80% Ah | Lead-acid 50% Ah | Peak current (A) |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for _, row in battery_table.iterrows():
        lines.append(
            f"| {int(row['Voltage'])} | {row['Required energy (Wh)']:.2f} | "
            f"{row['Required lithium capacity @ 80% usable (Ah)']:.2f} | "
            f"{row['Required lead-acid capacity @ 50% usable (Ah)']:.2f} | "
            f"{row['Peak pack current (A)']:.2f} |"
        )

    (output_dir / "spec_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_spec_report_pipeline(
    input_dir: str | Path,
    output_dir: str | Path,
    workbook_path: str | Path,
    collision_manifest_path: str | Path,
    signal: SignalProcessingAssumptions,
    vehicle: VehicleAssumptions,
    motor: MotorOption,
    workbook_assumptions: SpreadsheetStyleAssumptions,
    voltage_candidates_v: list[float],
    selected_voltage_v: float = 48.0,
) -> dict[str, pd.DataFrame | str]:
    """Generate a spec-first report tied to the Needs+Specs workbook."""

    input_root = Path(input_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    specs = load_requirement_specs(workbook_path)
    collision_manifest = json.loads(Path(collision_manifest_path).read_text(encoding="utf-8"))

    session_rows: list[dict[str, float | str]] = []
    processed_by_game: dict[str, tuple] = {}
    for csv_path in sorted(input_root.glob("*.csv")):
        processed = preprocess_game_csv(csv_path, signal, gravity_m_s2=vehicle.gravity_m_s2)
        session = build_representative_session(processed, signal)
        motor_rows = pd.DataFrame(
            result.to_row()
            for result in summarize_motor_requirements(
                processed_signal=processed,
                session_frame=session,
                vehicle=vehicle,
                motor=motor,
                voltage_candidates_v=voltage_candidates_v,
                project_peak_torque_per_wheel_nm=39.6,
                project_speed_target_mph=11.0,
            )
        )
        session_energy_wh = float(motor_rows["session_energy_wh"].iloc[0])
        session_rows.append({"game_name": processed.game_name, "session_energy_wh": session_energy_wh})
        processed_by_game[processed.game_name] = (processed, session, motor_rows)

    hardest_game = max(session_rows, key=lambda row: row["session_energy_wh"])["game_name"]
    hardest_energy_wh = max(row["session_energy_wh"] for row in session_rows)
    processed, session, motor_summary = processed_by_game[hardest_game]

    drive_inputs = extract_spreadsheet_drive_inputs(processed, session, workbook_assumptions)
    drive_inputs = [row for row in drive_inputs if row.gear_ratio == motor.gear_ratio]
    motor_power = build_motor_power_requirements_table(drive_inputs, workbook_assumptions)
    battery_power = build_battery_power_requirements_table(motor_power, workbook_assumptions)
    battery_power = battery_power.loc[battery_power["game_name"] == hardest_game].sort_values("Voltage").reset_index(drop=True)
    endurance_rows = motor_summary.loc[:, ["voltage_v", "session_energy_wh", "peak_pack_current_a"]].copy()
    endurance_rows["Required lithium capacity @ 80% usable (Ah)"] = (
        endurance_rows["session_energy_wh"] / endurance_rows["voltage_v"] / workbook_assumptions.lithium_usable_fraction
    )
    endurance_rows["Required lead-acid capacity @ 50% usable (Ah)"] = (
        endurance_rows["session_energy_wh"] / endurance_rows["voltage_v"] / workbook_assumptions.lead_acid_usable_fraction
    )
    endurance_rows = endurance_rows.rename(
        columns={
            "voltage_v": "Voltage",
            "session_energy_wh": "Required energy (Wh)",
            "peak_pack_current_a": "Peak pack current (A)",
        }
    ).sort_values("Voltage").reset_index(drop=True)

    evaluations = _evaluate_specs(
        specs,
        hardest_game=hardest_game,
        motor_rows=motor_summary,
        endurance_rows=endurance_rows,
        signal=signal,
        selected_voltage_v=selected_voltage_v,
    )

    spec_table = pd.DataFrame(asdict(row) for row in evaluations)
    session_table = pd.DataFrame(session_rows).sort_values("session_energy_wh", ascending=False).reset_index(drop=True)
    spec_table.to_csv(output_root / "spec_compliance.csv", index=False)
    session_table.to_csv(output_root / "gameplay_session_ranking.csv", index=False)
    motor_summary.to_csv(output_root / "hardest_game_motor_summary.csv", index=False)
    endurance_rows.to_csv(output_root / "hardest_game_battery_requirements.csv", index=False)
    battery_power.to_csv(output_root / "hardest_game_workbook_battery_reference.csv", index=False)

    payload = {
        "authoritative_specs": [asdict(spec) for spec in specs if spec.spec_id in {"F", "G", "H", "O"}],
        "hardest_game": hardest_game,
        "session_ranking": session_rows,
        "spec_compliance": [asdict(row) for row in evaluations],
        "hardest_game_motor_summary": motor_summary.to_dict(orient="records"),
        "hardest_game_battery_requirements": endurance_rows.to_dict(orient="records"),
        "hardest_game_workbook_battery_reference": battery_power.to_dict(orient="records"),
    }
    (output_root / "spec_report_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _write_markdown_report(
        output_dir=output_root,
        specs=specs,
        evaluations=evaluations,
        hardest_game=hardest_game,
        hardest_energy_wh=hardest_energy_wh,
        selected_voltage_v=selected_voltage_v,
        battery_table=endurance_rows,
        collision_manifest=collision_manifest,
    )
    return {
        "spec_compliance": spec_table,
        "session_ranking": session_table,
        "motor_summary": motor_summary,
        "battery_requirements": battery_power,
        "hardest_game": hardest_game,
    }
