# Copyright (c) 2026 Gurov

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


class TokenType(Enum):
    USE = auto()
    KEYWORD = auto()


@dataclass
class ConfigLine:
    package: str | None = None
    flat_flags: list[str] = field(default_factory=list)
    grouped_flags: list[tuple[str, list[str]]] = field(default_factory=list)
    comment: str | None = None
    _raw_line: str | None = field(default=None, compare=False)

    def invalidate(self) -> None:
        self._raw_line = None


@dataclass
class ConfigFile:
    path: Path
    parsed_lines: list[ConfigLine]
    modified: bool = False
