# Copyright (c) 2026 Gurov

from __future__ import annotations

import functools
import json
import shutil
import subprocess

from typing import Any

from flagger.operations import is_wildcard_package


class MatchError(RuntimeError):
    pass


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


def match_package(package_spec: str) -> str:
    if is_wildcard_package(package_spec):
        if package_spec.count("/") != 1:
            raise ValueError("Not a valid category/package spec")
        return package_spec

    if "/" in package_spec:
        if package_spec.count("/") != 1:
            raise ValueError("Not a valid category/package spec")
        return package_spec

    package_manager = cached_package_manager()
    if package_manager is None:
        raise MatchError(
            f"{package_spec!r} does not include a category and package lookup is unavailable"
        )

    if isinstance(package_manager, SubprocessPackageManager):
        return package_manager.match_package(package_spec)

    parsed = package_manager.Atom(package_spec)
    matches = {str(pkg.key) for pkg in package_manager.stack.filter(package_spec)}
    if not matches:
        raise MatchError(f"{package_spec!r} matched no packages")
    if len(matches) > 1:
        raise MatchError(f"{package_spec!r} is ambiguous, matched {', '.join(sorted(matches))}")
    return package_spec.replace(str(parsed.key.package), next(iter(matches)))
