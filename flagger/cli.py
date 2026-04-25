# Copyright (c) 2026 Gurov

from __future__ import annotations

import argparse
import os
import shutil
import textwrap

from pathlib import Path
from typing import Generator

from flagger import __version__
from flagger.models import TokenType


CONFIG_ROOT_ENV = "FLAGGER_CONFIG_ROOT"
KEYWORD_VALUES = {"*", "~*", "**"}
NAMESPACE_MAP = {
    "use": (TokenType.USE, None),
    "kw": (TokenType.KEYWORD, None),
}
REQUEST_HELP = """
Every request consists of zero or more packages, followed by one or more flag
changes, i.e.:

  request = [package ...] op [op ...]

Packages can be specified in any form suitable for package.use and
package.accept_keywords. If category is omitted, a package lookup is attempted.
If no packages are specified, "*/*" is assumed.

The operations supported are:

  +[ns::]flag         Enable specified flag
  -[ns::]flag         Disable specified flag
  %[ns::][flag]       Remove specified flag (or all flags)

Supported namespaces:

  use::               package.use entries
  kw::                package.accept_keywords entries

Any other namespace is treated as a USE_EXPAND group name, e.g.
`PYTHON_TARGETS::python3_12`.
"""


def get_config_root() -> Path:
    return Path(os.environ.get(CONFIG_ROOT_ENV, "/"))


def build_parser(prog_name: str) -> argparse.ArgumentParser:
    help_width = shutil.get_terminal_size().columns - 2
    epilog = REQUEST_HELP
    if help_width > 10:
        epilog = "\n".join(
            textwrap.fill(
                line,
                width=help_width,
                drop_whitespace=False,
                replace_whitespace=False,
            )
            for line in REQUEST_HELP.splitlines()
        )

    parser = argparse.ArgumentParser(
        add_help=False,
        prog=os.path.basename(prog_name),
        usage="%(prog)s [options] request ...",
        epilog=epilog,
        formatter_class=lambda prog: argparse.RawDescriptionHelpFormatter(prog, width=help_width),
    )
    parser.add_argument("--help", action="help", help="Print help text and exit")
    parser.add_argument(
        "--pretend",
        action="store_true",
        help="Do not write any changes to the original files",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"flagger {__version__}",
        help="Print program version and exit",
    )
    return parser


def split_arg_sets(
    parser: argparse.ArgumentParser,
    args: list[str],
    operators: set[str],
) -> Generator[tuple[list[str], list[str]], None, None]:
    packages: list[str] = []
    operations: list[str] = []

    for arg in args:
        if not arg:
            parser.error("Empty string in requests")
        if arg[0] in operators:
            operations.append(arg)
            continue
        if operations:
            yield packages, operations
            packages = []
            operations = []
        packages.append(arg)

    if not operations:
        parser.error(f"Packages ({' '.join(packages)}) with no operations specified in requests")
    yield packages, operations


def split_operation(raw_operation: str) -> tuple[str, str | None, str | None]:
    operator = raw_operation[0]
    namespace_parts = raw_operation[1:].split("::", 1)
    namespace = namespace_parts[0] if len(namespace_parts) == 2 else None
    flag = namespace_parts[-1] or None
    return operator, namespace, flag


def infer_token_type(flag: str) -> TokenType:
    if flag.startswith("~") or flag in KEYWORD_VALUES:
        return TokenType.KEYWORD
    return TokenType.USE


def namespace_into_target(namespace: str) -> tuple[TokenType, str | None]:
    return NAMESPACE_MAP.get(namespace, (TokenType.USE, namespace))


def resolve_targets(
    parser: argparse.ArgumentParser,
    *,
    operator: str,
    namespace: str | None,
    flag: str | None,
) -> list[tuple[TokenType, str | None]]:
    if namespace in (None, "auto"):
        if operator == "%" and flag is None:
            return [NAMESPACE_MAP["use"], NAMESPACE_MAP["kw"]]
        assert flag is not None
        return [(infer_token_type(flag), None)]

    token_type, group = namespace_into_target(namespace)
    if token_type is TokenType.KEYWORD and group is not None:
        parser.error(f"{namespace}:: is not a valid keyword namespace")
    return [(token_type, group)]
