# Copyright (c) 2026 Gurov

import itertools

from pathlib import Path

import pytest

from flagger.config_files import parse_config_lines
from flagger.models import ConfigFile, ConfigLine
from flagger.operations import (
    WildcardEntryError,
    insert_sorted,
    is_wildcard_flag,
    is_wildcard_package,
    package_pattern_to_re,
    remove_flag,
    update_flag,
)


def get_config(raw_data: list[str]) -> list[ConfigFile]:
    return [ConfigFile(Path("test.conf"), list(parse_config_lines(raw_data)))]


def get_modified_line_numbers(config_file: ConfigFile) -> frozenset[int]:
    assert config_file.modified
    return frozenset(
        line_number
        for line_number, line in enumerate(config_file.parsed_lines)
        if line._raw_line is None
    )


def param_new() -> pytest.MarkDecorator:
    return pytest.mark.parametrize("new", ["-foo", "foo"])


def param_old_new(*, prefix: str = "", flag: str = "foo") -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        "old,new",
        itertools.product([f"-{prefix}{flag}", f"{prefix}{flag}"], repeat=2),
    )


def param_pkg(include_global: bool = False) -> pytest.MarkDecorator:
    packages = ["dev-foo/foo", "dev-bar/*"]
    if include_global:
        packages.append("*/*")
    return pytest.mark.parametrize("package", packages)


@param_old_new()
@param_pkg(include_global=True)
def test_toggle_flag(old, new, package):
    config = get_config(["*/* foo", "", f"{package} {old} bar", "dev-foo/bar foo", f"{package} baz"])
    update_flag(config, package, None, new.lstrip("-"), enabled=not new.startswith("-"))
    assert get_modified_line_numbers(config[0]) == {2}
    assert config[0].parsed_lines == [
        ConfigLine("*/*", ["foo"]),
        ConfigLine(),
        ConfigLine(package, [new, "bar"]),
        ConfigLine("dev-foo/bar", ["foo"]),
        ConfigLine(package, ["baz"]),
    ]


@param_new()
@param_pkg()
def test_toggle_flag_append(new, package):
    config = get_config(["*/* foo", "", f"{package} bar", "dev-foo/bar foo", f"{package} baz", f"{package} GROUP: other"])
    update_flag(config, package, None, new.lstrip("-"), enabled=not new.startswith("-"))
    assert get_modified_line_numbers(config[0]) == {4}
    assert config[0].parsed_lines == [
        ConfigLine("*/*", ["foo"]),
        ConfigLine(),
        ConfigLine(package, ["bar"]),
        ConfigLine("dev-foo/bar", ["foo"]),
        ConfigLine(package, ["baz", new]),
        ConfigLine(package, [], [("GROUP", ["other"])]),
    ]


@param_new()
@param_pkg(include_global=True)
def test_toggle_flag_append_to_group(new, package):
    config = get_config(["*/* foo", "", f"{package} GROUP: bar", "dev-foo/bar foo", f"{package} group_baz"])
    update_flag(config, package, "group", new.lstrip("-"), enabled=not new.startswith("-"))
    assert get_modified_line_numbers(config[0]) == {2}
    assert config[0].parsed_lines == [
        ConfigLine("*/*", ["foo"]),
        ConfigLine(),
        ConfigLine(package, [], [("GROUP", ["bar", new])]),
        ConfigLine("dev-foo/bar", ["foo"]),
        ConfigLine(package, ["group_baz"]),
    ]


@param_new()
def test_toggle_flag_new_entry(new):
    config = get_config(["*/* foo", "dev-foo/bar foo"])
    update_flag(config, "dev-foo/foo", None, new.lstrip("-"), enabled=not new.startswith("-"))
    assert get_modified_line_numbers(config[0]) == {2}
    assert config[0].parsed_lines == [
        ConfigLine("*/*", ["foo"]),
        ConfigLine("dev-foo/bar", ["foo"]),
        ConfigLine("dev-foo/foo", [new]),
    ]


@param_new()
def test_toggle_flag_new_entry_global(new):
    config = get_config(["dev-foo/bar foo"])
    update_flag(config, "*/*", None, new.lstrip("-"), enabled=not new.startswith("-"))
    assert get_modified_line_numbers(config[0]) == {0}
    assert config[0].parsed_lines == [
        ConfigLine("*/*", [new]),
        ConfigLine("dev-foo/bar", ["foo"]),
    ]


@param_new()
def test_toggle_flag_new_entry_wildcard(new):
    config = get_config(["dev-foo/bar foo"])
    with pytest.raises(WildcardEntryError):
        update_flag(config, "dev-foo/*", None, new.lstrip("-"), enabled=not new.startswith("-"))


def test_remove_flag():
    config = get_config(["dev-foo/bar foo bar", "dev-foo/bar GROUP: baz qux"])
    remove_flag(config, "dev-foo/bar", None, "foo")
    assert config[0].parsed_lines == [
        ConfigLine("dev-foo/bar", ["bar"]),
        ConfigLine("dev-foo/bar", [], [("GROUP", ["baz", "qux"])]),
    ]


def test_remove_all_flags():
    config = get_config(["dev-foo/bar foo", "dev-foo/bar GROUP: baz"])
    remove_flag(config, "dev-foo/bar", None, None)
    assert config[0].parsed_lines == []


def test_helpers():
    assert package_pattern_to_re("dev-foo/*").match("dev-foo/bar")
    assert is_wildcard_package("dev-foo/*")
    assert is_wildcard_flag("~*")
    flags = ["bar", "zoo"]
    insert_sorted(flags, "foo")
    assert flags == ["bar", "foo", "zoo"]
