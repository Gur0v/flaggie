# Copyright (c) 2026 Gurov

import argparse

from pathlib import Path

import pytest

from flagger.cli import (
    get_config_root,
    infer_token_type,
    namespace_into_target,
    parse_cli_args,
    read_request_tokens,
    resolve_targets,
    split_arg_sets,
    split_operation,
)
from flagger.models import TokenType


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["+foo", "-bar"], [([], ["+foo", "-bar"])]),
        (["dev-foo/bar", "+foo"], [(["dev-foo/bar"], ["+foo"])]),
        (["dev-foo/bar", "baz", "-foo"], [(["dev-foo/bar", "baz"], ["-foo"])]),
    ],
)
def test_split_arg_sets(args, expected):
    parser = argparse.ArgumentParser()
    assert list(split_arg_sets(parser, args, {"+", "-", "%"})) == expected


@pytest.mark.parametrize("args", [[""], ["dev-foo/bar"]])
def test_split_arg_sets_invalid(args):
    parser = argparse.ArgumentParser()
    with pytest.raises(SystemExit):
        list(split_arg_sets(parser, args, {"+", "-", "%"}))


@pytest.mark.parametrize(
    ("raw_operation", "expected"),
    [
        ("+foo", ("+", None, "foo")),
        ("-use::foo", ("-", "use", "foo")),
        ("%", ("%", None, None)),
    ],
)
def test_split_operation(raw_operation, expected):
    assert split_operation(raw_operation) == expected


@pytest.mark.parametrize(
    ("namespace", "expected"),
    [
        ("use", (TokenType.USE, None)),
        ("kw", (TokenType.KEYWORD, None)),
        ("PYTHON_TARGETS", (TokenType.USE, "PYTHON_TARGETS")),
    ],
)
def test_namespace_into_target(namespace, expected):
    assert namespace_into_target(namespace) == expected


@pytest.mark.parametrize(
    ("flag", "expected"),
    [("foo", TokenType.USE), ("~amd64", TokenType.KEYWORD), ("*", TokenType.KEYWORD)],
)
def test_infer_token_type(flag, expected):
    assert infer_token_type(flag) is expected


def test_get_config_root_default(monkeypatch):
    monkeypatch.delenv("FLAGGER_CONFIG_ROOT", raising=False)
    assert get_config_root() == Path("/")


def test_resolve_targets_remove_all():
    parser = argparse.ArgumentParser()
    assert resolve_targets(parser, operator="%", namespace=None, flag=None) == [
        (TokenType.USE, None),
        (TokenType.KEYWORD, None),
    ]


def test_read_request_tokens(tmp_path):
    path = tmp_path / "requests.txt"
    path.write_text("# comment\npkg +foo\n'*/ *'  \n")
    assert read_request_tokens(str(path)) == ["pkg", "+foo", "*/ *"]


def test_parse_cli_args_from_file(tmp_path):
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-file", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--pretend", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    path = tmp_path / "requests.txt"
    path.write_text("pkg +foo\n")
    parsed = parse_cli_args(parser, ["--from-file", str(path), "other", "+bar"])
    assert parsed.request == ["pkg", "+foo", "other", "+bar"]
