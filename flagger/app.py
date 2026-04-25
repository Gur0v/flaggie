# Copyright (c) 2026 Gurov

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from flagger.cli import (
    build_parser,
    get_config_root,
    parse_cli_args,
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


@dataclass(frozen=True)
class PlannedOperation:
    operator: str
    token_type: TokenType
    group: str | None
    flag: str | None
    source: str


@dataclass(frozen=True)
class PackageResolution:
    requested: str
    resolved: str


@dataclass(frozen=True)
class RunResult:
    modified_files: int
    modified_paths: tuple[str, ...]
    pretend: bool
    package_resolutions: tuple[PackageResolution, ...]
    warnings: tuple[str, ...]
    details: tuple[str, ...]

    @property
    def message(self) -> str:
        if self.pretend:
            if self.modified_files:
                return f"pretend: prepared changes for {self.modified_files} file(s)"
            return "pretend: no changes needed"
        if self.modified_files:
            return f"success: updated {self.modified_files} file(s)"
        return "success: no changes needed"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "success",
            "message": self.message,
            "pretend": self.pretend,
            "modified_files": self.modified_files,
            "modified_paths": list(self.modified_paths),
            "warnings": list(self.warnings),
            "details": list(self.details),
            "package_resolutions": [
                {"requested": item.requested, "resolved": item.resolved}
                for item in self.package_resolutions
            ],
        }

    def render(self, *, quiet: bool, json_output: bool, verbose: bool) -> str:
        if json_output:
            return json.dumps(self.to_dict(), sort_keys=True)
        lines: list[str] = []
        if not quiet:
            lines.append(self.message)
        if verbose:
            lines.extend(f"detail: {detail}" for detail in self.details)
            lines.extend(
                f"resolved: {item.requested} -> {item.resolved}"
                for item in self.package_resolutions
                if item.requested != item.resolved
            )
        lines.extend(f"warning: {warning}" for warning in self.warnings)
        return "\n".join(lines)


OPERATIONS = {
    "+": OperationSpec(partial(update_flag, enabled=True), flag_required=True),
    "-": OperationSpec(partial(update_flag, enabled=False), flag_required=True),
    "%": OperationSpec(remove_flag, flag_required=False),
}


def load_config_files(config_root: Path) -> dict[TokenType, list[ConfigFile]]:
    return {
        token_type: list(read_config_files(find_config_files(config_root, token_type, create=False)))
        for token_type in TokenType
    }


def resolve_packages(parser, packages: list[str]) -> list[PackageResolution]:
    resolved: list[PackageResolution] = []
    for package in packages or ["*/*"]:
        try:
            resolved_package = match_package(package)
        except (MatchError, ValueError) as err:
            parser.error(str(err))
        resolved.append(PackageResolution(requested=package, resolved=resolved_package))
    return resolved


def normalize_operations(
    parser,
    raw_operations: list[str],
) -> tuple[list[PlannedOperation], list[str]]:
    planned_by_key: dict[tuple[TokenType, str | None, str | None], PlannedOperation] = {}
    warnings: list[str] = []

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
            key = (token_type, group, flag)
            planned = PlannedOperation(
                operator=operator,
                token_type=token_type,
                group=group,
                flag=flag,
                source=raw_operation,
            )
            existing = planned_by_key.pop(key, None)
            if existing is not None:
                if existing.operator == operator:
                    warnings.append(f"ignoring duplicate request {raw_operation!r}")
                else:
                    warnings.append(
                        f"using last request {raw_operation!r} instead of {existing.source!r}"
                    )
            planned_by_key[key] = planned

    return list(planned_by_key.values()), warnings


def run(argv: list[str], *, prog_name: str) -> RunResult:
    parser = build_parser(prog_name)
    args = parse_cli_args(parser, argv)
    if not args.request:
        parser.error("No request specified")

    config_root = get_config_root()
    portage_dir = config_root / "etc/portage"
    if not portage_dir.is_dir():
        parser.error(
            f"{portage_dir} does not exist. Set FLAGGER_CONFIG_ROOT if you want to work on a different root."
        )

    config_files_by_type = load_config_files(config_root)
    warnings: list[str] = []
    details: list[str] = []
    package_resolutions: list[PackageResolution] = []

    for packages, raw_operations in split_arg_sets(parser, args.request, set(OPERATIONS)):
        resolved_packages = resolve_packages(parser, packages)
        package_resolutions.extend(resolved_packages)
        planned_operations, request_warnings = normalize_operations(parser, raw_operations)
        warnings.extend(request_warnings)

        for planned in planned_operations:
            operation = OPERATIONS[planned.operator]
            for package_resolution in resolved_packages:
                operation.function(
                    config_files_by_type[planned.token_type],
                    package_resolution.resolved,
                    planned.group,
                    planned.flag,
                )

    all_config_files = [
        config_file for files in config_files_by_type.values() for config_file in files
    ]
    modified_files = sum(1 for config_file in all_config_files if config_file.modified)
    modified_paths = tuple(str(config_file.path) for config_file in all_config_files if config_file.modified)

    if args.verbose:
        details.extend(
            f"writing {path}" if not args.pretend else f"would write {path}"
            for path in modified_paths
        )

    if not args.pretend:
        save_config_files(
            all_config_files,
            confirm_cb=lambda orig_file, temp_file: True,
        )
    return RunResult(
        modified_files=modified_files,
        modified_paths=modified_paths,
        pretend=args.pretend,
        package_resolutions=tuple(package_resolutions),
        warnings=tuple(warnings),
        details=tuple(details),
    )
