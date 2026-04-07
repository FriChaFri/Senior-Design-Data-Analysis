import pandas as pd

from imu_pipeline.gameplay_dataset import build_collision_trimmed_game, detect_collision_windows


def test_detect_collision_windows_clusters_and_merges_padding() -> None:
    frame = pd.DataFrame(
        {
            "loggingTime(txt)": pd.date_range("2026-04-01T12:00:00", periods=8, freq="250ms"),
            "motionUserAccelerationX(G)": [0.0, 0.0, 5.0, 0.0, 4.5, 0.0, 0.0, 0.0],
            "motionUserAccelerationY(G)": [0.0] * 8,
            "motionUserAccelerationZ(G)": [0.0] * 8,
        }
    )

    windows = detect_collision_windows(
        frame,
        magnitude_threshold_m_s2=40.0,
        cluster_gap_s=0.5,
        padding_s=0.5,
    )

    assert len(windows) == 1
    assert windows[0].peak_accel_m_s2 > 40.0
    assert windows[0].start_min == 0.0
    assert windows[0].end_min > 0.02


def test_build_collision_trimmed_game_compresses_removed_window() -> None:
    frame = pd.DataFrame(
        {
            "loggingTime(txt)": pd.to_datetime(
                [
                    "2026-04-01T12:00:00",
                    "2026-04-01T12:00:01",
                    "2026-04-01T12:00:02",
                    "2026-04-01T12:00:03",
                    "2026-04-01T12:00:04",
                ]
            ),
            "motionUserAccelerationX(G)": [0.0] * 5,
            "motionUserAccelerationY(G)": [0.0] * 5,
            "motionUserAccelerationZ(G)": [0.0] * 5,
        }
    )

    trimmed = build_collision_trimmed_game(
        frame,
        windows=[],
    )
    assert len(trimmed) == 5

    trimmed = build_collision_trimmed_game(
        frame,
        windows=[
            type(
                "Window",
                (),
                {"start_min": 1.5 / 60.0, "end_min": 3.5 / 60.0},
            )(),
        ],
    )

    assert len(trimmed) == 3
    assert trimmed["elapsed_min_from_trim_start"].tolist() == [0.0, 1.0 / 60.0, 2.0 / 60.0]
