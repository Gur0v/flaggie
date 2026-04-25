# Copyright (c) 2026 Gurov

from __future__ import annotations

from functools import partial
from pathlib import Path

from flagger.cli import (
    build_parser,
    get_config_root,
    resolve_targets,
    split_arg_sets,
    split_operation,
)
from flagger.config_files import find_config_files, read_config_files, save_config_files
from flagger.models import ConfigFile, TokenType
from flagger.operations import remove_flag, update_flag
from flagger.package_manager import MatchError, match_package


class OperationSpec:
    def __init__(self, function, *, flag_required: bool):
        self.function = function
        self.flag_required = flag_required


OPERATIONS = {
    "+": OperationSpec(partial(update_flag, enabled=True), flag_required=True),
    "-": OperationSpec(partial(update_flag, enabled=False), flag_required=True),
    "%": OperationSpec(remove_flag, flag_required=False),
}


def load_config_files(config_root: Path) -> dict[TokenType, list[ConfigFile]]:
    return {
        token_type: list(read_config_files(find_config_files(config_root, token_type)))
        for token_type in TokenType
    }


def resolve_packages(parser, packages: list[str]) -> list[str]:
    resolved: list[str] = []
    for package in packages or ["*/*"]:
        try:
            resolved.append(match_package(package))
        except (MatchError, ValueError) as err:
            parser.error(str(err))
    return resolved


def run(argv: list[str], *, prog_name: str) -> int:
    parser = build_parser(prog_name)
    args, request = parser.parse_known_args(argv)
    if not request:
        parser.error("No request specified")

    config_root = get_config_root()
    portage_dir = config_root / "etc/portage"
    if not portage_dir.is_dir():
        parser.error(
            f"{portage_dir} does not exist. Set FLAGGER_CONFIG_ROOT if you want to work on a different root."
        )

    config_files_by_type = load_config_files(config_root)

    for packages, raw_operations in split_arg_sets(parser, request, set(OPERATIONS)):
        resolved_packages = resolve_packages(parser, packages)

        for raw_operation in raw_operations:
            operator, namespace, flag = split_operation(raw_operation)
            operation = OPERATIONS.get(operator)
            if operation is None:
                parser.error(f"{raw_operation}: incorrect operation")
            if operation.flag_required and not flag:
                parser.error(f"{raw_operation}: flag name required")

            for token_type, group in resolve_targets(
                parser,
                operator=operator,
                namespace=namespace,
                flag=flag,
            ):
                for package in resolved_packages:
                    operation.function(config_files_by_type[token_type], package, group, flag)

    save_config_files(
        (config_file for files in config_files_by_type.values() for config_file in files),
        confirm_cb=lambda orig_file, temp_file: not args.pretend,
    )
    return 0
