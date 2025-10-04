from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal


ScopeLiteral = Literal["current", "all"]
DuplicateReason = Literal["hash", "name", "duration"]


def _normalize_keywords(keywords: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for raw in keywords:
        stripped = raw.strip()
        if not stripped:
            continue
        normalized.append(stripped)
    return normalized


@dataclass(slots=True)
class SearchQuery:
    keywords: list[str]
    scope: ScopeLiteral = "current"
    case_sensitive: bool = False
    limit: int = 100

    def __post_init__(self) -> None:
        cleaned = _normalize_keywords(self.keywords)
        if not cleaned:
            raise ValueError("keywords must contain at least one non-empty value")
        object.__setattr__(self, "keywords", cleaned)
        if self.scope not in ("current", "all"):
            raise ValueError(f"invalid scope: {self.scope}")
        if self.limit <= 0:
            raise ValueError("limit must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "keywords": list(self.keywords),
            "scope": self.scope,
            "case_sensitive": self.case_sensitive,
            "limit": self.limit,
        }


@dataclass(slots=True)
class SearchResultItem:
    path: Path
    name: str
    matched_field: str
    score: float | None = None
    directory: Path = field(init=False)

    def __post_init__(self) -> None:
        path_obj = Path(self.path)
        object.__setattr__(self, "path", path_obj)
        object.__setattr__(self, "directory", path_obj.parent)

    def to_json(self) -> str:
        payload = {
            "path": str(self.path),
            "name": self.name,
            "matched_field": self.matched_field,
            "score": self.score,
        }
        return json.dumps(payload, ensure_ascii=False)


@dataclass(slots=True)
class DuplicateEntry:
    path: Path
    size: int
    duration_seconds: float | None
    hash_value: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.size < 0:
            raise ValueError("size must be non-negative")


@dataclass(slots=True)
class DuplicateGroup:
    group_id: str
    files: list[DuplicateEntry]
    reason: DuplicateReason

    def __post_init__(self) -> None:
        if self.reason not in ("hash", "name", "duration"):
            raise ValueError(f"invalid reason: {self.reason}")
        if not self.files:
            raise ValueError("DuplicateGroup requires at least one entry")
        # Normalize ordering for deterministic behaviour
        sorted_files = sorted(self.files, key=lambda entry: str(entry.path))
        object.__setattr__(self, "files", sorted_files)


@dataclass(slots=True)
class DiskUsageNode:
    path: Path
    display_name: str
    size_bytes: int
    children: list["DiskUsageNode"] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")

    def add_child(self, child: "DiskUsageNode") -> None:
        self.children.append(child)

    @property
    def total_size(self) -> int:
        return self.size_bytes + sum(child.total_size for child in self.children)


@dataclass(slots=True)
class DigestRequest:
    source_path: Path
    thumbnail_count: int
    clip_length: float
    output_dir: Path | None = None

    def __post_init__(self) -> None:
        source = Path(self.source_path)
        object.__setattr__(self, "source_path", source)
        default_output = source.parent
        output = Path(self.output_dir) if self.output_dir is not None else default_output
        object.__setattr__(self, "output_dir", output)
        if self.thumbnail_count <= 0:
            raise ValueError("thumbnail_count must be positive")
        if self.clip_length <= 0:
            raise ValueError("clip_length must be positive")


__all__ = [
    "SearchQuery",
    "SearchResultItem",
    "DuplicateEntry",
    "DuplicateGroup",
    "DiskUsageNode",
    "DigestRequest",
]
