# Copyright (c) 2026 Gurov

from __future__ import annotations

import os
import sys

from flagger.app import run
from flagger.cli import get_config_root
from flagger.privilege import reexec_with_privileges


def main() -> None:
    argv = list(sys.argv[1:])
    config_root = get_config_root()
    try:
        result = run(argv, prog_name=sys.argv[0])
    except PermissionError as err:
        if reexec_with_privileges(sys.argv[0], argv, config_root=config_root):
            raise AssertionError("Privilege re-exec unexpectedly returned")
        print(f"flagger: failed: {os.strerror(err.errno)}", file=sys.stderr)
        raise SystemExit(1) from err
    except Exception as err:
        print(f"flagger: failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err

    rendered = result.render(
        quiet="--quiet" in argv,
        json_output="--json" in argv,
        verbose="--verbose" in argv,
    )
    if rendered:
        print(rendered)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
