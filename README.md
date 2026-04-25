# flagger

`flagger` is a rewrite of Gentoo’s `flaggie`, built because I wanted something simpler.

It is not a drop-in replacement. It is not trying to preserve every feature. It does less, on purpose.

The goal is a tool that is predictable, easy to maintain, and fits a modern Python workflow, especially with `uv`.

## What Changed

This version is deliberately narrower:

* only edits `package.use` and `package.accept_keywords`
* drops legacy features that made `flaggie` harder to reason about
* writes to `99local.conf` when targeting a directory
* leaves other files alone
* installs cleanly with `uv`
* only escalates privileges when it actually needs to write
* supports `sudo`, `sudo-rs`, `doas`, `run0`, and `pkexec`
* keeps the original syntax, with optional `use::` and `kw::` namespaces

If you want the full feature set of old `flaggie`, use `flaggie`.

## Install

```bash
cd ~/Projects/flagger
uv tool install --with gentoopm .
```

`gentoopm` is optional, but useful if you want short names like `pipewire` to resolve automatically.

## Usage

There are only three flags:

* `--help`
* `--version`
* `--pretend`

Everything else is just operations:

```text
flagger [options] [package ...] op [op ...]
```

No package means `*/*`.

### USE flags

```bash
flagger media-video/pipewire +sound-server
flagger media-video/pipewire -sound-server
flagger media-video/pipewire %sound-server
flagger media-video/pipewire +PYTHON_TARGETS::python3_12
```

### Keywords

```bash
flagger media-video/pipewire +~amd64
flagger media-video/pipewire +kw::amd64
flagger media-video/pipewire %kw::~amd64
```

Keyword-style values (`~amd64`, `*`, `~*`, `**`) go to `package.accept_keywords`.

Everything else goes to `package.use` unless you say otherwise.

### Dry run

```bash
flagger --pretend media-video/pipewire +sound-server +~amd64
```

## Notes

You can point `flagger` at another Portage root using `FLAGGER_CONFIG_ROOT`.

On a real system, it tries to write first. If that fails with a `PermissionError`, it re-runs itself through the first available helper (`sudo`, `sudo-rs`, `doas`, `run0`, or `pkexec`).

No guessing, no always-running-as-root.

## Layout

```text
flagger/
├── flagger/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py
│   ├── cli.py
│   ├── config_files.py
│   ├── models.py
│   ├── operations.py
│   ├── package_manager.py
│   └── privilege.py
├── tests/
├── pyproject.toml
└── tox.ini
```

## Philosophy

* small surface area
* fewer features, fewer bugs
* predictable behavior
* no magic
* no unnecessary abstraction

This is not a general-purpose Portage tool.

It edits flags. That is it.

## Upstream

Original `flaggie`:
[https://github.com/gentoo/flaggie](https://github.com/gentoo/flaggie)
