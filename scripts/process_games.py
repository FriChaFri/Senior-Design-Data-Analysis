#!/usr/bin/env python3
"""Trim raw game files and keep only conservative gameplay-focused sensor columns."""

from __future__ import annotations

from pathlib import Path

from imu_pipeline.game_processing import build_clean_games_dataset


def main() -> None:
    processed_dir = Path("data/processed/clean_games")
    manifest = build_clean_games_dataset(processed_dir=processed_dir)
    for stem, summary in manifest.items():
        print(f"{stem}: cleaned {summary['cleaned_rows']} rows from {summary['raw_rows']} raw rows")
    print(f"\nWrote cleaned games to {processed_dir.resolve()}")


if __name__ == "__main__":
    main()
