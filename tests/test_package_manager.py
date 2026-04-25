# Copyright (c) 2026 Gurov

import types

import pytest

from flagger.package_manager import (
    MatchError,
    SubprocessPackageManager,
    match_package,
    validate_package_spec,
)


class MockPackageManager:
    class Atom:
        def __init__(self, atom: str) -> None:
            self._atom = atom

        @property
        def key(self):
            if "/" in self._atom:
                category, package = self._atom.split("/", 1)
                return types.SimpleNamespace(category=category, package=package)
            return types.SimpleNamespace(category=None, package=self._atom)

    class stack:
        @staticmethod
        def filter(atom: str):
            if atom == "enoent":
                return []
            if atom == "multiple":
                return [
                    types.SimpleNamespace(key="app-foo/multi"),
                    types.SimpleNamespace(key="app-bar/multi"),
                ]
            if "/" in atom:
                return [types.SimpleNamespace(key=atom)]
            return [types.SimpleNamespace(key=f"app-foo/{atom}")]


def test_match_package_with_category():
    assert match_package("app-foo/bar") == "app-foo/bar"


def test_match_package_wildcard():
    assert match_package("app-foo/*") == "app-foo/*"


def test_match_package_without_category(monkeypatch):
    monkeypatch.setattr("flagger.package_manager.cached_package_manager", lambda: MockPackageManager())
    assert match_package("bar") == "app-foo/bar"


def test_match_package_without_lookup(monkeypatch):
    monkeypatch.setattr("flagger.package_manager.cached_package_manager", lambda: None)
    with pytest.raises(MatchError):
        match_package("bar")


def test_match_package_multiple(monkeypatch):
    monkeypatch.setattr("flagger.package_manager.cached_package_manager", lambda: MockPackageManager())
    with pytest.raises(MatchError):
        match_package("multiple")


def test_match_package_subprocess_package_manager(monkeypatch):
    package_manager = SubprocessPackageManager("python3")
    monkeypatch.setattr(package_manager, "match_package", lambda package_spec: "app-foo/bar")
    monkeypatch.setattr("flagger.package_manager.cached_package_manager", lambda: package_manager)
    assert match_package("bar") == "app-foo/bar"


def test_validate_package_spec_repo_qualified_wildcard():
    validate_package_spec("*/*::steam-overlay")


@pytest.mark.parametrize("package_spec", ["app-foo/bar::", "bad repo::steam overlay", "app-foo//bar"])
def test_validate_package_spec_invalid(package_spec):
    with pytest.raises(ValueError):
        validate_package_spec(package_spec)
