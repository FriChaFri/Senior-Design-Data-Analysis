from pathlib import Path

from imu_pipeline.chunked_data import chunk_file, reconstruct_file


def test_chunk_file_and_reconstruct_round_trip(tmp_path: Path) -> None:
    repo_root = tmp_path
    source_path = repo_root / "data" / "raw" / "sample.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    original_bytes = b"abcdefghijklmnopqrstuvwxyz"
    source_path.write_bytes(original_bytes)

    manifest_path = repo_root / "data" / "chunked" / "manifest.json"

    record = chunk_file(
        source_path,
        repo_root=repo_root,
        manifest_path=manifest_path,
        chunk_size_bytes=7,
        remove_source=True,
    )

    assert record.byte_size == len(original_bytes)
    assert not source_path.exists()
    assert len(record.chunk_paths) == 4

    rebuilt_path = reconstruct_file(
        "data/raw/sample.csv",
        repo_root=repo_root,
        manifest_path=manifest_path,
    )

    assert rebuilt_path == source_path
    assert rebuilt_path.read_bytes() == original_bytes


def test_reconstruct_csv_recovers_from_line_ending_normalization(tmp_path: Path) -> None:
    repo_root = tmp_path
    source_path = repo_root / "data" / "raw" / "sample.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    original_bytes = b"alpha\nbeta\ngamma\n"
    source_path.write_bytes(original_bytes)

    manifest_path = repo_root / "data" / "chunked" / "manifest.json"
    record = chunk_file(
        source_path,
        repo_root=repo_root,
        manifest_path=manifest_path,
        chunk_size_bytes=5,
        remove_source=True,
    )

    for chunk_rel in record.chunk_paths:
        chunk_path = repo_root / chunk_rel
        chunk_path.write_bytes(chunk_path.read_bytes().replace(b"\n", b"\r\n"))

    rebuilt_path = reconstruct_file(
        "data/raw/sample.csv",
        repo_root=repo_root,
        manifest_path=manifest_path,
    )

    assert rebuilt_path.read_bytes() == original_bytes
