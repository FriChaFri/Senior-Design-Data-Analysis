from pathlib import Path

import pandas as pd

from imu_pipeline.game_processing import build_clean_games_dataset, ensure_raw_file_available
from imu_pipeline.io import TrimSpec


def test_ensure_raw_file_available_reconstructs_chunked_source(tmp_path: Path) -> None:
    repo_root = tmp_path
    source_dir = repo_root / "data" / "raw"
    source_dir.mkdir(parents=True, exist_ok=True)
    original = source_dir / "sample.csv"
    original.write_text("loggingTime(txt),value\n2026-03-24T17:00:00,1\n", encoding="utf-8")

    from imu_pipeline.chunked_data import chunk_file

    manifest_path = repo_root / "data" / "chunked" / "manifest.json"
    chunk_file(
        original,
        repo_root=repo_root,
        manifest_path=manifest_path,
        chunk_size_bytes=8,
        remove_source=True,
    )

    rebuilt = ensure_raw_file_available(
        "data/raw/sample.csv",
        repo_root=repo_root,
        chunk_manifest_path=Path("data/chunked/manifest.json"),
    )

    assert rebuilt == repo_root / "data" / "raw" / "sample.csv"
    assert rebuilt.read_text(encoding="utf-8").startswith("loggingTime(txt),value")


def test_build_clean_games_dataset_rebuilds_from_chunked_raw(tmp_path: Path) -> None:
    repo_root = tmp_path
    source_dir = repo_root / "data" / "raw"
    source_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(
        {
            "loggingTime(txt)": pd.date_range("2026-03-24T17:00:00", periods=6, freq="1min"),
            "loggingSample(N)": range(6),
            "accelerometerTimestamp_sinceReboot(s)": [0, 60, 120, 180, 240, 300],
            "accelerometerAccelerationX(G)": [0.0] * 6,
            "accelerometerAccelerationY(G)": [0.0] * 6,
            "accelerometerAccelerationZ(G)": [1.0] * 6,
            "gyroTimestamp_sinceReboot(s)": [0, 60, 120, 180, 240, 300],
            "gyroRotationX(rad/s)": [0.0] * 6,
            "gyroRotationY(rad/s)": [0.0] * 6,
            "gyroRotationZ(rad/s)": [0.0] * 6,
            "motionTimestamp_sinceReboot(s)": [0, 60, 120, 180, 240, 300],
            "motionRotationRateX(rad/s)": [0.0] * 6,
            "motionRotationRateY(rad/s)": [0.0] * 6,
            "motionRotationRateZ(rad/s)": [0.0] * 6,
            "motionUserAccelerationX(G)": [0.0] * 6,
            "motionUserAccelerationY(G)": [0.0] * 6,
            "motionUserAccelerationZ(G)": [0.0] * 6,
            "motionGravityX(G)": [0.0] * 6,
            "motionGravityY(G)": [0.0] * 6,
            "motionGravityZ(G)": [1.0] * 6,
        }
    )
    source_path = source_dir / "Game1CharlesPhone.csv"
    frame.to_csv(source_path, index=False)

    from imu_pipeline.chunked_data import chunk_file

    manifest_path = repo_root / "data" / "chunked" / "manifest.json"
    chunk_file(
        source_path,
        repo_root=repo_root,
        manifest_path=manifest_path,
        chunk_size_bytes=64,
        remove_source=True,
    )

    trim_specs = {"Game1CharlesPhone": TrimSpec(keep_start_min=1.0, keep_end_min=4.0)}
    manifest = build_clean_games_dataset(
        repo_root=repo_root,
        raw_dir=Path("data/raw"),
        processed_dir=Path("data/processed/clean_games"),
        chunk_manifest_path=Path("data/chunked/manifest.json"),
        trim_specs=trim_specs,
    )

    cleaned_path = repo_root / "data" / "processed" / "clean_games" / "Game1CharlesPhone_clean.csv"
    cleaned = pd.read_csv(cleaned_path)

    assert (repo_root / "data" / "raw" / "Game1CharlesPhone.csv").exists()
    assert cleaned.shape[0] == 3
    assert manifest["Game1CharlesPhone"]["cleaned_rows"] == 3


def test_ensure_raw_file_available_rebuilds_invalid_existing_file(tmp_path: Path) -> None:
    repo_root = tmp_path
    source_dir = repo_root / "data" / "raw"
    source_dir.mkdir(parents=True, exist_ok=True)
    original = source_dir / "sample.csv"
    original.write_text("loggingTime(txt),value\n2026-03-24T17:00:00,1\n", encoding="utf-8")

    from imu_pipeline.chunked_data import chunk_file

    manifest_path = repo_root / "data" / "chunked" / "manifest.json"
    chunk_file(
        original,
        repo_root=repo_root,
        manifest_path=manifest_path,
        chunk_size_bytes=8,
        remove_source=True,
    )

    rebuilt_once = ensure_raw_file_available(
        "data/raw/sample.csv",
        repo_root=repo_root,
        chunk_manifest_path=Path("data/chunked/manifest.json"),
    )
    rebuilt_once.write_text("corrupted\n", encoding="utf-8")

    rebuilt_twice = ensure_raw_file_available(
        "data/raw/sample.csv",
        repo_root=repo_root,
        chunk_manifest_path=Path("data/chunked/manifest.json"),
    )

    assert rebuilt_twice.read_text(encoding="utf-8").startswith("loggingTime(txt),value")
