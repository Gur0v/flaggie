# Copyright (c) 2026 Gurov

from pathlib import Path

import pytest

from flagger.app import normalize_operations, run
from flagger.models import TokenType


def test_run_updates_use_and_keywords(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["media-video/pipewire", "+sound-server", "+~amd64"], prog_name="flagger")
    assert result.modified_files == 2
    assert len(result.modified_paths) == 2
    assert not result.pretend
    assert result.message == "success: updated 2 file(s)"
    assert (
        (tmp_path / "etc/portage/package.use/99local.conf").read_text()
        == "media-video/pipewire sound-server\n"
    )
    assert (
        (tmp_path / "etc/portage/package.accept_keywords/99local.conf").read_text()
        == "media-video/pipewire ~amd64\n"
    )


def test_run_pretend_does_not_write(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["--pretend", "media-video/pipewire", "+sound-server"], prog_name="flagger")
    assert result.modified_files == 1
    assert result.pretend
    assert result.message == "pretend: prepared changes for 1 file(s)"
    assert (tmp_path / "etc/portage/package.use/99local.conf").read_text() == ""


def test_run_pretend_does_not_create_missing_config_files(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["--pretend", "media-video/pipewire", "+sound-server", "+~amd64"], prog_name="flagger")
    assert result.modified_files == 2
    assert not (tmp_path / "etc/portage/package.use").exists()
    assert not (tmp_path / "etc/portage/package.accept_keywords").exists()


def test_run_remove_all_updates_both_supported_files(tmp_path, monkeypatch):
    (tmp_path / "etc/portage/package.use").mkdir(parents=True)
    (tmp_path / "etc/portage/package.accept_keywords").mkdir(parents=True)
    (tmp_path / "etc/portage/package.use/99local.conf").write_text(
        "media-video/pipewire sound-server\n"
    )
    (tmp_path / "etc/portage/package.accept_keywords/99local.conf").write_text(
        "media-video/pipewire ~amd64\n"
    )
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["media-video/pipewire", "%"], prog_name="flagger")
    assert result.modified_files == 2
    assert (tmp_path / "etc/portage/package.use/99local.conf").read_text() == ""
    assert (tmp_path / "etc/portage/package.accept_keywords/99local.conf").read_text() == ""


def test_run_explicit_kw_namespace_updates_keywords_file(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["media-video/pipewire", "+kw::amd64"], prog_name="flagger")
    assert result.modified_files == 1
    assert (
        (tmp_path / "etc/portage/package.accept_keywords/99local.conf").read_text()
        == "media-video/pipewire amd64\n"
    )


def test_run_reports_no_changes_needed(tmp_path, monkeypatch):
    (tmp_path / "etc/portage/package.use").mkdir(parents=True)
    (tmp_path / "etc/portage/package.use/99local.conf").write_text(
        "media-video/pipewire sound-server\n"
    )
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["media-video/pipewire", "+sound-server"], prog_name="flagger")
    assert result.modified_files == 0
    assert result.message == "success: no changes needed"


def test_run_json_and_verbose_data(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: "media-libs/mesa")

    result = run(["--verbose", "mesa", "+opencl"], prog_name="flagger")
    assert result.package_resolutions[0].requested == "mesa"
    assert result.package_resolutions[0].resolved == "media-libs/mesa"
    assert result.details
    assert result.to_dict()["status"] == "success"


def test_run_from_file(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    request_file = tmp_path / "requests.txt"
    request_file.write_text("media-video/pipewire +sound-server\n")
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    result = run(["--from-file", str(request_file)], prog_name="flagger")
    assert result.modified_files == 1


def test_normalize_operations_warns_on_conflict():
    parser = __import__("argparse").ArgumentParser()
    operations, warnings = normalize_operations(parser, ["+foo", "-foo", "+kw::amd64", "+kw::amd64"])
    assert warnings == [
        "using last request '-foo' instead of '+foo'",
        "ignoring duplicate request '+kw::amd64'",
    ]
    assert [(item.operator, item.token_type, item.flag) for item in operations] == [
        ("-", TokenType.USE, "foo"),
        ("+", TokenType.KEYWORD, "amd64"),
    ]


def test_run_requires_request(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    with pytest.raises(SystemExit):
        run([], prog_name="flagger")
