# Copyright (c) 2026 Gurov

from __future__ import annotations

import functools
import re

from typing import Generator

from flagger.models import ConfigFile, ConfigLine


@functools.cache
def package_pattern_to_re(pattern: str) -> re.Pattern[str]:
    return re.compile(".*".join(re.escape(part) for part in pattern.split("*")))


def is_wildcard_package(package: str) -> bool:
    if package.startswith("="):
        package = package.rstrip("*")
    return "*" in package


def is_wildcard_flag(flag: str) -> bool:
    return flag in {"*", "**", "~*"} or flag.endswith("_*")


def iter_matching_packages(
    config_files: list[ConfigFile],
    package: str,
    *,
    exact_match: bool,
) -> Generator[tuple[ConfigFile, int, ConfigLine], None, None]:
    for config_file in reversed(config_files):
        line_count = len(config_file.parsed_lines)
        for reverse_index, line in enumerate(reversed(config_file.parsed_lines)):
            if line.package is None:
                continue

            if exact_match:
                matched = line.package == package
            else:
                matched = package_pattern_to_re(line.package).match(package) is not None

            if matched:
                yield config_file, line_count - reverse_index, line


def iter_matching_flags(
    line: ConfigLine,
    full_name: str,
) -> Generator[tuple[str | None, list[str], int], None, None]:
    full_name_pattern = package_pattern_to_re(full_name)

    for group_name, flags in reversed(line.grouped_flags):
        normalized_group = group_name.lower()
        for reverse_index, flag in enumerate(reversed(flags)):
            grouped_name = f"{normalized_group}_{flag.lstrip('-')}"
            if (
                package_pattern_to_re(grouped_name).match(full_name) is not None
                or full_name_pattern.match(grouped_name) is not None
            ):
                yield normalized_group, flags, len(flags) - reverse_index - 1

    for reverse_index, flag in enumerate(reversed(line.flat_flags)):
        normalized_flag = flag.lstrip("-")
        if (
            package_pattern_to_re(normalized_flag).match(full_name) is not None
            or full_name_pattern.match(normalized_flag) is not None
        ):
            yield None, line.flat_flags, len(line.flat_flags) - reverse_index - 1


class WildcardEntryError(Exception):
    def __init__(self) -> None:
        super().__init__("Adding wildcard entries other than */* is not supported")


def insert_sorted(flags: list[str], new_flag: str) -> None:
    new_value = new_flag.lstrip("-")
    if new_value == "*":
        flags.append(new_flag)
        return

    insertion_offset = 0
    previous = flags[-1].lstrip("-")
    for insertion_offset, existing in enumerate(reversed(flags)):
        normalized_existing = existing.lstrip("-")
        if normalized_existing > previous:
            break
        if is_wildcard_flag(normalized_existing):
            break
        if new_value > normalized_existing:
            break
        previous = normalized_existing
    else:
        insertion_offset += 1

    flags.insert(len(flags) - insertion_offset, new_flag)


def update_flag(
    config_files: list[ConfigFile],
    package: str,
    group: str | None,
    name: str,
    *,
    enabled: bool,
) -> None:
    package_is_wildcard = is_wildcard_package(package)
    full_name = name if group is None else f"{group.lower()}_{name}"
    rendered_flag = "" if enabled else "-"

    def try_update_existing() -> bool:
        for config_file, _, line in iter_matching_packages(
            config_files,
            package,
            exact_match=package_is_wildcard,
        ):
            for matched_group, flag_list, index in iter_matching_flags(line, full_name):
                matched_name = flag_list[index].lstrip("-")
                effective_name = matched_name if matched_group is None else f"{matched_group}_{matched_name}"
                if line.package == package and effective_name == full_name:
                    flag_list[index] = rendered_flag + matched_name
                    line.invalidate()
                    config_file.modified = True
                    return True
                return False
        return False

    def try_insert_into_existing_line() -> bool:
        for config_file, _, line in iter_matching_packages(
            config_files,
            package,
            exact_match=package_is_wildcard,
        ):
            if line.package != package:
                return False

            if group is None:
                if line.grouped_flags:
                    continue
                insert_sorted(line.flat_flags, rendered_flag + full_name)
            else:
                for existing_group, flags in line.grouped_flags:
                    if existing_group.lower() == group.lower():
                        insert_sorted(flags, rendered_flag + name)
                        break
                else:
                    continue

            line.invalidate()
            config_file.modified = True
            return True
        return False

    def make_line() -> ConfigLine:
        if group is None:
            return ConfigLine(package=package, flat_flags=[rendered_flag + name])
        return ConfigLine(package=package, grouped_flags=[(group.upper(), [rendered_flag + name])])

    def try_insert_after_existing(new_line: ConfigLine) -> bool:
        for config_file, line_number, line in iter_matching_packages(
            config_files,
            package,
            exact_match=package_is_wildcard,
        ):
            if line.package != package:
                return False
            config_file.parsed_lines.insert(line_number, new_line)
            config_file.modified = True
            return True
        return False

    def append_new_line(new_line: ConfigLine) -> None:
        assert new_line.package is not None
        if new_line.package == "*/*":
            config_files[0].parsed_lines.insert(0, new_line)
            config_files[0].modified = True
            return
        if is_wildcard_package(new_line.package):
            raise WildcardEntryError()
        config_files[-1].parsed_lines.append(new_line)
        config_files[-1].modified = True

    if try_update_existing() or try_insert_into_existing_line():
        return

    new_line = make_line()
    if not try_insert_after_existing(new_line):
        append_new_line(new_line)


def remove_flag(
    config_files: list[ConfigFile],
    package: str,
    group: str | None,
    name: str | None,
) -> None:
    normalized_group = group.lower() if group is not None else None
    full_name = None
    if name is not None:
        full_name = name if normalized_group is None else f"{normalized_group}_{name}"

    for config_file, line_number, line in iter_matching_packages(
        config_files,
        package,
        exact_match=True,
    ):
        matched = False

        def keep_flat(flag: str) -> bool:
            nonlocal matched
            normalized_flag = flag.lstrip("-")
            if full_name is not None and normalized_flag == full_name:
                matched = True
                return False
            if full_name is None and normalized_group is not None and normalized_flag.startswith(f"{normalized_group}_"):
                matched = True
                return False
            return True

        def keep_grouped(flag: str) -> bool:
            nonlocal matched
            if name is not None and flag.lstrip("-") == name:
                matched = True
                return False
            return True

        if name is not None:
            line.flat_flags = list(filter(keep_flat, line.flat_flags))
        elif normalized_group is not None:
            line.flat_flags = list(filter(keep_flat, line.flat_flags))
        else:
            line.flat_flags.clear()
            line.grouped_flags.clear()
            matched = True

        if normalized_group is not None:
            updated_groups: list[tuple[str, list[str]]] = []
            for group_name, flags in line.grouped_flags:
                if group_name.lower() != normalized_group:
                    updated_groups.append((group_name, flags))
                    continue
                if name is None:
                    matched = True
                    continue
                filtered_flags = list(filter(keep_grouped, flags))
                if filtered_flags:
                    updated_groups.append((group_name, filtered_flags))
            line.grouped_flags = updated_groups

        if matched:
            line.invalidate()
            config_file.modified = True
            if not line.flat_flags and not line.grouped_flags:
                del config_file.parsed_lines[line_number - 1]
