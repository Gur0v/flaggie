# Copyright (c) 2026 Gurov

import dataclasses
import os
import stat

import pytest

from flagger.config_files import (
    find_config_files,
    parse_config_lines,
    read_config_files,
    render_config_line,
    save_config_files,
)
from flagger.models import ConfigFile, ConfigLine, TokenType


@pytest.mark.parametrize(
    ("token_type", "layout", "expected"),
    [
        (TokenType.USE, [], ["package.use/99local.conf"]),
        (TokenType.USE, ["package.use"], None),
        (TokenType.KEYWORD, [], ["package.accept_keywords/99local.conf"]),
        (TokenType.KEYWORD, ["package.accept_keywords"], None),
    ],
)
def test_find_config(token_type, layout, expected, tmp_path):
    confdir = tmp_path / "etc/portage"
    for entry in layout:
        path = confdir / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    if expected is None:
        expected = layout
    assert find_config_files(tmp_path, token_type) == [confdir / item for item in expected]


TEST_CONFIG_FILE = [
    "#initial comment\n",
    "  # comment with whitespace\n",
    "\n",
    "*/* foo bar baz # global flags\n",
    "*/* FROBNICATE_TARGETS: frob1 frob2\n",
    "  dev-foo/bar weird#flag other # actual comment # more comment\n",
    "dev-foo/baz mixed LONG: too EMPTY:\n",
]

PARSED_TEST_CONFIG = [
    ConfigLine(comment="initial comment"),
    ConfigLine(comment=" comment with whitespace"),
    ConfigLine(),
    ConfigLine("*/*", ["foo", "bar", "baz"], [], " global flags"),
    ConfigLine("*/*", [], [("FROBNICATE_TARGETS", ["frob1", "frob2"])]),
    ConfigLine("dev-foo/bar", ["weird#flag", "other"], [], " actual comment # more comment"),
    ConfigLine("dev-foo/baz", ["mixed"], [("LONG", ["too"]), ("EMPTY", [])]),
]

for raw_line, line in zip(TEST_CONFIG_FILE, PARSED_TEST_CONFIG):
    line._raw_line = raw_line


def test_parse_config_lines():
    assert list(parse_config_lines(TEST_CONFIG_FILE)) == PARSED_TEST_CONFIG


def test_render_config_line():
    assert [render_config_line(line) for line in parse_config_lines(TEST_CONFIG_FILE)] == [
        raw_line.lstrip(" ") for raw_line in TEST_CONFIG_FILE
    ]


def test_read_config_files(tmp_path):
    (tmp_path / "config").write_text("".join(TEST_CONFIG_FILE))
    (tmp_path / "config2").write_text("")
    assert list(read_config_files([tmp_path / "config", tmp_path / "config2"])) == [
        ConfigFile(tmp_path / "config", PARSED_TEST_CONFIG),
        ConfigFile(tmp_path / "config2", []),
    ]


def test_save_config_files_no_modification(tmp_path):
    config_files = [
        ConfigFile(tmp_path / "config", PARSED_TEST_CONFIG),
        ConfigFile(tmp_path / "config2", []),
    ]
    save_config_files(config_files)
    assert all(not config_file.path.exists() for config_file in config_files)


def invalidate_config_lines(lines: list[ConfigLine], *line_numbers: int) -> list[ConfigLine]:
    updated_lines = list(lines)
    for line_number in line_numbers:
        updated_lines[line_number] = dataclasses.replace(updated_lines[line_number])
        updated_lines[line_number].invalidate()
    return updated_lines


@pytest.mark.parametrize("write", [False, True])
def test_save_config_files(tmp_path, write):
    config_files = [
        ConfigFile(
            tmp_path / "config",
            invalidate_config_lines(PARSED_TEST_CONFIG, 1, 5),
            modified=True,
        ),
        ConfigFile(
            tmp_path / "config2",
            [ConfigLine("dev-foo/bar", ["new"], [])],
            modified=True,
        ),
        ConfigFile(tmp_path / "config3", []),
    ]

    for config_file in config_files:
        with config_file.path.open("w") as handle:
            os.fchmod(handle.fileno(), 0o400)
            handle.write("<original content>")

    save_config_files(config_files, confirm_cb=lambda orig_file, temp_file: write)

    expected = ["<original content>" for _ in config_files]
    if write:
        expected[:2] = [
            "".join(raw_line.lstrip(" ") for raw_line in TEST_CONFIG_FILE),
            "dev-foo/bar new\n",
        ]

    assert [config_file.path.read_text() for config_file in config_files] == expected
    assert [stat.S_IMODE(os.stat(config_file.path).st_mode) for config_file in config_files] == [
        0o400 for _ in config_files
    ]
