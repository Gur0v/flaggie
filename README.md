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

Upstream project:

- original project: <https://github.com/gentoo/flaggie>
