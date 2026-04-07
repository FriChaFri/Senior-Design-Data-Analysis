#!/usr/bin/env python3
"""Generate review plots for the planar, yaw-aware propulsion pipeline."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys

import matplotlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from imu_pipeline.battery_sizing import (  # noqa: E402
    GRAVITY_COLUMNS,
    GYRO_COLUMNS,
    USER_ACCEL_COLUMNS,
    SignalProcessingAssumptions,
    VehicleAssumptions,
    _centered_rolling_median,
    _impact_mask,
    _integrate_planar_velocity,
    _interpolate_masked,
    _lowpass,
    _project_along_velocity,
    _uniform_resample,
    _winsorize,
    align_vectors_to_average_gravity,
)
from imu_pipeline.io import load_game_csv  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


G = 9.80665
OUTPUT_ROOT = Path("data/processed/acceleration_processing_review")
INPUT_DIR_CANDIDATES = (
    Path("data/processed/clean_games"),
    Path("data/processed/clean_games_caleb"),
)


def default_assumptions() -> SignalProcessingAssumptions:
    return SignalProcessingAssumptions(
        resample_hz=100.0,
        winsor_percentile=99.5,
        lowpass_cutoff_hz=0.5,
        lowpass_order=4,
        linear_lowpass_cutoff_hz=1.25,
        yaw_lowpass_cutoff_hz=1.5,
        bias_window_s=8.0,
        v_max_m_s=6.0,
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


def default_vehicle() -> VehicleAssumptions:
    return VehicleAssumptions(
        system_mass_kg=105.0,
        wheel_track_m=0.68,
        yaw_inertia_kg_m2=10.0,
    )


def iter_input_files() -> list[Path]:
    files: list[Path] = []
    for directory in INPUT_DIR_CANDIDATES:
        if directory.exists():
            files.extend(sorted(directory.glob("*.csv")))
    return files


def _vector_clip(vectors: np.ndarray, limit: float | None) -> np.ndarray:
    clipped = np.asarray(vectors, dtype=float).copy()
    if limit is None or limit <= 0.0 or len(clipped) == 0:
        return clipped

    magnitude = np.linalg.norm(clipped, axis=1)
    over_limit = magnitude > limit
    if np.any(over_limit):
        clipped[over_limit] *= (limit / magnitude[over_limit])[:, None]
    return clipped


def _window_around_index(index: int, half_window_samples: int, frame_len: int) -> tuple[int, int]:
    start = max(0, index - half_window_samples)
    end = min(frame_len, index + half_window_samples + 1)
    return start, end


def _pick_event_windows(frame: pd.DataFrame) -> list[tuple[str, tuple[int, int]]]:
    half_window_samples = 18
    impact_series = frame["impact_mask"].to_numpy(dtype=bool)
    impact_indices = np.flatnonzero(impact_series)
    impact_center = int(impact_indices[len(impact_indices) // 2]) if impact_indices.size else int(
        np.argmax(frame["raw_planar_mag_m_s2"].to_numpy(dtype=float))
    )
    propulsion_center = int(np.argmax(np.abs(frame["unclipped_propulsion_m_s2"].to_numpy(dtype=float))))
    turn_center = int(np.argmax(np.abs(frame["filtered_yaw_rate_rad_s"].to_numpy(dtype=float))))
    return [
        ("impact_window", _window_around_index(impact_center, half_window_samples, len(frame))),
        ("propulsion_window", _window_around_index(propulsion_center, half_window_samples, len(frame))),
        ("turn_window", _window_around_index(turn_center, half_window_samples, len(frame))),
    ]


def compute_review_frame(
    path: Path,
    assumptions: SignalProcessingAssumptions,
    vehicle: VehicleAssumptions,
) -> tuple[pd.DataFrame, dict[str, object]]:
    raw_frame = load_game_csv(path)
    raw_timestamps = pd.to_datetime(raw_frame["loggingTime(txt)"])
    raw_elapsed_s = (raw_timestamps - raw_timestamps.iloc[0]).dt.total_seconds().to_numpy(dtype=float)

    resampled = _uniform_resample(raw_frame, assumptions.resample_hz)
    dt_s = 1.0 / assumptions.resample_hz

    accel_m_s2 = resampled[USER_ACCEL_COLUMNS].to_numpy(dtype=float) * G
    gravity_vectors = resampled[GRAVITY_COLUMNS].to_numpy(dtype=float)
    gyro_available = all(column in resampled.columns for column in GYRO_COLUMNS)
    if gyro_available:
        gyro_rad_s = resampled[GYRO_COLUMNS].to_numpy(dtype=float)
    else:
        gyro_rad_s = np.zeros_like(accel_m_s2, dtype=float)

    aligned_accel, rotation = align_vectors_to_average_gravity(accel_m_s2, gravity_vectors)
    aligned_gravity = gravity_vectors @ rotation.T
    aligned_gyro = gyro_rad_s @ rotation.T

    gravity_unit = aligned_gravity / np.linalg.norm(aligned_gravity, axis=1, keepdims=True)
    vertical_component = np.sum(aligned_accel * gravity_unit, axis=1)
    horizontal_accel = aligned_accel - (vertical_component[:, None] * gravity_unit)
    planar_xy = horizontal_accel[:, :2]
    planar_mag = np.linalg.norm(planar_xy, axis=1)
    raw_yaw_rate = aligned_gyro[:, 2]

    impact_mask, impact_window_count = _impact_mask(planar_xy, dt_s, assumptions)
    repaired_planar = np.column_stack([_interpolate_masked(planar_xy[:, axis], impact_mask) for axis in range(2)])
    repaired_yaw = _interpolate_masked(raw_yaw_rate, impact_mask)

    winsorized_components: list[np.ndarray] = []
    winsor_limits: list[float] = []
    for axis in range(2):
        clipped, limit = _winsorize(repaired_planar[:, axis], assumptions.winsor_percentile)
        winsorized_components.append(clipped)
        winsor_limits.append(limit)
    winsorized_planar = np.column_stack(winsorized_components)

    filtered_planar = np.column_stack(
        [
            _lowpass(
                winsorized_planar[:, axis],
                assumptions.resample_hz,
                assumptions.effective_linear_cutoff_hz(),
                assumptions.lowpass_order,
            )
            for axis in range(2)
        ]
    )
    filtered_yaw = _lowpass(
        repaired_yaw,
        assumptions.resample_hz,
        assumptions.effective_yaw_cutoff_hz(),
        assumptions.lowpass_order,
    )

    bias_window = int(round(assumptions.bias_window_s * assumptions.resample_hz))
    planar_bias = np.column_stack(
        [_centered_rolling_median(filtered_planar[:, axis], bias_window) for axis in range(2)]
    )
    unclipped_planar = filtered_planar - planar_bias
    clipped_planar = _vector_clip(unclipped_planar, assumptions.max_realistic_accel_m_s2)

    velocity_xy, speed_m_s = _integrate_planar_velocity(clipped_planar, filtered_yaw, dt_s, assumptions)
    yaw_accel_rad_s2 = np.gradient(filtered_yaw, dt_s) if len(filtered_yaw) > 1 else np.zeros_like(filtered_yaw)
    unclipped_propulsion = _project_along_velocity(unclipped_planar, velocity_xy, speed_m_s)
    clipped_propulsion = _project_along_velocity(clipped_planar, velocity_xy, speed_m_s)

    half_track = vehicle.wheel_track_m / 2.0
    left_wheel_speed = speed_m_s - (half_track * filtered_yaw)
    right_wheel_speed = speed_m_s + (half_track * filtered_yaw)
    stationary = (
        (np.linalg.norm(clipped_planar, axis=1) <= assumptions.stationary_accel_threshold_m_s2)
        & (np.abs(filtered_yaw) <= assumptions.stationary_yaw_rate_threshold_rad_s)
    )

    frame = pd.DataFrame(
        {
            "time_s": resampled["time_s"],
            "elapsed_min": resampled["time_s"] / 60.0,
            "raw_accel_x_m_s2": accel_m_s2[:, 0],
            "raw_accel_y_m_s2": accel_m_s2[:, 1],
            "raw_accel_z_m_s2": accel_m_s2[:, 2],
            "gravity_x_g": aligned_gravity[:, 0],
            "gravity_y_g": aligned_gravity[:, 1],
            "gravity_z_g": aligned_gravity[:, 2],
            "planar_raw_x_m_s2": planar_xy[:, 0],
            "planar_raw_y_m_s2": planar_xy[:, 1],
            "raw_planar_mag_m_s2": planar_mag,
            "planar_repaired_x_m_s2": repaired_planar[:, 0],
            "planar_repaired_y_m_s2": repaired_planar[:, 1],
            "planar_winsor_x_m_s2": winsorized_planar[:, 0],
            "planar_winsor_y_m_s2": winsorized_planar[:, 1],
            "planar_filtered_x_m_s2": filtered_planar[:, 0],
            "planar_filtered_y_m_s2": filtered_planar[:, 1],
            "planar_bias_x_m_s2": planar_bias[:, 0],
            "planar_bias_y_m_s2": planar_bias[:, 1],
            "planar_unclipped_x_m_s2": unclipped_planar[:, 0],
            "planar_unclipped_y_m_s2": unclipped_planar[:, 1],
            "planar_clipped_x_m_s2": clipped_planar[:, 0],
            "planar_clipped_y_m_s2": clipped_planar[:, 1],
            "unclipped_propulsion_m_s2": unclipped_propulsion,
            "clipped_propulsion_m_s2": clipped_propulsion,
            "raw_yaw_rate_rad_s": raw_yaw_rate,
            "repaired_yaw_rate_rad_s": repaired_yaw,
            "filtered_yaw_rate_rad_s": filtered_yaw,
            "yaw_accel_rad_s2": yaw_accel_rad_s2,
            "surrogate_velocity_x_m_s": velocity_xy[:, 0],
            "surrogate_velocity_y_m_s": velocity_xy[:, 1],
            "surrogate_speed_m_s": speed_m_s,
            "left_wheel_speed_m_s": left_wheel_speed,
            "right_wheel_speed_m_s": right_wheel_speed,
            "impact_mask": impact_mask.astype(int),
            "stationary_mask": stationary.astype(int),
        }
    )

    metadata: dict[str, object] = {
        "game_name": path.stem.replace("_clean", ""),
        "source_path": str(path),
        "raw_samples": int(len(raw_frame)),
        "resampled_samples": int(len(resampled)),
        "raw_duration_min": float(raw_elapsed_s[-1] / 60.0) if len(raw_elapsed_s) else 0.0,
        "resampled_duration_min": float(frame["elapsed_min"].iloc[-1]) if len(frame) else 0.0,
        "impact_sample_count": int(np.sum(impact_mask)),
        "impact_window_count": impact_window_count,
        "gyro_available": gyro_available,
        "winsor_limit_planar_x_m_s2": float(winsor_limits[0]) if winsor_limits else 0.0,
        "winsor_limit_planar_y_m_s2": float(winsor_limits[1]) if len(winsor_limits) > 1 else 0.0,
        "clip_limit_m_s2": float(assumptions.max_realistic_accel_m_s2) if assumptions.max_realistic_accel_m_s2 is not None else None,
        "peak_planar_mag_m_s2": float(frame["raw_planar_mag_m_s2"].max()),
        "peak_propulsion_m_s2": float(np.abs(frame["clipped_propulsion_m_s2"]).max()),
        "peak_yaw_rate_rad_s": float(np.abs(frame["filtered_yaw_rate_rad_s"]).max()),
        "peak_speed_m_s": float(frame["surrogate_speed_m_s"].max()),
        "peak_left_wheel_speed_m_s": float(np.abs(frame["left_wheel_speed_m_s"]).max()),
        "peak_right_wheel_speed_m_s": float(np.abs(frame["right_wheel_speed_m_s"]).max()),
        "stationary_samples": int(frame["stationary_mask"].sum()),
    }
    return frame, metadata


def _shade_impact_regions(axis: plt.Axes, elapsed: pd.Series, impact_mask: np.ndarray) -> None:
    if not np.any(impact_mask):
        return
    starts = np.flatnonzero(impact_mask & ~np.concatenate(([False], impact_mask[:-1])))
    ends = np.flatnonzero(impact_mask & ~np.concatenate((impact_mask[1:], [False])))
    for start, end in zip(starts, ends):
        axis.axvspan(float(elapsed.iloc[start]), float(elapsed.iloc[end]), color="#e45756", alpha=0.12)


def save_sensor_context(frame: pd.DataFrame, metadata: dict[str, object], outdir: Path) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True, constrained_layout=True)
    elapsed = frame["elapsed_min"]
    impact_mask = frame["impact_mask"].to_numpy(dtype=bool)

    axes[0].plot(elapsed, frame["raw_accel_x_m_s2"], color="#4c78a8", linewidth=0.7, label="User accel X")
    axes[0].plot(elapsed, frame["raw_accel_y_m_s2"], color="#f58518", linewidth=0.7, label="User accel Y")
    axes[0].plot(elapsed, frame["raw_accel_z_m_s2"], color="#54a24b", linewidth=0.7, label="User accel Z")
    axes[0].set_title(f"{metadata['game_name']}: raw phone acceleration axes")
    axes[0].set_ylabel("m/s^2")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="upper right")

    axes[1].plot(elapsed, frame["gravity_x_g"], color="#4c78a8", linewidth=0.7, label="Aligned gravity X")
    axes[1].plot(elapsed, frame["gravity_y_g"], color="#f58518", linewidth=0.7, label="Aligned gravity Y")
    axes[1].plot(elapsed, frame["gravity_z_g"], color="#54a24b", linewidth=0.7, label="Aligned gravity Z")
    axes[1].set_title("Gravity alignment used to flatten motion into the court plane")
    axes[1].set_ylabel("g")
    axes[1].grid(alpha=0.25)
    axes[1].legend(loc="upper right")

    axes[2].plot(elapsed, frame["planar_raw_x_m_s2"], color="#4c78a8", linewidth=0.8, label="Planar X")
    axes[2].plot(elapsed, frame["planar_raw_y_m_s2"], color="#f58518", linewidth=0.8, label="Planar Y")
    axes[2].plot(elapsed, frame["raw_planar_mag_m_s2"], color="#222222", linewidth=0.9, alpha=0.8, label="Planar magnitude")
    _shade_impact_regions(axes[2], elapsed, impact_mask)
    axes[2].set_title("Court-plane motion before impact repair")
    axes[2].set_ylabel("m/s^2")
    axes[2].grid(alpha=0.25)
    axes[2].legend(loc="upper right")

    axes[3].plot(elapsed, frame["raw_yaw_rate_rad_s"], color="#9ecae9", linewidth=0.8, alpha=0.6, label="Raw yaw rate")
    axes[3].plot(elapsed, frame["filtered_yaw_rate_rad_s"], color="#e45756", linewidth=1.1, label="Filtered yaw rate")
    _shade_impact_regions(axes[3], elapsed, impact_mask)
    axes[3].axhline(0.0, color="#444444", linewidth=0.9)
    if metadata["gyro_available"]:
        axes[3].set_title("Yaw rate shows turning demand directly")
        axes[3].legend(loc="upper right")
    else:
        axes[3].set_title("Yaw rate unavailable in this dataset; current trace is zero-filled")
        axes[3].text(
            0.99,
            0.9,
            "No motionRotationRate columns in the cleaned CSV",
            transform=axes[3].transAxes,
            ha="right",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
        )
    axes[3].set_ylabel("rad/s")
    axes[3].set_xlabel("Elapsed time (min)")
    axes[3].grid(alpha=0.25)

    fig.savefig(outdir / "sensor_context.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_pipeline_overview(frame: pd.DataFrame, metadata: dict[str, object], outdir: Path) -> None:
    fig = plt.figure(figsize=(16, 13), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, height_ratios=[1.15, 1.0, 1.0])
    elapsed = frame["elapsed_min"]
    impact_mask = frame["impact_mask"].to_numpy(dtype=bool)
    clip_limit = metadata["clip_limit_m_s2"]

    ax1 = fig.add_subplot(grid[0, :])
    ax1.plot(elapsed, frame["raw_planar_mag_m_s2"], color="#9ecae9", linewidth=0.8, alpha=0.45, label="Raw planar magnitude")
    ax1.plot(elapsed, np.linalg.norm(frame[["planar_repaired_x_m_s2", "planar_repaired_y_m_s2"]].to_numpy(dtype=float), axis=1), color="#4c78a8", linewidth=0.9, label="After impact repair")
    ax1.plot(elapsed, np.linalg.norm(frame[["planar_clipped_x_m_s2", "planar_clipped_y_m_s2"]].to_numpy(dtype=float), axis=1), color="#54a24b", linewidth=1.1, label="Final planar magnitude")
    _shade_impact_regions(ax1, elapsed, impact_mask)
    ax1.set_title(f"{metadata['game_name']}: impact masking before smoothing")
    ax1.set_xlabel("Elapsed time (min)")
    ax1.set_ylabel("Acceleration (m/s^2)")
    ax1.grid(alpha=0.25)
    ax1.legend(loc="upper right")

    ax2 = fig.add_subplot(grid[1, 0])
    ax2.plot(elapsed, frame["planar_raw_x_m_s2"], color="#9ecae9", linewidth=0.7, alpha=0.5, label="Raw planar X")
    ax2.plot(elapsed, frame["planar_winsor_x_m_s2"], color="#4c78a8", linewidth=0.8, alpha=0.9, label="Winsorized X")
    ax2.plot(elapsed, frame["planar_filtered_x_m_s2"], color="#f58518", linewidth=1.0, label="Filtered X")
    ax2.plot(elapsed, frame["planar_bias_x_m_s2"], color="#72b7b2", linewidth=1.0, label="Rolling bias")
    ax2.plot(elapsed, frame["planar_clipped_x_m_s2"], color="#54a24b", linewidth=1.1, label="Final planar X")
    _shade_impact_regions(ax2, elapsed, impact_mask)
    ax2.set_title("Planar acceleration cleaning on one axis")
    ax2.set_xlabel("Elapsed time (min)")
    ax2.set_ylabel("m/s^2")
    ax2.grid(alpha=0.25)
    ax2.legend(loc="upper right", fontsize=8)

    ax3 = fig.add_subplot(grid[1, 1])
    ax3.plot(elapsed, frame["unclipped_propulsion_m_s2"], color="#e45756", linewidth=0.9, label="Propulsion before clip")
    ax3.plot(elapsed, frame["clipped_propulsion_m_s2"], color="#54a24b", linewidth=1.1, label="Final propulsion demand")
    if clip_limit is not None:
        ax3.axhline(float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
        ax3.axhline(-float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
    ax3.axhline(0.0, color="#444444", linewidth=0.9)
    _shade_impact_regions(ax3, elapsed, impact_mask)
    ax3.set_title("Scalar propulsion signal used downstream")
    ax3.set_xlabel("Elapsed time (min)")
    ax3.set_ylabel("m/s^2")
    ax3.grid(alpha=0.25)
    ax3.legend(loc="upper right")

    ax4 = fig.add_subplot(grid[2, 0])
    ax4.plot(elapsed, frame["filtered_yaw_rate_rad_s"], color="#e45756", linewidth=1.0, label="Filtered yaw rate")
    ax4.plot(elapsed, frame["left_wheel_speed_m_s"], color="#4c78a8", linewidth=0.9, label="Left wheel speed")
    ax4.plot(elapsed, frame["right_wheel_speed_m_s"], color="#f58518", linewidth=0.9, label="Right wheel speed")
    ax4.axhline(0.0, color="#444444", linewidth=0.9)
    if metadata["gyro_available"]:
        ax4.set_title("Turning splits left/right wheel demand")
    else:
        ax4.set_title("Wheel split panel is inactive here because yaw data is missing")
        ax4.text(
            0.99,
            0.9,
            "Left/right traces collapse together without yaw input",
            transform=ax4.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
        )
    ax4.set_xlabel("Elapsed time (min)")
    ax4.set_ylabel("rad/s or m/s")
    ax4.grid(alpha=0.25)
    ax4.legend(loc="upper right")

    ax5 = fig.add_subplot(grid[2, 1])
    text = (
        f"Impact windows: {metadata['impact_window_count']}\n"
        f"Impact samples: {metadata['impact_sample_count']}\n"
        f"Winsor X: {metadata['winsor_limit_planar_x_m_s2']:.2f} m/s^2\n"
        f"Winsor Y: {metadata['winsor_limit_planar_y_m_s2']:.2f} m/s^2\n"
        f"Clip limit: {metadata['clip_limit_m_s2']:.2f} m/s^2\n"
        f"Gyro available: {metadata['gyro_available']}\n"
        f"Peak planar magnitude: {metadata['peak_planar_mag_m_s2']:.2f} m/s^2\n"
        f"Peak propulsion: {metadata['peak_propulsion_m_s2']:.2f} m/s^2\n"
        f"Peak yaw rate: {metadata['peak_yaw_rate_rad_s']:.2f} rad/s\n"
        f"Peak speed: {metadata['peak_speed_m_s']:.2f} m/s\n"
        f"Peak left/right wheel speed: {metadata['peak_left_wheel_speed_m_s']:.2f} / {metadata['peak_right_wheel_speed_m_s']:.2f} m/s"
    )
    ax5.axis("off")
    ax5.text(0.02, 0.98, text, va="top", ha="left", fontsize=11, family="monospace")

    fig.suptitle("Planar propulsion processing overview", fontsize=18, weight="bold")
    fig.savefig(outdir / "pipeline_overview.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_event_windows(frame: pd.DataFrame, metadata: dict[str, object], outdir: Path) -> None:
    events = _pick_event_windows(frame)
    fig, axes = plt.subplots(3, 1, figsize=(16, 12), constrained_layout=True)
    clip_limit = metadata["clip_limit_m_s2"]

    for axis, (label, (start, end)) in zip(axes, events):
        window = frame.iloc[start:end]
        elapsed = window["elapsed_min"]
        if label == "impact_window":
            axis.plot(elapsed, window["raw_planar_mag_m_s2"], color="#9ecae9", linewidth=0.9, label="Raw planar magnitude")
            axis.plot(
                elapsed,
                np.linalg.norm(window[["planar_repaired_x_m_s2", "planar_repaired_y_m_s2"]].to_numpy(dtype=float), axis=1),
                color="#4c78a8",
                linewidth=1.1,
                label="After impact repair",
            )
            axis.fill_between(elapsed, 0.0, window["impact_mask"], color="#e45756", alpha=0.18, label="Impact mask")
            axis.set_title("Strongest impact-like window")
            axis.set_ylabel("m/s^2")
        elif label == "propulsion_window":
            axis.plot(elapsed, window["unclipped_propulsion_m_s2"], color="#e45756", linewidth=1.0, label="Before clip")
            axis.plot(elapsed, window["clipped_propulsion_m_s2"], color="#54a24b", linewidth=1.2, label="Final propulsion")
            if clip_limit is not None:
                axis.axhline(float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
                axis.axhline(-float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
            axis.axhline(0.0, color="#444444", linewidth=0.9)
            axis.set_title("Strongest propulsion window")
            axis.set_ylabel("m/s^2")
        else:
            axis.plot(elapsed, window["filtered_yaw_rate_rad_s"], color="#e45756", linewidth=1.1, label="Yaw rate")
            axis.plot(elapsed, window["left_wheel_speed_m_s"], color="#4c78a8", linewidth=1.0, label="Left wheel")
            axis.plot(elapsed, window["right_wheel_speed_m_s"], color="#f58518", linewidth=1.0, label="Right wheel")
            axis.axhline(0.0, color="#444444", linewidth=0.9)
            if metadata["gyro_available"]:
                axis.set_title("Strongest turning window")
            else:
                axis.set_title("Turning window placeholder: yaw unavailable in cleaned CSV")
                axis.text(
                    0.99,
                    0.88,
                    "Current dataset cannot isolate turning from missing gyro channels",
                    transform=axis.transAxes,
                    ha="right",
                    va="top",
                    fontsize=9,
                    bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
                )
            axis.set_ylabel("rad/s or m/s")
        axis.set_xlabel("Elapsed time (min)")
        axis.grid(alpha=0.25)
        axis.legend(loc="upper right")

    fig.suptitle(f"{metadata['game_name']}: event-level review", fontsize=17, weight="bold")
    fig.savefig(outdir / "event_windows.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_summary_dashboard(summary: pd.DataFrame) -> None:
    if summary.empty:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    axes[0, 0].bar(summary["game_name"], summary["impact_window_count"], color="#e45756")
    axes[0, 0].set_title("Detected impact windows")
    axes[0, 0].set_ylabel("count")
    axes[0, 0].grid(axis="y", alpha=0.25)

    axes[0, 1].bar(summary["game_name"], summary["peak_propulsion_m_s2"], color="#54a24b")
    axes[0, 1].set_title("Peak propulsion demand")
    axes[0, 1].set_ylabel("m/s^2")
    axes[0, 1].grid(axis="y", alpha=0.25)

    if summary["gyro_available"].any():
        axes[1, 0].bar(summary["game_name"], summary["peak_yaw_rate_rad_s"], color="#4c78a8")
        axes[1, 0].set_title("Peak yaw rate")
        axes[1, 0].set_ylabel("rad/s")
        axes[1, 0].grid(axis="y", alpha=0.25)
    else:
        axes[1, 0].set_title("Peak yaw rate")
        axes[1, 0].axis("off")
        axes[1, 0].text(
            0.5,
            0.5,
            "Yaw-rate channels are absent\nin the cleaned gameplay CSVs\nfor this workspace.",
            ha="center",
            va="center",
            fontsize=12,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9, "edgecolor": "#cccccc"},
        )

    axes[1, 1].bar(summary["game_name"], summary["peak_speed_m_s"], color="#f58518")
    axes[1, 1].set_title("Peak surrogate speed")
    axes[1, 1].set_ylabel("m/s")
    axes[1, 1].grid(axis="y", alpha=0.25)

    fig.savefig(OUTPUT_ROOT / "summary_dashboard.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_summary(metadata_rows: list[dict[str, object]], assumptions: SignalProcessingAssumptions, vehicle: VehicleAssumptions) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(metadata_rows).sort_values("game_name").reset_index(drop=True)
    summary_path = OUTPUT_ROOT / "processing_summary.csv"
    summary.to_csv(summary_path, index=False)
    save_summary_dashboard(summary)

    lines = [
        "# Propulsion Processing Review",
        "",
        "These plots explain the current planar, yaw-aware gameplay pipeline used for wheelchair propulsion sizing.",
        "",
        "Important limitation: the cleaned gameplay CSVs currently present in this workspace do not include `motionRotationRate*` columns, so these review plots can validate impact handling and planar propulsion demand, but they cannot validate turning from this dataset alone.",
        "",
        "## Current flow",
        "",
        "1. Load the cleaned gameplay CSV and resample it to a uniform time base.",
        "2. Convert user acceleration from g to m/s^2.",
        "3. Align the average gravity direction to vertical and keep only court-plane motion.",
        "4. Detect impact-like events from planar acceleration magnitude and jerk, then interpolate across those windows.",
        "5. Winsorize and low-pass filter the planar acceleration and yaw-rate traces.",
        "6. Remove slow planar drift with a rolling median bias estimate.",
        "7. Clip only the final propulsion-demand magnitude to the realistic acceleration cap.",
        "8. Integrate planar acceleration into planar velocity with zero-velocity resets during stationary windows.",
        "9. Use yaw rate plus speed to split demand into left/right wheel speeds for turning-aware sizing.",
        "",
        "## Files",
        "",
        "- `summary_dashboard.png`: cross-game overview of impacts, propulsion peaks, yaw peaks, and speed peaks",
        "- `<game>/sensor_context.png`: raw phone signals, gravity alignment, planar motion, and yaw rate",
        "- `<game>/pipeline_overview.png`: impact repair, smoothing, clipping, speed, and wheel-speed split",
        "- `<game>/event_windows.png`: zoomed windows for impact, propulsion, and turning events",
        "",
        "## Assumptions used",
        "",
    ]
    for key, value in asdict(assumptions).items():
        lines.append(f"- {key}: {value}")
    lines.append(f"- wheel_track_m: {vehicle.wheel_track_m}")
    lines.append(f"- yaw_inertia_kg_m2: {vehicle.yaw_inertia_kg_m2}")
    lines.extend(
        [
            "",
            f"Machine-readable summary: `{summary_path.as_posix()}`",
        ]
    )
    (OUTPUT_ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    assumptions = default_assumptions()
    vehicle = default_vehicle()
    files = iter_input_files()
    if not files:
        raise FileNotFoundError("No cleaned gameplay CSV files were found in the expected processed-data folders.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    metadata_rows: list[dict[str, object]] = []
    for path in files:
        frame, metadata = compute_review_frame(path, assumptions, vehicle)
        game_dir = OUTPUT_ROOT / str(metadata["game_name"])
        game_dir.mkdir(parents=True, exist_ok=True)
        save_sensor_context(frame, metadata, game_dir)
        save_pipeline_overview(frame, metadata, game_dir)
        save_event_windows(frame, metadata, game_dir)
        metadata_rows.append(metadata)

    save_summary(metadata_rows, assumptions, vehicle)
    print(f"Wrote propulsion processing review outputs to {OUTPUT_ROOT.resolve()}")


if __name__ == "__main__":
    main()
