from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

StartupMode = Literal["last_session", "specific"]


@dataclass(slots=True)
class AppPreference:
    font_family: str
    font_size: int
    icon_size: int
    list_palette: dict[str, str]
    startup_mode: StartupMode
    startup_folder: Path | None
    index_db_path: Path

    def __post_init__(self) -> None:
        if self.startup_mode not in ("last_session", "specific"):
            raise ValueError(f"invalid startup_mode: {self.startup_mode}")
        if self.font_size <= 0:
            raise ValueError("font_size must be positive")
        if self.icon_size <= 0:
            raise ValueError("icon_size must be positive")
        if not self.list_palette:
            raise ValueError("list_palette must not be empty")
        object.__setattr__(self, "startup_folder", None if self.startup_folder is None else Path(self.startup_folder))
        object.__setattr__(self, "index_db_path", Path(self.index_db_path))


__all__ = ["AppPreference"]
