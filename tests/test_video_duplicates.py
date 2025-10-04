import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_manager.video_duplicates import find_duplicate_videos


def test_find_duplicate_videos_detects_duplicates(tmp_path):
    target_dir = tmp_path / "videos"
    target_dir.mkdir()

    file1 = target_dir / "movie_a.mp4"
    file2 = target_dir / "movie_b.mp4"
    file3 = target_dir / "clip.mkv"
    file4 = target_dir / "unique.mp4"

    file1.write_bytes(b"sample-data")
    file2.write_bytes(b"sample-data")
    file3.write_bytes(b"sample-data")
    file4.write_bytes(b"different")

    duplicates = find_duplicate_videos(str(target_dir))

    assert len(duplicates) == 1
    group = duplicates[0]
    assert group.size == len(b"sample-data")
    assert {Path(p).name for p in group.files} == {"movie_a.mp4", "movie_b.mp4", "clip.mkv"}


def test_find_duplicate_videos_reports_progress(tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()

    (folder / "a.mp4").write_bytes(b"x" * 1024)
    (folder / "b.mp4").write_bytes(b"x" * 1024)

    progress_values = []

    def on_progress(value: int) -> None:
        progress_values.append(value)

    find_duplicate_videos(str(folder), progress_callback=on_progress)

    assert progress_values
    assert 100 in progress_values
    assert all(0 <= v <= 100 for v in progress_values)


def test_find_duplicate_videos_can_stop(tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()

    for index in range(5):
        (folder / f"file_{index}.mp4").write_bytes(b"data" + bytes([index]))

    stop_calls = {"count": 0}

    def should_stop() -> bool:
        stop_calls["count"] += 1
        return stop_calls["count"] > 1

    result = find_duplicate_videos(str(folder), stop_callback=should_stop)

    assert result == []
    assert stop_calls["count"] >= 2


def test_find_duplicate_videos_keeps_symlink_paths(tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()

    original = folder / "base.mp4"
    original.write_bytes(b"content")
    symlink_path = folder / "alias.mp4"

    try:
        os.symlink(original, symlink_path)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")

    duplicates = find_duplicate_videos(str(folder), recursive=False)

    assert duplicates
    names = {Path(p).name for p in duplicates[0].files}
    assert names == {"base.mp4", "alias.mp4"}

