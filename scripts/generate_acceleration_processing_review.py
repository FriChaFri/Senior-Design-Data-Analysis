#!/usr/bin/env python3
"""Generate comprehensive plots explaining the acceleration cleaning pipeline."""

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
    USER_ACCEL_COLUMNS,
    SignalProcessingAssumptions,
    _centered_rolling_median,
    _estimate_forward_axis,
    _lowpass,
    _uniform_resample,
    _winsorize,
    integrate_speed,
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
        winsor_percentile=99.9,
        lowpass_cutoff_hz=0.5,
        lowpass_order=4,
        bias_window_s=20.0,
        v_max_m_s=11.0 * 0.44704,
        representative_minutes=60.0,
        session_hours=2.0,
        use_acceleration_magnitude=False,
        max_realistic_accel_m_s2=2.85,
    )


def iter_input_files() -> list[Path]:
    files: list[Path] = []
    for directory in INPUT_DIR_CANDIDATES:
        if directory.exists():
            files.extend(sorted(directory.glob("*.csv")))
    return files


def compute_pipeline(path: Path, assumptions: SignalProcessingAssumptions) -> tuple[pd.DataFrame, dict[str, object]]:
    raw_frame = load_game_csv(path)
    raw_timestamps = pd.to_datetime(raw_frame["loggingTime(txt)"])
    raw_elapsed_s = (raw_timestamps - raw_timestamps.iloc[0]).dt.total_seconds().to_numpy(dtype=float)

    resampled = _uniform_resample(raw_frame, assumptions.resample_hz)
    accel_m_s2 = resampled[USER_ACCEL_COLUMNS].to_numpy(dtype=float) * G
    gravity_vectors = resampled[GRAVITY_COLUMNS].to_numpy(dtype=float)
    gravity_norm = np.linalg.norm(gravity_vectors, axis=1, keepdims=True)
    gravity_hat = gravity_vectors / gravity_norm
    vertical_component = np.sum(accel_m_s2 * gravity_hat, axis=1)
    horizontal_accel = accel_m_s2 - (vertical_component[:, None] * gravity_hat)

    axis = _estimate_forward_axis(horizontal_accel, assumptions.resample_hz, assumptions)
    raw_forward = horizontal_accel @ axis
    winsorized_forward, winsor_limit = _winsorize(raw_forward, assumptions.winsor_percentile)
    filtered_forward = _lowpass(
        winsorized_forward,
        assumptions.resample_hz,
        assumptions.lowpass_cutoff_hz,
        assumptions.lowpass_order,
    )
    bias = _centered_rolling_median(
        filtered_forward,
        int(round(assumptions.bias_window_s * assumptions.resample_hz)),
    )
    bias_corrected = filtered_forward - bias
    unclipped_forward = bias_corrected.copy()

    accel_limit = assumptions.max_realistic_accel_m_s2
    if accel_limit is None:
        clipped_forward = unclipped_forward.copy()
    else:
        clipped_forward = np.clip(unclipped_forward, -accel_limit, accel_limit)

    speed_unclipped = integrate_speed(unclipped_forward, 1.0 / assumptions.resample_hz, assumptions.v_max_m_s)
    speed_clipped = integrate_speed(clipped_forward, 1.0 / assumptions.resample_hz, assumptions.v_max_m_s)

    frame = pd.DataFrame(
        {
            "time_s": resampled["time_s"],
            "elapsed_min": resampled["time_s"] / 60.0,
            "raw_forward_m_s2": raw_forward,
            "winsorized_forward_m_s2": winsorized_forward,
            "filtered_forward_m_s2": filtered_forward,
            "bias_m_s2": bias,
            "unclipped_forward_m_s2": unclipped_forward,
            "clipped_forward_m_s2": clipped_forward,
            "speed_unclipped_m_s": speed_unclipped,
            "speed_clipped_m_s": speed_clipped,
            "horizontal_mag_m_s2": np.linalg.norm(horizontal_accel, axis=1),
            "accel_x_m_s2": accel_m_s2[:, 0],
            "accel_y_m_s2": accel_m_s2[:, 1],
            "accel_z_m_s2": accel_m_s2[:, 2],
            "horizontal_x_m_s2": horizontal_accel[:, 0],
            "horizontal_y_m_s2": horizontal_accel[:, 1],
            "horizontal_z_m_s2": horizontal_accel[:, 2],
            "gravity_x_g": gravity_vectors[:, 0],
            "gravity_y_g": gravity_vectors[:, 1],
            "gravity_z_g": gravity_vectors[:, 2],
            "gravity_mag_g": np.linalg.norm(gravity_vectors, axis=1),
        }
    )

    metadata: dict[str, object] = {
        "game_name": path.stem.replace("_clean", ""),
        "source_path": str(path),
        "axis_x": float(axis[0]),
        "axis_y": float(axis[1]),
        "axis_z": float(axis[2]),
        "winsor_limit_m_s2": float(winsor_limit),
        "clip_limit_m_s2": float(accel_limit) if accel_limit is not None else None,
        "positive_clip_samples": int(np.sum(unclipped_forward > accel_limit)) if accel_limit is not None else 0,
        "negative_clip_samples": int(np.sum(unclipped_forward < -accel_limit)) if accel_limit is not None else 0,
        "raw_samples": int(len(raw_frame)),
        "resampled_samples": int(len(resampled)),
        "raw_duration_min": float(raw_elapsed_s[-1] / 60.0) if len(raw_elapsed_s) else 0.0,
        "resampled_duration_min": float(frame["elapsed_min"].iloc[-1]) if len(frame) else 0.0,
        "max_positive_unclipped_m_s2": float(np.max(unclipped_forward)),
        "max_negative_unclipped_m_s2": float(np.min(unclipped_forward)),
        "peak_horizontal_mag_m_s2": float(np.max(frame["horizontal_mag_m_s2"])),
        "peak_speed_unclipped_m_s": float(np.max(speed_unclipped)),
        "peak_speed_clipped_m_s": float(np.max(speed_clipped)),
        "mean_positive_accel_m_s2": float(frame.loc[frame["clipped_forward_m_s2"] > 0.0, "clipped_forward_m_s2"].mean()),
        "mean_negative_accel_m_s2": float(frame.loc[frame["clipped_forward_m_s2"] < 0.0, "clipped_forward_m_s2"].mean()),
    }
    return frame, metadata


def _event_windows(frame: pd.DataFrame) -> list[tuple[str, tuple[float, float]]]:
    unclipped = frame["unclipped_forward_m_s2"].to_numpy(dtype=float)
    max_idx = int(np.argmax(unclipped))
    min_idx = int(np.argmin(unclipped))
    pos_center = float(frame.iloc[max_idx]["elapsed_min"])
    neg_center = float(frame.iloc[min_idx]["elapsed_min"])
    half_window_min = 0.12
    return [
        ("strongest_positive_event", (max(0.0, pos_center - half_window_min), pos_center + half_window_min)),
        ("strongest_negative_event", (max(0.0, neg_center - half_window_min), neg_center + half_window_min)),
    ]


def save_pipeline_overview(frame: pd.DataFrame, metadata: dict[str, object], outdir: Path) -> None:
    fig = plt.figure(figsize=(16, 13), constrained_layout=True)
    grid = fig.add_gridspec(4, 2, height_ratios=[1.15, 1.0, 1.0, 1.0])
    elapsed = frame["elapsed_min"]
    clip_limit = metadata["clip_limit_m_s2"]

    ax1 = fig.add_subplot(grid[0, :])
    plot_slice = slice(None, None, 10)
    ax1.plot(elapsed.iloc[plot_slice], frame["raw_forward_m_s2"].iloc[plot_slice], color="#9ecae9", linewidth=0.7, alpha=0.45, label="Raw forward estimate")
    ax1.plot(elapsed, frame["winsorized_forward_m_s2"], color="#4c78a8", linewidth=0.9, alpha=0.8, label="After winsorization")
    ax1.plot(elapsed, frame["filtered_forward_m_s2"], color="#f58518", linewidth=1.0, label="After low-pass filter")
    ax1.plot(elapsed, frame["unclipped_forward_m_s2"], color="#e45756", linewidth=1.0, alpha=0.95, label="After bias removal")
    ax1.plot(elapsed, frame["clipped_forward_m_s2"], color="#54a24b", linewidth=1.2, alpha=0.95, label="Final acceleration used")
    if clip_limit is not None:
        ax1.axhline(float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
        ax1.axhline(-float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
    ax1.set_title(f"{metadata['game_name']}: full preprocessing pipeline")
    ax1.set_xlabel("Elapsed time (min)")
    ax1.set_ylabel("Acceleration (m/s^2)")
    ax1.grid(alpha=0.25)
    ax1.legend(loc="upper right", ncol=2)

    ax2 = fig.add_subplot(grid[1, 0])
    ax2.plot(elapsed, frame["filtered_forward_m_s2"], color="#f58518", linewidth=1.0, label="Filtered")
    ax2.plot(elapsed, frame["bias_m_s2"], color="#72b7b2", linewidth=1.0, label="Rolling median bias")
    ax2.plot(elapsed, frame["unclipped_forward_m_s2"], color="#e45756", linewidth=1.0, label="Filtered - bias")
    ax2.axhline(0.0, color="#444444", linewidth=0.9)
    ax2.set_title("Bias removal justification")
    ax2.set_xlabel("Elapsed time (min)")
    ax2.set_ylabel("Acceleration (m/s^2)")
    ax2.grid(alpha=0.25)
    ax2.legend(loc="upper right")

    ax3 = fig.add_subplot(grid[1, 1])
    ax3.hist(frame["raw_forward_m_s2"], bins=120, density=True, alpha=0.35, color="#9ecae9", label="Raw forward")
    ax3.hist(frame["filtered_forward_m_s2"], bins=120, density=True, alpha=0.45, color="#f58518", label="Filtered")
    ax3.hist(frame["clipped_forward_m_s2"], bins=120, density=True, alpha=0.5, color="#54a24b", label="Final clipped")
    if clip_limit is not None:
        ax3.axvline(float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
        ax3.axvline(-float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
    ax3.set_title("Distribution through processing")
    ax3.set_xlabel("Acceleration (m/s^2)")
    ax3.set_ylabel("Density")
    ax3.grid(alpha=0.2)
    ax3.legend(loc="upper right")

    ax4 = fig.add_subplot(grid[2, 0])
    ax4.plot(elapsed, frame["unclipped_forward_m_s2"], color="#e45756", linewidth=0.9, label="Unclipped")
    ax4.plot(elapsed, frame["clipped_forward_m_s2"], color="#54a24b", linewidth=1.1, label="Clipped")
    if clip_limit is not None:
        ax4.fill_between(elapsed, float(clip_limit), frame["unclipped_forward_m_s2"], where=frame["unclipped_forward_m_s2"] > float(clip_limit), color="#e45756", alpha=0.18)
        ax4.fill_between(elapsed, -float(clip_limit), frame["unclipped_forward_m_s2"], where=frame["unclipped_forward_m_s2"] < -float(clip_limit), color="#e45756", alpha=0.18)
        ax4.axhline(float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
        ax4.axhline(-float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
    ax4.axhline(0.0, color="#444444", linewidth=0.9)
    ax4.set_title("Spike clipping / possible collision trimming")
    ax4.set_xlabel("Elapsed time (min)")
    ax4.set_ylabel("Acceleration (m/s^2)")
    ax4.grid(alpha=0.25)
    ax4.legend(loc="upper right")

    ax5 = fig.add_subplot(grid[2, 1])
    ax5.plot(elapsed, frame["speed_unclipped_m_s"], color="#e45756", linewidth=1.0, label="Speed from unclipped accel")
    ax5.plot(elapsed, frame["speed_clipped_m_s"], color="#54a24b", linewidth=1.1, label="Speed from clipped accel")
    ax5.set_title("Why clipping matters to downstream speed")
    ax5.set_xlabel("Elapsed time (min)")
    ax5.set_ylabel("Surrogate speed (m/s)")
    ax5.grid(alpha=0.25)
    ax5.legend(loc="upper right")

    ax6 = fig.add_subplot(grid[3, 0])
    ax6.plot(elapsed, frame["horizontal_mag_m_s2"], color="#4c78a8", linewidth=0.8, alpha=0.8, label="Horizontal magnitude")
    ax6.plot(elapsed, np.abs(frame["clipped_forward_m_s2"]), color="#f58518", linewidth=1.0, alpha=0.85, label="Absolute forward demand")
    ax6.set_title("Magnitude vs signed forward demand")
    ax6.set_xlabel("Elapsed time (min)")
    ax6.set_ylabel("Acceleration (m/s^2)")
    ax6.grid(alpha=0.25)
    ax6.legend(loc="upper right")

    ax7 = fig.add_subplot(grid[3, 1])
    text = (
        f"Forward axis: ({metadata['axis_x']:.3f}, {metadata['axis_y']:.3f}, {metadata['axis_z']:.3f})\n"
        f"Winsor limit: {metadata['winsor_limit_m_s2']:.2f} m/s^2\n"
        f"Clip limit: {metadata['clip_limit_m_s2']:.2f} m/s^2\n"
        f"Positive clipped samples: {metadata['positive_clip_samples']}\n"
        f"Negative clipped samples: {metadata['negative_clip_samples']}\n"
        f"Max positive before clip: {metadata['max_positive_unclipped_m_s2']:.2f} m/s^2\n"
        f"Max negative before clip: {metadata['max_negative_unclipped_m_s2']:.2f} m/s^2\n"
        f"Peak speed before clip: {metadata['peak_speed_unclipped_m_s']:.2f} m/s\n"
        f"Peak speed after clip: {metadata['peak_speed_clipped_m_s']:.2f} m/s"
    )
    ax7.axis("off")
    ax7.text(0.02, 0.98, text, va="top", ha="left", fontsize=11, family="monospace")

    fig.suptitle("Acceleration processing review", fontsize=18, weight="bold")
    fig.savefig(outdir / "pipeline_overview.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_sensor_context(frame: pd.DataFrame, metadata: dict[str, object], outdir: Path) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True, constrained_layout=True)
    elapsed = frame["elapsed_min"]

    axes[0].plot(elapsed, frame["accel_x_m_s2"], color="#4c78a8", linewidth=0.7, label="User accel X")
    axes[0].plot(elapsed, frame["accel_y_m_s2"], color="#f58518", linewidth=0.7, label="User accel Y")
    axes[0].plot(elapsed, frame["accel_z_m_s2"], color="#54a24b", linewidth=0.7, label="User accel Z")
    axes[0].set_title(f"{metadata['game_name']}: raw user-acceleration axes")
    axes[0].set_ylabel("m/s^2")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="upper right")

    axes[1].plot(elapsed, frame["gravity_x_g"], color="#4c78a8", linewidth=0.7, label="Gravity X")
    axes[1].plot(elapsed, frame["gravity_y_g"], color="#f58518", linewidth=0.7, label="Gravity Y")
    axes[1].plot(elapsed, frame["gravity_z_g"], color="#54a24b", linewidth=0.7, label="Gravity Z")
    axes[1].plot(elapsed, frame["gravity_mag_g"], color="#222222", linewidth=1.0, alpha=0.8, label="Gravity magnitude")
    axes[1].set_title("Gravity vector used to separate vertical from horizontal motion")
    axes[1].set_ylabel("g")
    axes[1].grid(alpha=0.25)
    axes[1].legend(loc="upper right")

    axes[2].plot(elapsed, frame["horizontal_x_m_s2"], color="#4c78a8", linewidth=0.7, label="Horizontal X")
    axes[2].plot(elapsed, frame["horizontal_y_m_s2"], color="#f58518", linewidth=0.7, label="Horizontal Y")
    axes[2].plot(elapsed, frame["horizontal_z_m_s2"], color="#54a24b", linewidth=0.7, label="Horizontal Z")
    axes[2].set_title("After subtracting the vertical component")
    axes[2].set_ylabel("m/s^2")
    axes[2].grid(alpha=0.25)
    axes[2].legend(loc="upper right")

    axes[3].plot(elapsed, frame["horizontal_mag_m_s2"], color="#4c78a8", linewidth=0.8, label="Horizontal magnitude")
    axes[3].plot(elapsed, frame["raw_forward_m_s2"], color="#e45756", linewidth=0.8, alpha=0.9, label="Projected onto forward axis")
    axes[3].axhline(0.0, color="#444444", linewidth=0.9)
    axes[3].set_title("Reducing 3-axis motion to one signed drive/brake direction")
    axes[3].set_ylabel("m/s^2")
    axes[3].set_xlabel("Elapsed time (min)")
    axes[3].grid(alpha=0.25)
    axes[3].legend(loc="upper right")

    fig.savefig(outdir / "sensor_context.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_event_windows(frame: pd.DataFrame, metadata: dict[str, object], outdir: Path) -> None:
    windows = _event_windows(frame)
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), constrained_layout=True)
    clip_limit = metadata["clip_limit_m_s2"]

    for axis, (label, window) in zip(axes, windows):
        mask = frame["elapsed_min"].between(window[0], window[1])
        axis.plot(frame.loc[mask, "elapsed_min"], frame.loc[mask, "raw_forward_m_s2"], color="#9ecae9", linewidth=0.8, alpha=0.6, label="Raw forward")
        axis.plot(frame.loc[mask, "elapsed_min"], frame.loc[mask, "winsorized_forward_m_s2"], color="#4c78a8", linewidth=0.9, alpha=0.9, label="Winsorized")
        axis.plot(frame.loc[mask, "elapsed_min"], frame.loc[mask, "filtered_forward_m_s2"], color="#f58518", linewidth=1.0, label="Low-pass filtered")
        axis.plot(frame.loc[mask, "elapsed_min"], frame.loc[mask, "unclipped_forward_m_s2"], color="#e45756", linewidth=1.1, label="Bias removed")
        axis.plot(frame.loc[mask, "elapsed_min"], frame.loc[mask, "clipped_forward_m_s2"], color="#54a24b", linewidth=1.3, label="Final clipped")
        if clip_limit is not None:
            axis.axhline(float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
            axis.axhline(-float(clip_limit), color="#666666", linestyle="--", linewidth=1.0)
        axis.axhline(0.0, color="#444444", linewidth=0.9)
        axis.set_xlim(window)
        axis.set_title(label.replace("_", " "))
        axis.set_xlabel("Elapsed time (min)")
        axis.set_ylabel("Acceleration (m/s^2)")
        axis.grid(alpha=0.25)
        axis.legend(loc="upper right")

    fig.suptitle(f"{metadata['game_name']}: strongest acceleration and braking events", fontsize=17, weight="bold")
    fig.savefig(outdir / "event_windows.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_summary(metadata_rows: list[dict[str, object]], assumptions: SignalProcessingAssumptions) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT_ROOT / "processing_summary.csv"
    pd.DataFrame(metadata_rows).to_csv(summary_path, index=False)

    lines = [
        "# Acceleration Processing Review",
        "",
        "These outputs explain how the gameplay acceleration signal is cleaned before it is used for battery sizing.",
        "",
        "## Processing steps",
        "",
        "1. Load the cleaned gameplay CSV and resample it to a uniform sample rate.",
        "2. Convert user acceleration from g to m/s^2.",
        "3. Use the gravity vector to remove the vertical component and keep horizontal motion.",
        "4. Estimate a dominant forward axis and project the 3-axis motion onto that signed direction.",
        "5. Winsorize extreme outliers at a high percentile to reduce the influence of isolated spikes.",
        "6. Low-pass filter to remove very fast jitter that does not represent wheelchair-scale motion.",
        "7. Remove slow bias drift with a centered rolling median.",
        "8. Clip acceleration above the realistic threshold to limit likely collision-like spikes.",
        "9. Integrate the final acceleration into a bounded surrogate speed for downstream force and power modeling.",
        "",
        "## Assumptions used",
        "",
    ]
    for key, value in asdict(assumptions).items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Per-game folders",
            "",
            "Each game folder contains:",
            "- `sensor_context.png`: raw axes, gravity, horizontal-only motion, and forward-axis projection",
            "- `pipeline_overview.png`: the full signal-cleaning pipeline and before/after comparisons",
            "- `event_windows.png`: zoomed views of the strongest positive and negative events",
            "",
            f"A machine-readable summary was also written to `{summary_path.as_posix()}`.",
        ]
    )
    (OUTPUT_ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    assumptions = default_assumptions()
    files = iter_input_files()
    if not files:
        raise FileNotFoundError("No cleaned gameplay CSV files were found in the expected processed-data folders.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    metadata_rows: list[dict[str, object]] = []
    for path in files:
        frame, metadata = compute_pipeline(path, assumptions)
        game_dir = OUTPUT_ROOT / str(metadata["game_name"])
        game_dir.mkdir(parents=True, exist_ok=True)
        save_sensor_context(frame, metadata, game_dir)
        save_pipeline_overview(frame, metadata, game_dir)
        save_event_windows(frame, metadata, game_dir)
        metadata_rows.append(metadata)

    save_summary(metadata_rows, assumptions)
    print(f"Wrote acceleration processing review outputs to {OUTPUT_ROOT.resolve()}")


if __name__ == "__main__":
    main()
