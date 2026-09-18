"""ファイル名翻訳サービス。"""

from __future__ import annotations

import json
import os
import re
from html import unescape
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from urllib import error, parse, request

from .logger import logger

INVALID_FILENAME_CHARS = '\\/:*?"<>|'
TRANSLATION_API_ENV_KEY = "TRANSLATION_API_KEY"
TRANSLATION_BACKEND_ENV_KEY = "TRANSLATION_BACKEND"
OLLAMA_MODEL_ENV_KEY = "OLLAMA_MODEL"
GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "gemma2:2b"

JAPANESE_RANGES = (
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
)

KANA_RANGES = (
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
)

HIRAGANA_LETTER_RANGES = (
    (0x3041, 0x3096),  # ぁ-ゖ
    (0x309D, 0x309F),  # ゝゞゟ
)

KATAKANA_LETTER_RANGES = (
    (0x30A1, 0x30FA),  # ァ-ヺ
    (0x30FD, 0x30FF),  # ヽヾヿ
    (0x31F0, 0x31FF),  # Katakana Phonetic Extensions
    (0xFF66, 0xFF9D),  # Halfwidth Katakana
)

TEXT_CHAR_RANGES = JAPANESE_RANGES + (
    (0x0041, 0x005A),  # A-Z
    (0x0061, 0x007A),  # a-z
    (0x00C0, 0x024F),  # Latin Extended
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x04FF),  # Cyrillic
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0x3400, 0x4DBF),  # CJK Extension A
)


@dataclass(frozen=True)
class TranslationRenameCandidate:
    """翻訳後リネーム候補。"""

    source_path: Path
    original_name: str
    translated_name: str
    source_language: str | None
    status: str
    message: str = ""

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"


TranslateBackend = Callable[[str, str, str], dict[str, str | None]]


def _is_char_in_ranges(char: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in ranges)


def contains_meaningful_text(text: str) -> bool:
    """翻訳対象になりうる文字列か判定する。"""
    return any(_is_char_in_ranges(char, TEXT_CHAR_RANGES) for char in text)


def is_japanese_text(text: str) -> bool:
    """日本語主体かどうかを保守的に判定する。

    誤判定を避けるため、漢字だけでは日本語扱いしない。
    ひらがな・カタカナの実文字が含まれる場合のみ日本語とみなす。
    `・` や `ー` のような記号だけでは日本語扱いしない。
    """
    has_hiragana = any(_is_char_in_ranges(char, HIRAGANA_LETTER_RANGES) for char in text)
    has_katakana = any(_is_char_in_ranges(char, KATAKANA_LETTER_RANGES) for char in text)
    return has_hiragana or has_katakana


def contains_japanese_filename_text(text: str) -> bool:
    """日本語ファイル名として使える文字を含むかを判定する。"""
    return any(_is_char_in_ranges(char, JAPANESE_RANGES) for char in text)


def sanitize_filename_component(component: str) -> str:
    """OS 非対応文字を除去してファイル名として使える形にする。"""
    sanitized = "".join(char for char in component if char not in INVALID_FILENAME_CHARS)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    sanitized = sanitized.rstrip(". ")
    return sanitized


def has_invalid_filename_component(component: str) -> bool:
    """ファイル名として問題のある文字列かどうか。"""
    if not component or component in {".", ".."}:
        return True
    if any(char in INVALID_FILENAME_CHARS for char in component):
        return True
    if any(ord(char) < 32 for char in component):
        return True
    if component != component.rstrip(". "):
        return True
    return False


def load_env_value(key: str, env_path: Path | None = None) -> str:
    """環境変数または `.env` から値を読む。"""
    env_value = os.getenv(key)
    if env_value:
        return env_value

    resolved_env_path = env_path or Path(__file__).resolve().parents[2] / ".env"
    if not resolved_env_path.exists():
        return ""

    for raw_line in resolved_env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        parsed_value = value.strip().strip('"').strip("'")
        if parsed_value:
            return parsed_value
    return ""


class FilenameTranslationService:
    """ファイル名翻訳サービス。"""

    def __init__(
        self,
        api_key: str,
        *,
        translate_backend: TranslateBackend | None = None,
        backend_type: str = "google",
    ) -> None:
        self.api_key = api_key
        self.backend_type = backend_type
        self._translate_backend = translate_backend or self._default_translate_backend

    @property
    def requires_api_key(self) -> bool:
        return self.backend_type != "ollama"

    @classmethod
    def from_env(
        cls,
        env_path: Path | None = None,
        *,
        translate_backend: TranslateBackend | None = None,
    ) -> "FilenameTranslationService":
        backend_type = load_env_value(TRANSLATION_BACKEND_ENV_KEY, env_path=env_path).lower()
        api_key = load_env_value(TRANSLATION_API_ENV_KEY, env_path=env_path)

        if translate_backend is None and backend_type == "ollama":
            model = load_env_value(OLLAMA_MODEL_ENV_KEY, env_path=env_path) or DEFAULT_OLLAMA_MODEL
            service = cls(api_key, backend_type="ollama")
            service._translate_backend = lambda text, target, key: service._ollama_translate_backend(
                text,
                target,
                model,
            )
            return service

        return cls(
            api_key,
            translate_backend=translate_backend,
            backend_type=backend_type or "google",
        )

    def _ollama_translate_backend(self, text: str, target_language: str, model: str) -> dict[str, str | None]:
        target_label = self._target_language_label(target_language)
        prompt = (
            f"Translate the following file name into natural, fluent {target_label}. "
            "The source text may be in Chinese, English, Korean, or another language, even if "
            "it happens to use kanji characters that superficially resemble Japanese — Chinese "
            "and Japanese are different languages, so do not just copy or reorder the source "
            "kanji as-is. Actually translate the meaning into authentic Japanese vocabulary and "
            "grammar. Keep alphanumeric product codes, usernames, and numbers unchanged. "
            "Output only the translated file name text. "
            "Do not include explanations, quotes, romanized text, source text, or prefixes. "
            "File name to translate:\n"
            f"{text}"
        )
        payload = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8")

        http_request = request.Request(
            OLLAMA_API_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=120) as response:
                body = response.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(
                f"Ollama に接続できませんでした。Ollama が起動しているか確認してください: {exc.reason}"
            ) from exc

        parsed = json.loads(body)
        response_text = self._normalize_translation_text(parsed.get("response", ""))
        return {
            "translated_text": response_text,
            "source_language": None,
        }

    @staticmethod
    def _target_language_label(target_language: str) -> str:
        language = (target_language or "").strip().lower()
        return {
            "ja": "Japanese",
            "jp": "Japanese",
            "japanese": "Japanese",
        }.get(language, target_language or "Japanese")

    @staticmethod
    def _normalize_translation_text(value) -> str:
        text = unescape(str(value or "")).strip().strip('"').strip("'").strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            text = lines[0]
        text = re.sub(r"^(?:Japanese|日本語|翻訳|Translation)\s*[:：]\s*", "", text, flags=re.IGNORECASE)
        return text.strip().strip('"').strip("'").strip()

    def translate_paths(
        self,
        paths: list[Path],
        target_language: str = "ja",
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> list[TranslationRenameCandidate]:
        """複数パスの翻訳候補を返す。"""
        candidates: list[TranslationRenameCandidate] = []
        total = len(paths)
        for i, path in enumerate(paths):
            if cancel_check and cancel_check():
                break
            candidates.append(self._build_candidate(Path(path), target_language))
            if progress_callback:
                progress_callback(i + 1, total)
        return self._apply_conflict_checks(candidates)

    def _build_candidate(self, path: Path, target_language: str) -> TranslationRenameCandidate:
        original_name = path.name
        if not path.exists() or not path.is_file():
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=None,
                status="skipped_not_file",
                message="ファイルのみ対象です。",
            )

        stem = path.stem
        suffix = path.suffix
        if not contains_meaningful_text(stem):
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=None,
                status="skipped_no_text",
                message="翻訳対象の文字がありません。",
            )

        if is_japanese_text(stem):
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language="ja",
                status="skipped_japanese",
                message="日本語名のためスキップしました。",
            )

        if self.requires_api_key and not self.api_key:
            logger.error(
                "ファイル名の日本語翻訳に失敗しました "
                "(backend=%s, path=%s, target_language=%s): APIキーが未設定です",
                self.backend_type,
                path,
                target_language,
            )
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=None,
                status="error_api",
                message="翻訳 API キーが設定されていません。",
            )

        try:
            translation_result = self._translate_backend(stem, target_language, self.api_key)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "ファイル名の日本語翻訳に失敗しました "
                "(backend=%s, path=%s, target_language=%s): %s",
                self.backend_type,
                path,
                target_language,
                exc,
            )
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=None,
                status="error_api",
                message=f"翻訳に失敗しました: {exc}",
            )

        translated_stem = sanitize_filename_component(
            self._normalize_translation_text(translation_result.get("translated_text"))
        )
        source_language = str(translation_result.get("source_language") or "") or None
        if source_language and source_language.casefold().split("-", 1)[0] == "ja":
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=source_language,
                status="skipped_japanese",
                message="翻訳サービスが日本語名と判定したためスキップしました。",
            )
        if not translated_stem:
            logger.error(
                "ファイル名の日本語翻訳に失敗しました "
                "(backend=%s, path=%s, target_language=%s, "
                "source_language=%s): 翻訳結果が空です (response=%r)",
                self.backend_type,
                path,
                target_language,
                source_language,
                translation_result.get("translated_text"),
            )
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=source_language,
                status="error_invalid_name",
                message="翻訳結果が空のため使用できません。",
            )

        if self._target_language_label(target_language) == "Japanese" and not contains_japanese_filename_text(
            translated_stem
        ):
            logger.error(
                "ファイル名の日本語翻訳に失敗しました "
                "(backend=%s, path=%s, target_language=%s, "
                "source_language=%s): 翻訳結果に日本語が含まれていません "
                "(response=%r)",
                self.backend_type,
                path,
                target_language,
                source_language,
                translated_stem,
            )
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=original_name,
                source_language=source_language,
                status="error_invalid_name",
                message="翻訳結果が日本語ではありません。",
            )

        translated_name = f"{translated_stem}{suffix}"
        if translated_name == original_name:
            return TranslationRenameCandidate(
                source_path=path,
                original_name=original_name,
                translated_name=translated_name,
                source_language=source_language,
                status="skipped_same_name",
                message="翻訳後の名前が元と同じです。",
            )

        return TranslationRenameCandidate(
            source_path=path,
            original_name=original_name,
            translated_name=translated_name,
            source_language=source_language,
            status="ready",
            message="翻訳候補を生成しました。",
        )

    def _apply_conflict_checks(
        self,
        candidates: list[TranslationRenameCandidate],
    ) -> list[TranslationRenameCandidate]:
        used_names: dict[Path, set[str]] = {}

        validated: list[TranslationRenameCandidate] = []
        for candidate in candidates:
            if not candidate.is_ready:
                validated.append(candidate)
                continue

            if has_invalid_filename_component(candidate.translated_name):
                validated.append(
                    replace(
                        candidate,
                        status="error_invalid_name",
                        message="翻訳後ファイル名が不正です。",
                    )
                )
                continue

            parent = candidate.source_path.parent
            reserved = used_names.setdefault(parent, set())
            unique_name = self._resolve_unique_filename(
                parent,
                candidate.translated_name,
                exclude_path=candidate.source_path,
                reserved=reserved,
            )
            reserved.add(unique_name)

            if unique_name != candidate.translated_name:
                validated.append(replace(candidate, translated_name=unique_name))
            else:
                validated.append(candidate)

        return validated

    @staticmethod
    def _resolve_unique_filename(
        parent: Path,
        name: str,
        *,
        exclude_path: Path,
        reserved: set[str],
    ) -> str:
        """同名ファイルが存在する場合、連番を付与して重複を回避する。"""
        stem = Path(name).stem
        suffix = Path(name).suffix

        candidate_name = name
        counter = 1
        while True:
            target_path = parent / candidate_name
            is_conflict = candidate_name in reserved or (
                target_path.exists() and target_path != exclude_path
            )
            if not is_conflict:
                return candidate_name
            candidate_name = f"{stem}({counter}){suffix}"
            counter += 1

    def _default_translate_backend(self, text: str, target_language: str, api_key: str) -> dict[str, str | None]:
        params = parse.urlencode(
            {
                "q": text,
                "target": target_language,
                "key": api_key,
                "format": "text",
            }
        )
        url = f"{GOOGLE_TRANSLATE_URL}?{params}"

        http_request = request.Request(url, method="POST")
        try:
            with request.urlopen(http_request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Google Translate API エラー: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Google Translate API に接続できませんでした: {exc.reason}") from exc

        payload = json.loads(body)
        translations = payload.get("data", {}).get("translations", [])
        if not translations:
            return {"translated_text": "", "source_language": None}

        first = translations[0]
        return {
            "translated_text": self._normalize_translation_text(first.get("translatedText")),
            "source_language": str(first.get("detectedSourceLanguage") or "") or None,
        }
