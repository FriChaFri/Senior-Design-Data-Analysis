"""Basic I/O helpers for dataset discovery and loading."""

from __future__ import annotations

from pathlib import Path


def iter_session_dirs(raw_root: str | Path = "data/raw") -> list[Path]:
    """Return session directories under the raw data root."""
    root = Path(raw_root)
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def load_csv(path: str | Path, device_id: str):
    """Load a CSV and stamp it with a device identifier."""
    import pandas as pd

    frame = pd.read_csv(path)
    frame["device_id"] = device_id
    return frame
