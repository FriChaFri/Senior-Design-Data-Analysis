from pathlib import Path

from imu_pipeline.io import iter_session_dirs


def test_iter_session_dirs_returns_sorted_directories(tmp_path: Path) -> None:
    (tmp_path / "b_session").mkdir()
    (tmp_path / "a_session").mkdir()
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    result = iter_session_dirs(tmp_path)

    assert [path.name for path in result] == ["a_session", "b_session"]
