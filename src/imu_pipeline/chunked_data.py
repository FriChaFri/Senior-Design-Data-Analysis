from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CHUNK_SIZE_BYTES = 95_000_000
TEXT_RECONSTRUCT_SUFFIXES = {".csv"}


@dataclass(frozen=True)
class ChunkedFileRecord:
    source_path: str
    byte_size: int
    sha256: str
    chunk_size_bytes: int
    chunk_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "chunk_size_bytes": self.chunk_size_bytes,
            "chunk_paths": list(self.chunk_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ChunkedFileRecord":
        return cls(
            source_path=str(data["source_path"]),
            byte_size=int(data["byte_size"]),
            sha256=str(data["sha256"]),
            chunk_size_bytes=int(data["chunk_size_bytes"]),
            chunk_paths=tuple(str(path) for path in data["chunk_paths"]),
        )


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_chunk_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _write_reconstructed_bytes(
    destination_path: Path,
    *,
    repo_root: Path,
    chunk_paths: tuple[str, ...],
    normalize_text_newlines: bool,
) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with destination_path.open("wb") as handle:
        for chunk_rel in chunk_paths:
            chunk_bytes = (repo_root / chunk_rel).read_bytes()
            if normalize_text_newlines:
                chunk_bytes = chunk_bytes.replace(b"\r\n", b"\n")
            handle.write(chunk_bytes)


def _load_manifest(manifest_path: Path) -> dict[str, ChunkedFileRecord]:
    if not manifest_path.exists():
        return {}

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        str(record["source_path"]).replace("\\", "/"): ChunkedFileRecord.from_dict(record)
        for record in payload.get("files", [])
    }


def _write_manifest(manifest_path: Path, records: dict[str, ChunkedFileRecord]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "files": [
            records[key].to_dict()
            for key in sorted(records)
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_manifest_records(manifest_path: Path) -> dict[str, ChunkedFileRecord]:
    """Return chunk manifest records keyed by repo-relative source path."""

    return _load_manifest(manifest_path)


def _resolve_repo_relative_path(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    repo_root = repo_root.resolve()
    try:
        return resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"{path} is outside repository root {repo_root}") from exc


def file_matches_record(path: Path, record: ChunkedFileRecord) -> bool:
    """Return True when an on-disk file matches the manifest byte size and hash."""

    if not path.is_file():
        return False
    if path.stat().st_size != record.byte_size:
        return False
    return _sha256_for_file(path) == record.sha256


def chunk_file(
    source_path: Path,
    *,
    repo_root: Path,
    manifest_path: Path,
    chunk_size_bytes: int = DEFAULT_CHUNK_SIZE_BYTES,
    remove_source: bool = True,
) -> ChunkedFileRecord:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    source_path = source_path.resolve()
    source_rel = _resolve_repo_relative_path(source_path, repo_root)
    chunk_dir = manifest_path.parent / source_rel.parent / f"{source_rel.name}.parts"
    source_rel_key = source_rel.as_posix()

    if chunk_size_bytes <= 0:
        raise ValueError("chunk_size_bytes must be positive")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    _clean_chunk_dir(chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunk_paths: list[str] = []
    part_index = 0
    with source_path.open("rb") as handle:
        while True:
            data = handle.read(chunk_size_bytes)
            if not data:
                break

            part_path = chunk_dir / f"part-{part_index:04d}"
            part_path.write_bytes(data)
            chunk_paths.append(
                part_path.relative_to(repo_root).as_posix()
            )
            part_index += 1

    record = ChunkedFileRecord(
        source_path=source_rel_key,
        byte_size=source_path.stat().st_size,
        sha256=_sha256_for_file(source_path),
        chunk_size_bytes=chunk_size_bytes,
        chunk_paths=tuple(chunk_paths),
    )

    records = _load_manifest(manifest_path)
    records[record.source_path] = record
    _write_manifest(manifest_path, records)

    if remove_source:
        source_path.unlink()

    # Drop empty source directories when the chunk store already mirrors the path.
    source_parent = source_path.parent
    while source_parent != repo_root and source_parent.exists():
        try:
            source_parent.rmdir()
        except OSError:
            break
        source_parent = source_parent.parent

    return record


def reconstruct_file(
    source_path: str | Path,
    *,
    repo_root: Path,
    manifest_path: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    source_rel = Path(source_path)
    source_rel_key = source_rel.as_posix()
    records = _load_manifest(manifest_path)
    record = records.get(source_rel_key)
    if record is None:
        raise KeyError(f"{source_rel_key} is not listed in {manifest_path}")

    destination_path = output_path or (repo_root / record.source_path)
    if destination_path.exists() and not overwrite:
        raise FileExistsError(destination_path)

    _write_reconstructed_bytes(
        destination_path,
        repo_root=repo_root,
        chunk_paths=record.chunk_paths,
        normalize_text_newlines=False,
    )
    if destination_path.stat().st_size == record.byte_size and _sha256_for_file(destination_path) == record.sha256:
        return destination_path

    if destination_path.suffix.lower() in TEXT_RECONSTRUCT_SUFFIXES:
        _write_reconstructed_bytes(
            destination_path,
            repo_root=repo_root,
            chunk_paths=record.chunk_paths,
            normalize_text_newlines=True,
        )
        if destination_path.stat().st_size == record.byte_size and _sha256_for_file(destination_path) == record.sha256:
            return destination_path

    if destination_path.stat().st_size != record.byte_size:
        raise ValueError(f"Unexpected file size for {destination_path}")
    if _sha256_for_file(destination_path) != record.sha256:
        raise ValueError(f"SHA256 mismatch for {destination_path}")

    return destination_path


def reconstruct_all(
    *,
    repo_root: Path,
    manifest_path: Path,
    overwrite: bool = False,
) -> list[Path]:
    records = _load_manifest(manifest_path)
    rebuilt: list[Path] = []
    for source_path in sorted(records):
        rebuilt.append(
            reconstruct_file(
                source_path,
                repo_root=repo_root,
                manifest_path=manifest_path,
                overwrite=overwrite,
            )
        )
    return rebuilt
