# (c) 2023 Michał Górny
# Released under the terms of the MIT license

import functools
import json
import logging
import shutil
import subprocess
import typing

from pathlib import Path

import more_itertools

from flaggie.config import TokenType
from flaggie.mangle import is_wildcard_package


if typing.TYPE_CHECKING:
    import gentoopm


class MatchError(RuntimeError):
    pass


SYSTEM_GENTOOPM_HELPER = r"""
import json
import sys

import gentoopm

from pathlib import Path


def collapse(obj):
    if isinstance(obj, (str, bytes)):
        return [obj.decode() if isinstance(obj, bytes) else obj]
    if isinstance(obj, (list, tuple, set, frozenset)):
        out = []
        for item in obj:
            out.extend(collapse(item))
        return out
    return [str(obj)]


req = json.loads(sys.argv[1])
pm = gentoopm.get_package_manager()
action = req["action"]

if action == "probe":
    print(json.dumps({"ok": True}))
elif action == "match_package":
    package_spec = req["package_spec"]
    parsed = pm.Atom(package_spec)
    matched = sorted({str(pkg.key) for pkg in pm.stack.filter(package_spec)})
    if not matched:
        print(json.dumps({"error": "no_match"}))
    elif len(matched) > 1:
        print(json.dumps({"error": "multiple", "matched": matched}))
    elif parsed.key.category is None:
        print(json.dumps({
            "value": package_spec.replace(str(parsed.key.package), matched[0])
        }))
    else:
        print(json.dumps({"value": package_spec}))
elif action == "get_valid_values":
    package_spec = req["package_spec"]
    token_type = req["token_type"]
    group = req["group"]

    if token_type == "ENV_FILE":
        env_dir = Path(pm.config_root or "/") / "etc/portage/env"
        if not env_dir.is_dir():
            print(json.dumps({"values": []}))
        else:
            print(json.dumps({
                "values": sorted(path.name for path in env_dir.iterdir()
                                  if path.is_file())
            }))
        raise SystemExit(0)

    if package_spec != "*/*" and "/*" in package_spec:
        print(json.dumps({"values": None}))
        raise SystemExit(0)

    group_match = ""
    group_len = 0
    if group is not None:
        group_match = group.lower() + "_"
        group_len = len(group_match)

    values = set()
    values.add("**" if token_type == "KEYWORD" else "*")
    if token_type == "LICENSE":
        values.update(f"@{name}" for name in pm.stack.license_groups)

    if package_spec == "*/*":
        if token_type == "USE_FLAG":
            if group is not None:
                use_expand = pm.stack.use_expand.get(group)
                if use_expand is None or not use_expand.prefixed:
                    print(json.dumps({"values": []}))
                    raise SystemExit(0)
                values.update(use_expand.values)
            else:
                values.update(pm.stack.global_use)
        elif token_type == "KEYWORD":
            values.update(["*", "~*"])
            arches = pm.stack.arches.values()
            values.update(f"~{arch.name}" for arch in arches)
            values.update(arch.name for arch in arches
                          if arch.stability != "testing")
        elif token_type == "LICENSE":
            values.update(pm.stack.licenses)
        elif token_type == "PROPERTY":
            values.update(["interactive", "live", "test_network"])
        elif token_type == "RESTRICT":
            values.update(["fetch", "mirror", "strip", "test", "userpriv"])
            values.update(["binchecks", "bindist", "installsources",
                           "network-sandbox", "preserve-libs", "primaryuri",
                           "splitdebug"])
    else:
        for pkg in pm.stack.filter(package_spec):
            if token_type == "USE_FLAG":
                for flag in pkg.use:
                    flag = flag.lstrip("+-")
                    if flag.lower().startswith(group_match):
                        values.add(flag[group_len:])
            elif token_type == "KEYWORD":
                for keyword in pkg.keywords:
                    if keyword.startswith("-"):
                        continue
                    values.add(keyword)
                    values.add("~*")
                    if not keyword.startswith("~"):
                        values.add("*")
                        values.add(f"~{keyword}")
            elif token_type == "LICENSE":
                values.update(collapse(pkg.license))
            elif token_type == "PROPERTY":
                values.update(collapse(pkg.properties))
            elif token_type == "RESTRICT":
                values.update(collapse(pkg.restrict))

    print(json.dumps({"values": sorted(values)}))
elif action == "split_use_expand":
    flag = req["flag"]
    flag_uc = flag.upper()
    for group in sorted((group.name
                         for group in pm.stack.use_expand.values()
                         if group.prefixed),
                        key=lambda x: -len(x)):
        if flag_uc.startswith(f"{group}_"):
            print(json.dumps({"group": group, "flag": flag[len(group)+1:]}))
            break
    else:
        print(json.dumps({"group": None, "flag": flag}))
else:
    raise RuntimeError(f"Unknown action: {action}")
"""


class SubprocessPM:
    def __init__(self, python_executable: str, config_root: Path):
        self.python_executable = python_executable
        self.config_root = config_root

    def _run(self, payload: dict[str, typing.Any]) -> dict[str, typing.Any]:
        proc = subprocess.run(
            [self.python_executable, "-c", SYSTEM_GENTOOPM_HELPER,
             json.dumps(payload)],
            capture_output=True,
            text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"System package manager helper failed: {proc.stderr.strip()}")
        return typing.cast(dict[str, typing.Any], json.loads(proc.stdout))

    @functools.cache
    def probe(self) -> bool:
        return bool(self._run({"action": "probe"}).get("ok"))

    @functools.cache
    def match_package(self, package_spec: str) -> str:
        data = self._run({
            "action": "match_package",
            "package_spec": package_spec,
        })
        error = data.get("error")
        if error == "no_match":
            raise MatchError(f"{package_spec!r} matched no packages")
        if error == "multiple":
            matched = typing.cast(list[str], data["matched"])
            raise MatchError(
                f"{package_spec!r} is ambigous, matched {', '.join(matched)}")
        return typing.cast(str, data["value"])

    @functools.cache
    def get_valid_values(self,
                         package_spec: str,
                         token_type: TokenType,
                         group: typing.Optional[str],
                         ) -> typing.Optional[frozenset[str]]:
        data = self._run({
            "action": "get_valid_values",
            "package_spec": package_spec,
            "token_type": token_type.name,
            "group": group,
        })
        values = data["values"]
        if values is None:
            return None
        return frozenset(typing.cast(list[str], values))

    @functools.cache
    def split_use_expand(self, flag: str) -> tuple[typing.Optional[str], str]:
        data = self._run({
            "action": "split_use_expand",
            "flag": flag,
        })
        return (typing.cast(typing.Optional[str], data["group"]),
                typing.cast(str, data["flag"]))


def get_subprocess_pm(config_root: Path) -> typing.Optional[SubprocessPM]:
    if config_root != Path("/"):
        return None

    python_executable = shutil.which("python3")
    if python_executable is None:
        return None

    pm = SubprocessPM(python_executable, config_root)
    try:
        if pm.probe():
            return pm
    except Exception:
        pass
    return None


@functools.cache
def _filter_packages(pm: "gentoopm.basepm.PMBase",
                     query: str,
                     ) -> list["gentoopm.basepm.pkg.PMPackage"]:
    return pm.stack.filter(query)


def match_package(pm: typing.Optional["gentoopm.basepm.PMBase"],
                  package_spec: str,
                  ) -> str:
    """
    Match package spec against the repos

    Match the package specification against the repositories provided
    by the package manager instance.  Returns the (possibly expanded)
    package specification or raises an exception.
    """

    if pm is None or is_wildcard_package(package_spec):
        # if PM is not available or we're dealing with wildcards,
        # just perform basic validation
        # TODO: better validation?
        if package_spec.count("/") != 1:
            raise ValueError("Not a valid category/package spec")
        return package_spec

    if isinstance(pm, SubprocessPM):
        return pm.match_package(package_spec)

    parsed = pm.Atom(package_spec)
    matched = frozenset(str(pkg.key)
                        for pkg in _filter_packages(pm, package_spec))
    if not matched:
        raise MatchError(f"{package_spec!r} matched no packages")
    if len(matched) > 1:
        raise MatchError(
            f"{package_spec!r} is ambigous, matched {', '.join(matched)}")

    if parsed.key.category is None:
        # if user did not specify the category, copy it from the match
        # TODO: have gentoopm provide a better API for modifying atoms?
        return package_spec.replace(str(parsed.key.package), str(*matched))

    return package_spec


@functools.cache
def get_valid_values(pm: typing.Optional["gentoopm.basepm.PMBase"],
                     package_spec: str,
                     token_type: TokenType,
                     group: typing.Optional[str],
                     ) -> typing.Optional[set[str]]:
    """Get a list of valid values for (package, token type, group)"""

    if pm is None:
        return None

    if isinstance(pm, SubprocessPM):
        return pm.get_valid_values(package_spec, token_type, group)

    # env files are global by design
    if token_type == TokenType.ENV_FILE:
        env_dir = Path(pm.config_root or "/") / "etc/portage/env"
        if not env_dir.is_dir():
            logging.debug(f"{env_dir} is not a directory, no valid "
                          f"{token_type.name} values")
            return set()
        values = set(path.name for path in env_dir.iterdir() if path.is_file())
        logging.debug(f"Valid values for {token_type.name}: {values}")
        return values

    # wildcard packages not supported
    if package_spec != "*/*" and is_wildcard_package(package_spec):
        return None

    group_match = ""
    group_len = 0
    if group is not None:
        group_match = group.lower() + "_"
        group_len = len(group_match)

    values = set()
    values.add("**" if token_type == TokenType.KEYWORD else "*")
    if token_type == TokenType.LICENSE:
        values.update(f"@{name}" for name in pm.stack.license_groups)

    if package_spec == "*/*":
        if token_type == TokenType.USE_FLAG:
            if group is not None:
                use_expand = pm.stack.use_expand.get(group)
                if use_expand is None:
                    logging.debug(
                        f"{token_type.name} group: {group} is not valid")
                    return set()
                if not use_expand.prefixed:
                    logging.debug(
                        f"{token_type.name} group: {group} is not prefixed")
                    return set()
                values.update(use_expand.values)
            else:
                # NB: we deliberately ignore use_expand, as flaggie
                # is expected to have detected it and set the group
                values.update(pm.stack.global_use)
        elif token_type == TokenType.KEYWORD:
            values.update(["*", "~*"])
            arches = pm.stack.arches.values()
            values.update(f"~{arch.name}" for arch in arches)
            values.update(arch.name for arch in arches
                          if arch.stability != "testing")
        elif token_type == TokenType.LICENSE:
            values.update(pm.stack.licenses)
        elif token_type == TokenType.PROPERTY:
            # The PMs do not keep easily accessible lists of supported
            # PROPERTIES/RESTRICT values.  We could use *-allowed
            # from layout.conf but that would limit the available set
            # to these explicitly supported in ::gentoo.  Hardcoding
            # the complete set is also easier.

            # PMS-defined values
            values.update(["interactive", "live", "test_network"])
        elif token_type == TokenType.RESTRICT:
            # PMS-defined values
            values.update(["fetch", "mirror", "strip", "test", "userpriv"])
            # Additional Portage-defined values
            values.update(["binchecks", "bindist", "installsources",
                           "network-sandbox", "preserve-libs", "primaryuri",
                           "splitdebug",
                           ])
        else:
            assert False, f"Unhandled token type {token_type.name}"
    else:
        for pkg in _filter_packages(pm, package_spec):
            if token_type == TokenType.USE_FLAG:
                for flag in pkg.use:
                    flag = flag.lstrip("+-")
                    if flag.lower().startswith(group_match):
                        values.add(flag[group_len:])
            elif token_type == TokenType.KEYWORD:
                for keyword in pkg.keywords:
                    if keyword.startswith("-"):
                        continue
                    values.add(keyword)
                    values.add("~*")
                    if not keyword.startswith("~"):
                        values.add("*")
                        # allow ~arch even if the package is stable already
                        # https://github.com/projg2/flaggie/issues/42
                        values.add(f"~{keyword}")
            elif token_type == TokenType.LICENSE:
                values.update(more_itertools.collapse(pkg.license))
            elif token_type == TokenType.PROPERTY:
                values.update(more_itertools.collapse(pkg.properties))
            elif token_type == TokenType.RESTRICT:
                values.update(more_itertools.collapse(pkg.restrict))
            else:
                assert False, f"Unhandled token type {token_type.name}"

    logging.debug(
        f"Valid values for {package_spec} {token_type.name} group: {group}: "
        f"{values}")
    return values


@functools.cache
def split_use_expand(pm: typing.Optional["gentoopm.basepm.PMBase"],
                     flag: str,
                     ) -> tuple[typing.Optional[str], str]:
    """Split given flag into (group, name) using USE_EXPAND"""

    if isinstance(pm, SubprocessPM):
        return pm.split_use_expand(flag)

    if pm is not None:
        flag_uc = flag.upper()
        # start with longest first, in case they overlap
        for group in sorted((group.name
                             for group in pm.stack.use_expand.values()
                             if group.prefixed),
                            key=lambda x: -len(x)):
            if flag_uc.startswith(f"{group}_"):
                return (group, flag[len(group)+1:])

    return (None, flag)
