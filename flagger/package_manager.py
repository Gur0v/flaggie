# Copyright (c) 2026 Gurov

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess

from typing import Any

from flagger.operations import is_wildcard_package


class MatchError(RuntimeError):
    pass


REPO_SEPARATOR = "::"
PACKAGE_OPERATORS = ("<=", ">=", "=", "<", ">", "~")
SHORT_PACKAGE_RE = re.compile(r"^[A-Za-z0-9+_.-]+$")
ATOM_PART_RE = re.compile(r"^(?:\*|[A-Za-z0-9+_.-]+(?:\*?[A-Za-z0-9+_.-]*)*)$")
REPO_RE = re.compile(r"^[A-Za-z0-9+_.-]+$")


SYSTEM_GENTOOPM_HELPER = r"""
import json
import sys

import gentoopm


request = json.loads(sys.argv[1])
pm = gentoopm.get_package_manager()
package_spec = request["package_spec"]
parsed = pm.Atom(package_spec)
matches = sorted({str(pkg.key) for pkg in pm.stack.filter(package_spec)})
if not matches:
    print(json.dumps({"error": "no_match"}))
elif len(matches) > 1:
    print(json.dumps({"error": "multiple", "matched": matches}))
elif parsed.key.category is None:
    print(json.dumps({
        "value": package_spec.replace(str(parsed.key.package), matches[0])
    }))
else:
    print(json.dumps({"value": package_spec}))
"""


class SubprocessPackageManager:
    def __init__(self, python_executable: str):
        self.python_executable = python_executable

    def match_package(self, package_spec: str) -> str:
        process = subprocess.run(
            [self.python_executable, "-c", SYSTEM_GENTOOPM_HELPER, json.dumps({"package_spec": package_spec})],
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise MatchError(f"System package manager helper failed: {process.stderr.strip()}")

        payload = json.loads(process.stdout)
        error = payload.get("error")
        if error == "no_match":
            raise MatchError(f"{package_spec!r} matched no packages")
        if error == "multiple":
            raise MatchError(
                f"{package_spec!r} is ambiguous, matched {', '.join(payload['matched'])}"
            )
        return payload["value"]


def get_package_manager() -> Any | None:
    python_executable = shutil.which("python3")
    if python_executable is not None:
        package_manager = SubprocessPackageManager(python_executable)
        try:
            package_manager.match_package("sys-apps/portage")
        except Exception:
            pass
        else:
            return package_manager

    try:
        import gentoopm
    except Exception:
        return None

    try:
        return gentoopm.get_package_manager()
    except Exception:
        return None


@functools.cache
def cached_package_manager() -> Any | None:
    return get_package_manager()


def split_package_components(package_spec: str) -> tuple[str, str | None]:
    if REPO_SEPARATOR not in package_spec:
        return package_spec, None
    base, repo = package_spec.rsplit(REPO_SEPARATOR, 1)
    return base, repo or None


def strip_operator(package_spec: str) -> str:
    for operator in PACKAGE_OPERATORS:
        if package_spec.startswith(operator):
            return package_spec[len(operator) :]
    return package_spec


def validate_package_spec(package_spec: str) -> None:
    base, repo = split_package_components(package_spec)
    if repo is not None and REPO_RE.fullmatch(repo) is None:
        raise ValueError(f"{package_spec!r} is not a valid repo-qualified package spec")

    atom = strip_operator(base)
    if "/" not in atom:
        if SHORT_PACKAGE_RE.fullmatch(atom) is None:
            raise ValueError(f"{package_spec!r} is not a valid package spec")
        return

    if atom.count("/") != 1:
        raise ValueError(f"{package_spec!r} is not a valid category/package spec")

    category, name = atom.split("/", 1)
    if not category or not name:
        raise ValueError(f"{package_spec!r} is not a valid category/package spec")
    if ATOM_PART_RE.fullmatch(category) is None or ATOM_PART_RE.fullmatch(name) is None:
        raise ValueError(f"{package_spec!r} is not a valid category/package spec")


def match_package(package_spec: str) -> str:
    validate_package_spec(package_spec)

    if is_wildcard_package(package_spec):
        return package_spec

    base, repo = split_package_components(package_spec)
    if "/" in strip_operator(base):
        return package_spec

    package_manager = cached_package_manager()
    if package_manager is None:
        raise MatchError(
            f"{package_spec!r} does not include a category and package lookup is unavailable"
        )

    if isinstance(package_manager, SubprocessPackageManager):
        resolved = package_manager.match_package(base)
        return f"{resolved}{REPO_SEPARATOR}{repo}" if repo is not None else resolved

    parsed = package_manager.Atom(base)
    matches = {str(pkg.key) for pkg in package_manager.stack.filter(base)}
    if not matches:
        raise MatchError(f"{package_spec!r} matched no packages")
    if len(matches) > 1:
        raise MatchError(f"{package_spec!r} is ambiguous, matched {', '.join(sorted(matches))}")
    resolved = base.replace(str(parsed.key.package), next(iter(matches)))
    return f"{resolved}{REPO_SEPARATOR}{repo}" if repo is not None else resolved
