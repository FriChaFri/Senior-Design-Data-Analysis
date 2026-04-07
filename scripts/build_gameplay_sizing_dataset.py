#!/usr/bin/env python3
"""Derive a collision-trimmed gameplay dataset from the baseline cleaned files."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from imu_pipeline.game_processing import build_clean_games_dataset  # noqa: E402
from imu_pipeline.gameplay_dataset import derive_gameplay_dataset  # noqa: E402


INPUT_DIR = Path("data/processed/clean_games")
OUTPUT_DIR = Path("data/processed/clean_games_gameplay")


def main() -> None:
    build_clean_games_dataset(processed_dir=INPUT_DIR)
    manifest = derive_gameplay_dataset(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        magnitude_threshold_m_s2=40.0,
        cluster_gap_s=0.5,
        padding_s=0.75,
    )
    for game_name, summary in manifest.items():
        print(
            f"{game_name}: removed {summary['rows_removed']} rows across "
            f"{len(summary['collision_windows'])} collision windows"
        )
    print(f"\nWrote gameplay-sizing dataset to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
