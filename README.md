# flagger

`flagger` is my fork of Gentoo's `flaggie`.

I wanted a version that behaves better on a real system:

- if a `package.*` config is a directory, it only writes to `99local.conf`
- it does not touch sibling files
- it works nicely when installed with `uv`
- it can auto-elevate with `doas` or `sudo` when writing to real
  `/etc/portage`

## Install

```bash
sudo emerge -av dev-python/uv app-portage/gentoopm
cd ~/flagger
uv tool install --with gentoopm .
```

If needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Use

```bash
flagger pipewire +sound-server
flagger pipewire +~amd64
```

If you are working on the real system config, `flagger` will call `doas` or
`sudo` itself when needed.

To update after local changes:

```bash
cd ~/flagger
uv tool install --force --with gentoopm .
```

Upstream `flaggie`:

- <https://github.com/gentoo/flaggie>
