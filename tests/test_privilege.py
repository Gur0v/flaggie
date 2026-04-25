# Copyright (c) 2026 Gurov

from pathlib import Path

import pytest

from flagger.privilege import (
    AUTO_ELEVATE_ENV,
    ELEVATION_HELPERS,
    get_elevation_helper,
    reexec_with_privileges,
    resolve_program,
    should_retry_with_elevation,
)


def test_should_retry_with_elevation_defaults(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.delenv(AUTO_ELEVATE_ENV, raising=False)
    assert should_retry_with_elevation(["mesa", "+opencl"], config_root=Path("/"))


def test_should_retry_with_elevation_skips_for_root(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.delenv(AUTO_ELEVATE_ENV, raising=False)
    assert not should_retry_with_elevation(["mesa", "+opencl"], config_root=Path("/"))


def test_should_retry_with_elevation_skips_when_already_elevated(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.setenv(AUTO_ELEVATE_ENV, "1")
    assert not should_retry_with_elevation(["mesa", "+opencl"], config_root=Path("/"))


def test_should_retry_with_elevation_skips_for_help(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.delenv(AUTO_ELEVATE_ENV, raising=False)
    assert not should_retry_with_elevation(["--help"], config_root=Path("/"))


def test_should_retry_with_elevation_skips_for_pretend(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.delenv(AUTO_ELEVATE_ENV, raising=False)
    assert not should_retry_with_elevation(["--pretend", "mesa", "+opencl"], config_root=Path("/"))


def test_should_retry_with_elevation_skips_for_custom_root(monkeypatch, tmp_path):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.delenv(AUTO_ELEVATE_ENV, raising=False)
    assert not should_retry_with_elevation(["mesa", "+opencl"], config_root=tmp_path)


def test_get_elevation_helper_prefers_first_available(monkeypatch):
    available = {name: f"/usr/bin/{name}" for name in ELEVATION_HELPERS[2:4]}
    monkeypatch.setattr("shutil.which", lambda command: available.get(command))
    assert get_elevation_helper() == ELEVATION_HELPERS[2]


def test_resolve_program_uses_absolute_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")
    assert resolve_program("flagger") == "/usr/bin/flagger"
    assert resolve_program("./bin/flagger").endswith("/bin/flagger")


def test_reexec_with_privileges(monkeypatch):
    monkeypatch.setattr("flagger.privilege.should_auto_elevate", lambda argv, config_root: True)
    monkeypatch.setattr("flagger.privilege.get_elevation_helper", lambda: "run0")
    monkeypatch.setattr("flagger.privilege.resolve_program", lambda program: "/usr/bin/flagger")
    called = {}

    def fake_execvpe(file, args, env):
        called["file"] = file
        called["args"] = args
        called["env"] = env
        raise SystemExit(0)

    monkeypatch.setattr("os.execvpe", fake_execvpe)

    with pytest.raises(SystemExit):
        reexec_with_privileges("flagger", ["mesa", "+opencl"], config_root=Path("/"))

    assert called["file"] == "run0"
    assert called["args"] == ["run0", "/usr/bin/flagger", "mesa", "+opencl"]
    assert called["env"][AUTO_ELEVATE_ENV] == "1"
