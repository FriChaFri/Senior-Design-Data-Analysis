"""Build trimmed gameplay datasets directly from raw or chunked raw files."""

from __future__ import annotations

import json
from pathlib import Path

from imu_pipeline.chunked_data import file_matches_record, load_manifest_records, reconstruct_file
from imu_pipeline.io import CORE_GAMEPLAY_COLUMNS, TrimSpec, TrimWindow, load_game_csv, trim_game_data


DEFAULT_CHUNK_MANIFEST_PATH = Path("data/chunked/manifest.json")


GAME_TRIM_SPECS: dict[str, TrimSpec] = {
    "Game1CharlesPhone": TrimSpec(
        keep_start_min=4.0,
        keep_end_min=57.5,
        remove_windows=(TrimWindow(14.5, 18.5),),
    ),
    "Game2CharlesPhone": TrimSpec(
        keep_start_min=1.0,
        keep_end_min=38.4,
        remove_windows=(),
    ),
}


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_raw_file_available(
    source_rel: str | Path,
    *,
    repo_root: Path | None = None,
    chunk_manifest_path: str | Path = DEFAULT_CHUNK_MANIFEST_PATH,
    overwrite: bool = False,
) -> Path:
    """Return a raw file path, reconstructing it from chunked data when needed."""

    repo_root = (repo_root or _default_repo_root()).resolve()
    source_rel = Path(source_rel)
    target_path = repo_root / source_rel
    manifest_path = (repo_root / chunk_manifest_path).resolve()
    record = load_manifest_records(manifest_path).get(source_rel.as_posix())
    if target_path.exists() and not overwrite:
        if record is None or file_matches_record(target_path, record):
            return target_path

    return reconstruct_file(
        source_rel,
        repo_root=repo_root,
        manifest_path=manifest_path,
        overwrite=target_path.exists() or overwrite,
    )


def build_cleaning_manifest(raw_rows: int, cleaned_rows: int, spec: TrimSpec) -> dict[str, object]:
    """Build a JSON-safe record of the cleaning decisions."""

    return {
        "kept_window_minutes": {
            "start": spec.keep_start_min,
            "end": spec.keep_end_min,
        },
        "removed_windows_minutes": [
            {"start": window.start_min, "end": window.end_min}
            for window in spec.remove_windows
        ],
        "raw_rows": raw_rows,
        "cleaned_rows": cleaned_rows,
        "rows_removed": raw_rows - cleaned_rows,
        "columns_kept": CORE_GAMEPLAY_COLUMNS + ["elapsed_min_from_trim_start"],
    }


def build_clean_games_dataset(
    *,
    repo_root: Path | None = None,
    raw_dir: str | Path = "data/raw",
    processed_dir: str | Path = "data/processed/clean_games",
    chunk_manifest_path: str | Path = DEFAULT_CHUNK_MANIFEST_PATH,
    trim_specs: dict[str, TrimSpec] | None = None,
) -> dict[str, dict[str, object]]:
    """Regenerate cleaned gameplay CSVs from raw source data."""

    repo_root = (repo_root or _default_repo_root()).resolve()
    raw_root = (repo_root / raw_dir).resolve()
    processed_root = (repo_root / processed_dir).resolve()
    processed_root.mkdir(parents=True, exist_ok=True)

    selected_specs = trim_specs or GAME_TRIM_SPECS
    manifest: dict[str, dict[str, object]] = {}
    for stem, spec in selected_specs.items():
        raw_path = ensure_raw_file_available(
            raw_root.relative_to(repo_root) / f"{stem}.csv",
            repo_root=repo_root,
            chunk_manifest_path=chunk_manifest_path,
        )
        game = load_game_csv(raw_path, columns=CORE_GAMEPLAY_COLUMNS)
        cleaned = trim_game_data(game, spec)
        cleaned["loggingTime(txt)"] = cleaned["loggingTime(txt)"].dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        cleaned.to_csv(processed_root / f"{stem}_clean.csv", index=False)
        manifest[stem] = build_cleaning_manifest(len(game), len(cleaned), spec)

    (processed_root / "cleaning_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
