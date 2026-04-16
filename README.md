# flaggie fork

This fork of `flaggie` exists for one behavior change:

- when Portage package configuration is stored in a directory such as
  `package.use/`, `flaggie` will only read and write
  `99local.conf`
- it will not pick another existing file in that directory
- it will not modify sibling config files

Why:

- keep machine-managed changes in one predictable file
- avoid touching hand-maintained package config files

What stays same:

- normal `flaggie` CLI behavior
- direct file configs like `package.use` still work as before
- if `99local.conf` does not exist yet, this fork creates it

Setup on Gentoo:

1. Install `uv`:

   ```bash
   sudo emerge -av dev-python/uv
   ```

2. Install this fork as isolated tool, with `gentoopm` support:

   ```bash
   cd ~/flaggie
   uv tool install --with gentoopm .
   ```

3. If `flaggie` is not found, add local bin dir to `PATH`:

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

4. Verify install:

   ```bash
   flaggie --version
   flaggie --help
   ```

Notes:

- `uv tool install` gives global `flaggie` command without tying usage to repo
  shell or local `venv`
- after changing local source and wanting installed command updated, run:

  ```bash
  cd ~/flaggie
  uv tool install --force --with gentoopm .
  ```

Upstream project:

- original project: <https://github.com/gentoo/flaggie>
