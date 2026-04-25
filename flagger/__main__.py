# Copyright (c) 2026 Gurov

from __future__ import annotations

import sys

from flagger.app import run
from flagger.cli import get_config_root
from flagger.privilege import reexec_with_privileges


def main() -> None:
    argv = list(sys.argv[1:])
    config_root = get_config_root()
    try:
        sys.exit(run(argv, prog_name=sys.argv[0]))
    except PermissionError:
        reexec_with_privileges(sys.argv[0], argv, config_root=config_root)
        raise


if __name__ == "__main__":
    main()
