import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_manager.filename_translation import (
    FilenameTranslationService,
    TranslationRenameCandidate,
    contains_japanese_filename_text,
    is_japanese_text,
    load_env_value,
    sanitize_filename_component,
)


def test_is_japanese_text_detects_japanese():
    assert is_japanese_text("旅行メモ")


def test_is_japanese_text_rejects_english():
    assert not is_japanese_text("holiday_photo")


def test_is_japanese_text_rejects_chinese():
    """漢字のみのテキストは中国語の可能性があるため日本語と判定しない。"""
    assert not is_japanese_text("旅行照片")
    assert not is_japanese_text("文件管理器")


def test_is_japanese_text_detects_mixed_kana():
    """ひらがな・カタカナが含まれていれば日本語と判定する。"""
    assert is_japanese_text("旅行の写真")
    assert is_japanese_text("ファイル管理")


def test_is_japanese_text_rejects_cjk_with_middle_dot_only():
    """中黒だけで日本語扱いしない。"""
    assert not is_japanese_text("中文・示例")


def test_is_japanese_text_detects_halfwidth_katakana():
    """半角カナを含む場合は日本語扱いする。"""
    assert is_japanese_text("ﾌｧｲﾙ管理")


def test_sanitize_filename_component_removes_invalid_chars():
    assert sanitize_filename_component('旅:行*?"') == "旅行"


def test_load_env_value_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TRANSLATION_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.delenv("TRANSLATION_API_KEY", raising=False)

    assert load_env_value("TRANSLATION_API_KEY", env_path=env_file) == "test-key"


def test_translate_paths_preserves_extension(tmp_path):
    source = tmp_path / "hello.txt"
    source.write_text("x", encoding="utf-8")

    service = FilenameTranslationService(
        "dummy",
        translate_backend=lambda text, target, api_key: {
            "translated_text": "こんにちは",
            "source_language": "en",
        },
    )

    result = service.translate_paths([source])[0]

    assert result.translated_name == "こんにちは.txt"
    assert result.status == "ready"


def test_translate_paths_normalizes_japanese_translation(tmp_path):
    source = tmp_path / "meeting_notes.txt"
    source.write_text("x", encoding="utf-8")

    service = FilenameTranslationService(
        "dummy",
        translate_backend=lambda text, target, api_key: {
            "translated_text": "Japanese: &quot;会議メモ&quot;",
            "source_language": "en",
        },
    )

    result = service.translate_paths([source])[0]

    assert result.translated_name == "会議メモ.txt"
    assert result.status == "ready"


def test_translate_paths_rejects_non_japanese_translation(tmp_path):
    source = tmp_path / "meeting_notes.txt"
    source.write_text("x", encoding="utf-8")

    service = FilenameTranslationService(
        "dummy",
        translate_backend=lambda text, target, api_key: {
            "translated_text": "meeting notes",
            "source_language": "en",
        },
    )

    result = service.translate_paths([source])[0]

    assert result.translated_name == source.name
    assert result.status == "error_invalid_name"


def test_contains_japanese_filename_text_accepts_kanji_only():
    assert contains_japanese_filename_text("会議記録")


def test_translate_paths_skips_japanese(tmp_path):
    source = tmp_path / "にほんご.txt"
    source.write_text("x", encoding="utf-8")

    service = FilenameTranslationService("dummy")
    result = service.translate_paths([source])[0]

    assert result.status == "skipped_japanese"


def test_translate_paths_skips_source_detected_as_japanese(tmp_path):
    source = tmp_path / "請求書.txt"
    source.write_text("x", encoding="utf-8")
    service = FilenameTranslationService(
        "dummy",
        translate_backend=lambda text, target, api_key: {
            "translated_text": "請求書",
            "source_language": "ja",
        },
    )

    result = service.translate_paths([source])[0]

    assert result.status == "skipped_japanese"
    assert result.translated_name == source.name


def test_translate_paths_appends_sequence_number_for_existing_file(tmp_path):
    source = tmp_path / "hello.txt"
    source.write_text("x", encoding="utf-8")
    existing = tmp_path / "こんにちは.txt"
    existing.write_text("x", encoding="utf-8")

    service = FilenameTranslationService(
        "dummy",
        translate_backend=lambda text, target, api_key: {
            "translated_text": "こんにちは",
            "source_language": "en",
        },
    )

    result = service.translate_paths([source])[0]

    assert result.status == "ready"
    assert result.translated_name == "こんにちは(1).txt"


def test_translate_paths_appends_sequence_number_between_candidates(tmp_path):
    source1 = tmp_path / "hello.txt"
    source2 = tmp_path / "world.txt"
    source1.write_text("x", encoding="utf-8")
    source2.write_text("x", encoding="utf-8")

    service = FilenameTranslationService(
        "dummy",
        translate_backend=lambda text, target, api_key: {
            "translated_text": "同じ名前",
            "source_language": "en",
        },
    )

    results = service.translate_paths([source1, source2])

    assert {result.status for result in results} == {"ready"}
    assert {result.translated_name for result in results} == {
        "同じ名前.txt",
        "同じ名前(1).txt",
    }


def test_translate_paths_returns_api_error_and_logs_cause_when_backend_fails(
    caplog, tmp_path
):
    source = tmp_path / "hello.txt"
    source.write_text("x", encoding="utf-8")

    def failing_backend(text, target, api_key):
        raise RuntimeError("network")

    service = FilenameTranslationService("dummy", translate_backend=failing_backend)
    with caplog.at_level(logging.ERROR, logger="file_manager"):
        result = service.translate_paths([source])[0]

    assert result.status == "error_api"
    assert "ファイル名の日本語翻訳に失敗しました" in caplog.text
    assert "backend=google" in caplog.text
    assert str(source) in caplog.text
    assert "RuntimeError: network" in caplog.text


def test_translation_candidate_ready_property():
    candidate = TranslationRenameCandidate(
        source_path=Path("sample.txt"),
        original_name="sample.txt",
        translated_name="翻訳.txt",
        source_language="en",
        status="ready",
    )

    assert candidate.is_ready is True
