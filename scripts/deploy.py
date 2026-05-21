"""
Script to build TiLiA with Nuitka.
(a more flexible alternative to building with only pyside-deploy or Nuitka)
pyside-deploy has very limited Nuitka-specific options and Nuitka requires a specific file structure to build.
Hence this pyside-deploy-inspired script.

- Run `python scripts/deploy.py [ref_name] [os_type]`
- Builds the executable directly from the editable install (no sdist step).
  Generates a Nuitka package config from the static YAML + dynamic
  data-files / implicit-imports entries, then renames the output to the
  versioned artifact name for GitHub upload:
    build/[os_type]/exe/TiLiA-[tilia version](-[ref_name, if different])-[os_type]
"""

import os
import sys
import traceback
from enum import Enum
from pathlib import Path
from subprocess import check_call

import dotenv
from colorama import Fore
from lxml import etree
from nuitka.distutils.DistutilsCommands import build as n_build

root = Path(__file__).parents[1]
ref_name = ""
build_os = ""
buildlib = root / "build"
toml_file = root / "pyproject.toml"
pkg_cfg = root / "tilia.nuitka-package.config.yml"
outdir = Path()
out_filename = ""

if not toml_file.exists():
    options = {}
else:
    if sys.version_info >= (3, 11):
        from tomllib import load
    else:
        from tomli import load

    with open(toml_file, "rb") as f:
        options = load(f)


class P(Enum):
    CMD = Fore.BLUE
    ERROR = Fore.RED
    OK = Fore.GREEN


def _print(text: list[str | list[str]], p_type: P | None = None):
    if not text:
        return
    formatted_text = "\n".join([t.__str__() for t in text])
    if p_type:
        formatted_text = p_type.value + formatted_text + Fore.RESET
    sys.stdout.write(formatted_text + "\n")


def _handle_inputs():
    assert len(sys.argv) == 3, "Incorrect number of inputs"
    global ref_name, build_os, outdir
    ref_name = sys.argv[1]
    # in a git action runner, sys.argv[2] could look like someOS-latest, someOS-22.02, etc, where someOS is probably macos, ubuntu or windows.
    # we save build_os as the runner os stripped of "latest" and any digits: just someOS.
    if "macos" in sys.argv[2] and "intel" not in sys.argv[2]:
        build_os = "macos-silicon"
        # to identify the difference between macos-silicon and macos-intel. currently uses the images macos-latest and macos-15-intel (which are silicon and intel respectively.)
    else:
        build_os = "-".join(
            [
                x
                for x in sys.argv[2].split("-")
                if not x.replace(".", "", 1).isdigit() and x != "latest"
            ]
        )
    outdir = buildlib / build_os


def _get_nuitka_toml() -> list[str]:
    toml_cmds = []
    for option, value in options.get("tool", {}).get("nuitka", {}).items():
        toml_cmds.extend(n_build._parseOptionsEntry(option, value))
    return toml_cmds


def _set_out_filename(name: str, version: str):
    def _clean_version(v: str) -> list[str]:
        return v.strip("v ").split(".")

    global out_filename
    if _clean_version(version) == _clean_version(ref_name):
        out_filename = f"{name}-v{version}-{build_os}"
    else:
        safe_ref = ref_name.replace("/", "-")
        out_filename = f"{name}-v{version}-{safe_ref}-{build_os}"


def _get_exe_cmd() -> list[str]:
    name = options.get("project", {}).get("name", "TiLiA")
    version = options.get("project", {}).get("version", "0")
    _set_out_filename(name, version)
    icon_path = root / "docs" / "img" / "main_icon.ico"
    exe_args = [
        sys.executable,
        "-m",
        "nuitka",
        f"--output-dir={(outdir / 'exe').as_posix()}",
        f"--product-name={name}",
        f"--file-version={version}",
        f"--output-filename={out_filename}",
        f"--macos-app-icon={icon_path.as_posix()}",
        "--macos-app-mode=gui",
        f"--macos-app-name={name}",
        f"--macos-app-version={version}",
        "--windows-console-mode=attach",
        f"--windows-icon-from-ico={icon_path.as_posix()}",
        f"--linux-icon={icon_path.as_posix()}",
    ]

    return exe_args


def _get_implicit_imports():
    from tilia.utils import get_sibling_packages

    tls = [
        tl + ".timeline"
        for tl in get_sibling_packages(
            "tilia.timelines.base.timeline",
            (root / "tilia/timelines/base/timeline").as_posix(),
        )
    ]
    tluis = get_sibling_packages(
        "tilia.ui.timelines.base.timeline",
        (root / "tilia/ui/timelines/base/timeline").as_posix(),
    )
    return tls + tluis


def _write_pkg_cfg() -> Path:
    import yaml

    with open(pkg_cfg) as f:
        yml = yaml.safe_load(f)

    yml.append(
        {
            "module-name": "tilia",
            "data-files": [
                {
                    "patterns": [
                        e
                        for e in options.get("tool", {})
                        .get("setuptools", {})
                        .get("package-data", {})
                        .get("tilia", [])
                    ]
                },
                {"include-metadata": ["TiLiA"]},
            ],
            "implicit-imports": [{"depends": _get_implicit_imports()}],
        }
    )

    out_cfg = outdir / "tilia.nuitka-package.config.yml"
    out_cfg.parent.mkdir(parents=True, exist_ok=True)
    with open(out_cfg, "w") as f:
        yaml.dump(yml, f)

    return out_cfg


def _macos_app_bundle() -> Path:
    apps = list((outdir / "exe").glob("*.app"))
    assert len(apps) == 1, f"Expected 1 .app bundle, found: {apps}"
    return apps[0]


def _macos_binary_name() -> str:
    """Return CFBundleExecutable from the built .app bundle's Info.plist."""
    import plistlib

    plist_path = _macos_app_bundle() / "Contents" / "Info.plist"
    with open(plist_path, "rb") as f:
        return plistlib.load(f)["CFBundleExecutable"]


def _build_exe():
    cfg_path = _write_pkg_cfg()
    main_file = root / "tilia" / "__main__.py"

    exe_cmd = _get_exe_cmd()
    exe_cmd.extend(_get_nuitka_toml())
    exe_cmd.append(f"--user-package-configuration-file={cfg_path.as_posix()}")
    exe_cmd.append(main_file.as_posix())

    _print(["Building exe with command:", exe_cmd], P.CMD)
    check_call(exe_cmd)
    _print(["Build complete!"], P.OK)
    _print(["Compilation report:"])
    _print(
        [
            etree.tostring(
                etree.parse(root / "compilation-report.xml"),
                pretty_print=True,
                encoding=str,
            )
        ]
    )


def build():
    _handle_inputs()
    env_file = root / ".tilia.env"
    old_env_var = dotenv.dotenv_values(env_file).get("ENVIRONMENT") or ""
    dotenv.set_key(env_file, "ENVIRONMENT", "prod")
    if buildlib.exists():
        _print(["Cleaning build folder..."], P.ERROR)
        for r, dirs, files in os.walk(buildlib, False):
            p = Path(r)
            _print([f"\t~{p}"])
            for f in files:
                os.unlink(p / f)
            for d in dirs:
                os.rmdir(p / d)
        os.rmdir(buildlib)

    try:
        _build_exe()
        if os.environ.get("GITHUB_OUTPUT"):
            if "mac" in build_os:
                out_filepath = _macos_app_bundle()
                out_binary_name = _macos_binary_name()
            else:
                out_filepath = outdir / "exe" / out_filename
                out_binary_name = out_filename
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"out-filepath={out_filepath.as_posix()}\n")
                f.write(f"out-filename={out_filename}\n")
                f.write(f"out-binary-name={out_binary_name}\n")
        dotenv.set_key(env_file, "ENVIRONMENT", old_env_var)
    except Exception as e:
        _print(["Build failed!", e.__str__()], P.ERROR)
        _print([traceback.format_exc()])
        dotenv.set_key(env_file, "ENVIRONMENT", old_env_var)
        raise SystemExit(1) from e


if __name__ == "__main__":
    build()
