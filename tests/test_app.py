# Copyright (c) 2026 Gurov

from pathlib import Path

import pytest

from flagger.app import run


def test_run_updates_use_and_keywords(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    assert run(["media-video/pipewire", "+sound-server", "+~amd64"], prog_name="flagger") == 0
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

    assert run(["--pretend", "media-video/pipewire", "+sound-server"], prog_name="flagger") == 0
    assert (tmp_path / "etc/portage/package.use/99local.conf").read_text() == ""


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

    assert run(["media-video/pipewire", "%"], prog_name="flagger") == 0
    assert (tmp_path / "etc/portage/package.use/99local.conf").read_text() == ""
    assert (tmp_path / "etc/portage/package.accept_keywords/99local.conf").read_text() == ""


def test_run_explicit_kw_namespace_updates_keywords_file(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setattr("flagger.app.match_package", lambda package: package)

    assert run(["media-video/pipewire", "+kw::amd64"], prog_name="flagger") == 0
    assert (
        (tmp_path / "etc/portage/package.accept_keywords/99local.conf").read_text()
        == "media-video/pipewire amd64\n"
    )


def test_run_requires_request(tmp_path, monkeypatch):
    (tmp_path / "etc/portage").mkdir(parents=True)
    monkeypatch.setenv("FLAGGER_CONFIG_ROOT", str(tmp_path))
    with pytest.raises(SystemExit):
        run([], prog_name="flagger")
