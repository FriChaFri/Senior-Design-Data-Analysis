"""Derive gameplay-sizing datasets from the baseline cleaned files."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import pandas as pd

from imu_pipeline.io import TrimSpec, TrimWindow, load_game_csv, trim_game_data


USER_ACCEL_COLUMNS = [
    "motionUserAccelerationX(G)",
    "motionUserAccelerationY(G)",
    "motionUserAccelerationZ(G)",
]


@dataclass(frozen=True)
class CollisionWindowSummary:
    """One detected collision-like time window."""

    start_min: float
    end_min: float
    peak_accel_m_s2: float
    hit_samples: int


def detect_collision_windows(
    frame: pd.DataFrame,
    magnitude_threshold_m_s2: float = 40.0,
    cluster_gap_s: float = 0.5,
    padding_s: float = 0.75,
    gravity_m_s2: float = 9.80665,
) -> list[CollisionWindowSummary]:
    """Detect obvious collision-like spikes in an already-cleaned game."""

    elapsed_s = (
        pd.to_datetime(frame["loggingTime(txt)"]) - pd.to_datetime(frame["loggingTime(txt)"]).iloc[0]
    ).dt.total_seconds()
    accel_mag_m_s2 = (frame[USER_ACCEL_COLUMNS].pow(2).sum(axis=1) ** 0.5) * gravity_m_s2
    hit_index = frame.index[accel_mag_m_s2 >= magnitude_threshold_m_s2].tolist()
    if not hit_index:
        return []

    clustered: list[tuple[int, int]] = []
    start_index = hit_index[0]
    prev_index = hit_index[0]
    for index in hit_index[1:]:
        gap_s = float(elapsed_s.iloc[index] - elapsed_s.iloc[prev_index])
        if gap_s > cluster_gap_s:
            clustered.append((start_index, prev_index))
            start_index = index
        prev_index = index
    clustered.append((start_index, prev_index))

    windows: list[CollisionWindowSummary] = []
    for start_idx, end_idx in clustered:
        start_s = max(0.0, float(elapsed_s.iloc[start_idx]) - padding_s)
        end_s = min(float(elapsed_s.iloc[-1]), float(elapsed_s.iloc[end_idx]) + padding_s)
        peak_accel = float(accel_mag_m_s2.iloc[start_idx : end_idx + 1].max())
        windows.append(
            CollisionWindowSummary(
                start_min=start_s / 60.0,
                end_min=end_s / 60.0,
                peak_accel_m_s2=peak_accel,
                hit_samples=end_idx - start_idx + 1,
            )
        )

    merged: list[CollisionWindowSummary] = []
    for window in windows:
        if not merged or window.start_min > merged[-1].end_min:
            merged.append(window)
            continue

        previous = merged[-1]
        merged[-1] = CollisionWindowSummary(
            start_min=previous.start_min,
            end_min=max(previous.end_min, window.end_min),
            peak_accel_m_s2=max(previous.peak_accel_m_s2, window.peak_accel_m_s2),
            hit_samples=previous.hit_samples + window.hit_samples,
        )
    return merged


def build_collision_trimmed_game(
    frame: pd.DataFrame,
    windows: list[CollisionWindowSummary],
) -> pd.DataFrame:
    """Remove detected collision windows while preserving compressed gameplay time."""

    elapsed_s = (
        pd.to_datetime(frame["loggingTime(txt)"]) - pd.to_datetime(frame["loggingTime(txt)"]).iloc[0]
    ).dt.total_seconds()
    sample_period_s = float(elapsed_s.diff().median()) if len(frame) > 1 else 0.0
    keep_end_min = (float(elapsed_s.iloc[-1]) + sample_period_s) / 60.0
    trim_spec = TrimSpec(
        keep_start_min=0.0,
        keep_end_min=keep_end_min,
        remove_windows=tuple(TrimWindow(window.start_min, window.end_min) for window in windows),
    )
    trimmed = trim_game_data(frame, trim_spec)
    return trimmed


def derive_gameplay_dataset(
    input_dir: str | Path,
    output_dir: str | Path,
    magnitude_threshold_m_s2: float = 40.0,
    cluster_gap_s: float = 0.5,
    padding_s: float = 0.75,
) -> dict[str, dict]:
    """Create a gameplay-sizing dataset from the baseline cleaned files."""

    input_root = Path(input_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    for csv_path in sorted(input_root.glob("*.csv")):
        game = load_game_csv(csv_path)
        windows = detect_collision_windows(
            game,
            magnitude_threshold_m_s2=magnitude_threshold_m_s2,
            cluster_gap_s=cluster_gap_s,
            padding_s=padding_s,
        )
        trimmed = build_collision_trimmed_game(game, windows)
        trimmed["loggingTime(txt)"] = pd.to_datetime(trimmed["loggingTime(txt)"]).dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%f%z"
        )
        trimmed.to_csv(output_root / csv_path.name, index=False)
        manifest[csv_path.stem.replace("_clean", "")] = {
            "source_file": csv_path.name,
            "collision_threshold_m_s2": magnitude_threshold_m_s2,
            "cluster_gap_s": cluster_gap_s,
            "padding_s": padding_s,
            "source_rows": int(len(game)),
            "gameplay_rows": int(len(trimmed)),
            "rows_removed": int(len(game) - len(trimmed)),
            "collision_windows": [asdict(window) for window in windows],
        }

    (output_root / "collision_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
