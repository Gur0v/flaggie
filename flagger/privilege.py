# Copyright (c) 2026 Gurov

from __future__ import annotations

import os
import shutil

from pathlib import Path


AUTO_ELEVATE_ENV = "FLAGGER_ALREADY_ELEVATED"
ELEVATION_HELPERS = ("sudo", "sudo-rs", "doas", "run0", "pkexec")
SYSTEM_ROOT = Path("/")


def should_retry_with_elevation(argv: list[str], *, config_root: Path) -> bool:
    if os.geteuid() == 0:
        return False
    if os.environ.get(AUTO_ELEVATE_ENV) == "1":
        return False
    if any(arg in {"--help", "--version", "--pretend"} for arg in argv):
        return False
    return config_root == SYSTEM_ROOT


def get_elevation_helper() -> str | None:
    for helper in ELEVATION_HELPERS:
        if shutil.which(helper) is not None:
            return helper
    return None


def resolve_program(prog_name: str) -> str:
    if os.sep in prog_name:
        return os.path.abspath(prog_name)
    return shutil.which(prog_name) or prog_name


def reexec_with_privileges(prog_name: str, argv: list[str], *, config_root: Path) -> None:
    if not should_retry_with_elevation(argv, config_root=config_root):
        return

    helper = get_elevation_helper()
    if helper is None:
        return

    env = dict(os.environ)
    env[AUTO_ELEVATE_ENV] = "1"
    os.execvpe(helper, [helper, resolve_program(prog_name), *argv], env)
