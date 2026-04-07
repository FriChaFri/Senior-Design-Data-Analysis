#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from imu_pipeline.chunked_data import (
    DEFAULT_CHUNK_SIZE_BYTES,
    chunk_file,
    reconstruct_all,
    reconstruct_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split oversized tracked data into GitHub-safe chunks and rebuild them later."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root used to resolve relative file paths.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/chunked/manifest.json"),
        help="Manifest path relative to the repository root.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    chunk_parser = subparsers.add_parser("chunk", help="Chunk one or more files.")
    chunk_parser.add_argument("paths", nargs="+", type=Path, help="Files to split into chunk parts.")
    chunk_parser.add_argument(
        "--chunk-size-bytes",
        type=int,
        default=DEFAULT_CHUNK_SIZE_BYTES,
        help="Maximum bytes to store in each chunk file.",
    )
    chunk_parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Keep the original file after creating chunk files.",
    )

    rebuild_parser = subparsers.add_parser("rebuild", help="Reconstruct chunked files.")
    rebuild_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional subset of original repo-relative files to rebuild.",
    )
    rebuild_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files when reconstructing.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    manifest_path = (repo_root / args.manifest).resolve()

    if args.command == "chunk":
        for path in args.paths:
            target_path = (repo_root / path).resolve()
            record = chunk_file(
                target_path,
                repo_root=repo_root,
                manifest_path=manifest_path,
                chunk_size_bytes=args.chunk_size_bytes,
                remove_source=not args.keep_source,
            )
            print(
                f"chunked {record.source_path} into {len(record.chunk_paths)} part(s) "
                f"at {manifest_path.parent.relative_to(repo_root)}"
            )
        return 0

    if args.paths:
        for path in args.paths:
            output_path = reconstruct_file(
                path,
                repo_root=repo_root,
                manifest_path=manifest_path,
                overwrite=args.overwrite,
            )
            print(f"rebuilt {output_path.relative_to(repo_root)}")
        return 0

    for output_path in reconstruct_all(
        repo_root=repo_root,
        manifest_path=manifest_path,
        overwrite=args.overwrite,
    ):
        print(f"rebuilt {output_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
