#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ファイル名類似度検出機能のテスト"""

import os
import tempfile
from pathlib import Path

import pytest

from src.file_manager.filename_similarity import (
    SimilarFileGroup,
    calculate_similarity,
    calculate_size_similarity,
    calculate_combined_similarity,
    extract_number_pattern,
    find_similar_filenames,
    is_video_file,
    normalize_filename,
)


class TestNormalizeFilename:
    """ファイル名正規化のテスト"""

    def test_lowercase_conversion(self):
        assert normalize_filename("VIDEO.mp4") == "video"
        assert normalize_filename("MyFile.avi") == "myfile"

    def test_remove_extension(self):
        assert normalize_filename("test.mp4") == "test"
        assert normalize_filename("video.avi") == "video"

    def test_normalize_separators(self):
        assert normalize_filename("my-video_file.mp4") == "my_video_file"
        assert normalize_filename("my  video  file.mp4") == "my_video_file"

    def test_remove_brackets(self):
        assert normalize_filename("video (copy).mp4") == "video"
        assert normalize_filename("video [backup].mp4") == "video"
        assert normalize_filename("video (1) [copy].mp4") == "video"

    def test_consecutive_underscores(self):
        assert normalize_filename("my___video.mp4") == "my_video"


class TestCalculateSimilarity:
    """類似度計算のテスト"""

    def test_identical_names(self):
        similarity = calculate_similarity("video.mp4", "video.mp4")
        assert similarity == 1.0

    def test_similar_names(self):
        similarity = calculate_similarity("video_01.mp4", "video_02.mp4")
        assert similarity > 0.8

    def test_different_names(self):
        similarity = calculate_similarity("abc.mp4", "xyz.mp4")
        assert similarity < 0.5

    def test_copy_variants(self):
        similarity = calculate_similarity("video.mp4", "video (copy).mp4")
        assert similarity > 0.8


class TestExtractNumberPattern:
    """数字パターン抽出のテスト"""

    def test_single_number(self):
        pattern, numbers = extract_number_pattern("video_01.mp4")
        assert pattern == "video_#"
        assert numbers == [1]

    def test_multiple_numbers(self):
        pattern, numbers = extract_number_pattern("video_2024_01.mp4")
        assert pattern == "video_#_#"
        assert numbers == [2024, 1]

    def test_no_numbers(self):
        pattern, numbers = extract_number_pattern("video.mp4")
        assert pattern == "video"
        assert numbers == []


class TestIsVideoFile:
    """動画ファイル判定のテスト"""

    def test_video_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_extensions = [".mp4", ".avi", ".mov", ".mkv"]
            for ext in video_extensions:
                file_path = Path(tmpdir) / f"test{ext}"
                file_path.touch()
                assert is_video_file(file_path)

    def test_non_video_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            non_video = [".txt", ".jpg", ".pdf"]
            for ext in non_video:
                file_path = Path(tmpdir) / f"test{ext}"
                file_path.touch()
                assert not is_video_file(file_path)

    def test_custom_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.custom"
            file_path.touch()
            assert is_video_file(file_path, extensions=[".custom"])


class TestFindSimilarFilenames:
    """類似ファイル検出のテスト"""

    def test_find_similar_videos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 類似する動画ファイルを作成
            files = [
                "video_01.mp4",
                "video_02.mp4",
                "video_03.mp4",
                "different.avi",
            ]
            for filename in files:
                (Path(tmpdir) / filename).touch()

            results = find_similar_filenames(
                tmpdir, recursive=False, similarity_threshold=0.7, min_group_size=2
            )

            # video_01, video_02, video_03 が1つのグループになるべき
            assert len(results) >= 1
            assert any(len(group.files) == 3 for group in results)

    def test_no_similar_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 全く異なるファイル名
            files = ["abc.mp4", "xyz.mp4", "def.mp4"]
            for filename in files:
                (Path(tmpdir) / filename).touch()

            results = find_similar_filenames(
                tmpdir, recursive=False, similarity_threshold=0.7, min_group_size=2
            )

            # 類似グループが見つからないはず
            assert len(results) == 0

    def test_min_group_size_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 2つだけ類似
            files = ["video_01.mp4", "video_02.mp4", "different.avi"]
            for filename in files:
                (Path(tmpdir) / filename).touch()

            # min_group_size=3 では見つからない
            results = find_similar_filenames(
                tmpdir, recursive=False, similarity_threshold=0.7, min_group_size=3
            )
            assert len(results) == 0

            # min_group_size=2 では見つかる
            results = find_similar_filenames(
                tmpdir, recursive=False, similarity_threshold=0.7, min_group_size=2
            )
            assert len(results) >= 1

    def test_recursive_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # サブディレクトリを作成
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            (Path(tmpdir) / "video_01.mp4").touch()
            (subdir / "video_02.mp4").touch()

            # recursive=False では1つのファイルしか見つからない
            results = find_similar_filenames(
                tmpdir, recursive=False, similarity_threshold=0.7, min_group_size=2
            )
            assert len(results) == 0

            # recursive=True では両方見つかる
            results = find_similar_filenames(
                tmpdir, recursive=True, similarity_threshold=0.7, min_group_size=2
            )
            assert len(results) >= 1


class TestSizeSimilarity:
    """サイズ類似度計算のテスト"""

    def test_identical_sizes(self):
        similarity = calculate_size_similarity(1000, 1000)
        assert similarity == 1.0

    def test_similar_sizes(self):
        similarity = calculate_size_similarity(1000, 900)
        assert 0.8 < similarity < 1.0

    def test_different_sizes(self):
        similarity = calculate_size_similarity(1000, 100)
        assert similarity == 0.1

    def test_zero_sizes(self):
        assert calculate_size_similarity(0, 0) == 1.0
        assert calculate_size_similarity(0, 100) == 0.0
        assert calculate_size_similarity(100, 0) == 0.0


class TestCombinedSimilarity:
    """ファイル名とサイズの複合類似度のテスト"""

    def test_both_similar(self):
        similarity = calculate_combined_similarity(
            "video_01.mp4", "video_02.mp4", 1000, 1010, name_weight=0.7, size_weight=0.3
        )
        assert similarity > 0.8

    def test_name_similar_size_different(self):
        similarity = calculate_combined_similarity(
            "video_01.mp4", "video_02.mp4", 1000, 5000, name_weight=0.7, size_weight=0.3
        )
        # ファイル名は類似しているがサイズが異なる
        assert 0.5 < similarity < 0.9

    def test_name_different_size_similar(self):
        similarity = calculate_combined_similarity(
            "abc.mp4", "xyz.mp4", 1000, 1010, name_weight=0.7, size_weight=0.3
        )
        # サイズは類似しているがファイル名が異なる
        assert similarity < 0.5


class TestSimilarFileGroup:
    """SimilarFileGroup データクラスのテスト"""

    def test_files_sorted(self):
        group = SimilarFileGroup(
            representative_name="test.mp4",
            files=["/path/c.mp4", "/path/a.mp4", "/path/b.mp4"],
            similarity_score=0.95,
        )
        assert group.files == ["/path/a.mp4", "/path/b.mp4", "/path/c.mp4"]

    def test_dataclass_attributes(self):
        group = SimilarFileGroup(
            representative_name="video.mp4", files=["/path/video.mp4"], similarity_score=0.85
        )
        assert group.representative_name == "video.mp4"
        assert len(group.files) == 1
        assert group.similarity_score == 0.85

    def test_file_sizes(self):
        group = SimilarFileGroup(
            representative_name="test.mp4",
            files=["/path/a.mp4", "/path/b.mp4"],
            similarity_score=0.9,
            file_sizes={"/path/a.mp4": 1000, "/path/b.mp4": 1100},
        )
        assert group.get_average_size() == 1050

    def test_size_variance(self):
        group = SimilarFileGroup(
            representative_name="test.mp4",
            files=["/path/a.mp4", "/path/b.mp4", "/path/c.mp4"],
            similarity_score=0.9,
            file_sizes={"/path/a.mp4": 1000, "/path/b.mp4": 1000, "/path/c.mp4": 1000},
        )
        # すべて同じサイズなら分散は0
        assert group.get_size_variance() == 0.0


class TestFindSimilarFilenamesWithSize:
    """ファイルサイズ考慮した検索のテスト"""

    def test_size_based_grouping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # サイズの異なるファイルを作成
            files = [
                ("video_01.mp4", 1000),
                ("video_02.mp4", 1010),  # サイズが近い
                ("video_03.mp4", 5000),  # サイズが大きく異なる
            ]
            for filename, size in files:
                file_path = Path(tmpdir) / filename
                file_path.write_bytes(b"0" * size)

            # ファイルサイズを考慮した検索
            results = find_similar_filenames(
                tmpdir,
                recursive=False,
                similarity_threshold=0.7,
                min_group_size=2,
                use_file_size=True,
                size_weight=0.3,
            )

            # サイズが近い video_01 と video_02 がグループ化されるべき
            assert len(results) >= 1
            if len(results) > 0:
                # ファイルサイズ情報が含まれているか確認
                assert results[0].file_sizes is not None
                assert len(results[0].file_sizes) > 0

    def test_without_size_consideration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = [
                ("video_01.mp4", 1000),
                ("video_02.mp4", 5000),  # サイズが大きく異なる
            ]
            for filename, size in files:
                file_path = Path(tmpdir) / filename
                file_path.write_bytes(b"0" * size)

            # ファイルサイズを考慮しない検索
            results = find_similar_filenames(
                tmpdir,
                recursive=False,
                similarity_threshold=0.7,
                min_group_size=2,
                use_file_size=False,
            )

            # ファイル名だけで判断するので、サイズに関係なくグループ化される
            assert len(results) >= 1
