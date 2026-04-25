# Copyright (c) 2026 Gurov

from __future__ import annotations

import logging
import re
import shutil
import tempfile

from pathlib import Path
from typing import Callable, Generator, Iterable

from flagger.models import ConfigFile, ConfigLine, TokenType


CONFIG_FILENAMES = {
    TokenType.USE: "package.use",
    TokenType.KEYWORD: "package.accept_keywords",
}

COMMENT_RE = re.compile(r"(?<!\S)#(.*)$")
LOCAL_CONFIG_NAME = "99local.conf"


def render_config_line(line: ConfigLine) -> str:
    parts: list[str] = []
    if line.package is not None:
        parts.append(line.package)
    parts.extend(line.flat_flags)
    for group, flags in line.grouped_flags:
        parts.append(f"{group}:")
        parts.extend(flags)
    if line.comment is not None:
        parts.append(f"#{line.comment}")
    return " ".join(parts) + "\n"


def ensure_local_config(path: Path) -> Path:
    if path.is_dir():
        local_path = path / LOCAL_CONFIG_NAME
        local_path.touch(exist_ok=True)
        return local_path

    if not path.exists():
        path.mkdir(parents=True)
        local_path = path / LOCAL_CONFIG_NAME
        local_path.touch()
        return local_path

    return path


def resolve_config_path(path: Path, *, create: bool) -> Path:
    if create:
        return ensure_local_config(path)
    if path.is_dir():
        return path / LOCAL_CONFIG_NAME
    return path


def find_config_files(config_root: Path, token_type: TokenType, *, create: bool = True) -> list[Path]:
    path = config_root / "etc/portage" / CONFIG_FILENAMES[token_type]
    return [resolve_config_path(path, create=create)]


def parse_config_lines(lines: list[str]) -> Generator[ConfigLine, None, None]:
    for raw_line in lines:
        line = raw_line.rstrip()
        comment_match = COMMENT_RE.search(line)
        if comment_match is not None:
            line = line[:comment_match.start()]

        fields = line.split()
        current_group: tuple[str, list[str]] = ("", [])
        groups = [current_group]
        for field in fields[1:]:
            if field.endswith(":"):
                current_group = (field[:-1], [])
                groups.append(current_group)
                continue
            current_group[1].append(field)

        yield ConfigLine(
            package=fields[0] if fields else None,
            flat_flags=groups[0][1],
            grouped_flags=groups[1:],
            comment=comment_match.group(1) if comment_match is not None else None,
            _raw_line=raw_line,
        )


def read_config_files(paths: Iterable[Path]) -> Generator[ConfigFile, None, None]:
    for path in paths:
        logging.debug("Loading config file %s", path)
        if not path.exists():
            yield ConfigFile(path=path, parsed_lines=[])
            continue
        with path.open("r") as handle:
            yield ConfigFile(path=path, parsed_lines=list(parse_config_lines(handle.readlines())))


def save_config_files(
    config_files: Iterable[ConfigFile],
    confirm_cb: Callable[[Path, Path], bool] = lambda orig_file, temp_file: True,
) -> None:
    for config_file in config_files:
        if not config_file.modified:
            continue

        temp_path: Path | None = None
        try:
            if config_file.path.is_dir() or (
                not config_file.path.exists() and config_file.path.name in CONFIG_FILENAMES.values()
            ):
                config_file.path = ensure_local_config(config_file.path)
            else:
                config_file.path.parent.mkdir(parents=True, exist_ok=True)
                if not config_file.path.exists():
                    config_file.path.touch()
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=config_file.path.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                shutil.copymode(config_file.path, handle.fileno())  # type: ignore[arg-type]
                handle.write(
                    "".join(
                        line._raw_line if line._raw_line is not None else render_config_line(line)
                        for line in config_file.parsed_lines
                    )
                )

            if confirm_cb(config_file.path, temp_path):
                temp_path.replace(config_file.path)
            else:
                temp_path.unlink()
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise
