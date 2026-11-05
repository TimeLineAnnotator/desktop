"""
Script to build TiLiA with Nuitka.
(a more flexible alternative to building with only pyside-deploy or Nuitka)
pyside-deploy has very limited Nuitka-specific options and Nuitka requires a specific file structure to build.
Hence this pyside-deploy-inspired script.

- Run `python scripts/deploy.py [ref_name] [os_type]`. Both arguments are
  optional; see `--help`. CI passes the git ref and the runner image name.
- Builds the executable directly from the editable install (no sdist step).
  Generates a Nuitka package config from the static YAML + dynamic
  data-files / implicit-imports entries. The app lands in
  build/[os_type]/exe/ (tilia.dist/ on Windows and Linux, a .app bundle on macOS).
- Then packs it into an installer with Velopack's `vpk` CLI, into
  build/[os_type]/velopack/. Locally, this step is skipped when `vpk` is not
  on PATH; in CI it is required.
- CI uploads the result under the versioned artifact name
    TiLiA-v[tilia version](-[ref_name, if different])-[os_type]
"""

import argparse
import os
import platform
import re
import shutil
import sys
import traceback
from enum import Enum
from pathlib import Path
from subprocess import check_call, check_output

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
    from tomllib import load

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


def _project_name() -> str:
    return options.get("project", {}).get("name", "TiLiA")


def _project_version() -> str:
    return options.get("project", {}).get("version", "0")


def _semver_version() -> str:
    """Return the project version, validated as strict semver (MAJOR.MINOR.PATCH).

    Velopack's runtime requires exactly 3 non-negative integer parts; versions
    like 1.0.0.1 cause a 'Semver parse error' at install time.
    """
    version = _project_version()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(
            f"Version '{version}' in pyproject.toml is not valid semver "
            f"(expected MAJOR.MINOR.PATCH)."
        )
    return version


def _stable_exe_name() -> str:
    """Stable executable name used by Velopack (--mainExe)."""
    name = _project_name()
    if "mac" in build_os:
        return _macos_app_bundle().name
    elif "windows" in build_os:
        return f"{name}.exe"
    else:
        return name


# Values build_os can take. They double as Velopack update channels, so the
# auto-updater relies on them staying the same.
OS_TYPES = ("windows", "macos-silicon", "macos-intel", "ubuntu")


def _host_os_type() -> str:
    """The os type of the machine running this script (Nuitka can't cross-compile)."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        # platform.machine() reports the interpreter's architecture, which is
        # what Nuitka compiles for (x86_64 under Rosetta).
        return "macos-silicon" if platform.machine() == "arm64" else "macos-intel"
    return "ubuntu"


def _normalize_os_type(raw: str) -> str:
    # In a GitHub Actions runner, the runner image looks like someOS-latest,
    # someOS-22.04, macos-15-intel, etc. We strip "latest" and any version
    # numbers, keeping just someOS. macos-latest is Apple Silicon.
    if "macos" in raw and "intel" not in raw:
        return "macos-silicon"
    return "-".join(
        x
        for x in raw.split("-")
        if not x.replace(".", "", 1).isdigit() and x != "latest"
    )


def _handle_inputs():
    parser = argparse.ArgumentParser(
        description="Build a stand-alone TiLiA executable with Nuitka and, if "
        "Velopack's `vpk` CLI is on PATH, an installer."
    )
    parser.add_argument(
        "ref_name",
        nargs="?",
        default="",
        help="git ref being built. Only used in the name CI gives the "
        "uploaded artifact. Defaults to the version in pyproject.toml.",
    )
    parser.add_argument(
        "os_type",
        nargs="?",
        default=None,
        help=f"one of {', '.join(OS_TYPES)}, or a GitHub runner image name "
        "such as windows-latest. Must match this machine. Defaults to this "
        f"machine's ({_host_os_type()}).",
    )
    args = parser.parse_args()

    global ref_name, build_os, outdir
    ref_name = args.ref_name
    host_os = _host_os_type()
    build_os = host_os if args.os_type is None else _normalize_os_type(args.os_type)
    if build_os not in OS_TYPES:
        parser.error(
            f"unknown os_type {args.os_type!r}. Use one of {', '.join(OS_TYPES)}, "
            "or leave it out to build for this machine."
        )
    if build_os != host_os:
        parser.error(
            f"os_type {build_os!r} does not match this machine ({host_os!r}). "
            "Nuitka can't cross-compile: build on the target platform, or leave "
            "os_type out."
        )
    outdir = buildlib / build_os


def _get_nuitka_toml() -> list[str]:
    toml_cmds = []
    for option, value in options.get("tool", {}).get("nuitka", {}).items():
        toml_cmds.extend(n_build._parseOptionsEntry(option, value))
    return toml_cmds


def _set_out_filename():
    def _clean_version(v: str) -> list[str]:
        return v.strip("v ").split(".")

    global out_filename
    name = _project_name()
    version = _semver_version()
    if not ref_name or _clean_version(version) == _clean_version(ref_name):
        out_filename = f"{name}-v{version}-{build_os}"
    else:
        safe_ref = ref_name.replace("/", "-")
        out_filename = f"{name}-v{version}-{safe_ref}-{build_os}"


def _get_exe_cmd() -> list[str]:
    name = _project_name()
    version = _semver_version()
    _set_out_filename()
    icon_path = root / "docs" / "img" / "main_icon.ico"
    exe_args = [
        sys.executable,
        "-m",
        "nuitka",
        f"--output-dir={(outdir / 'exe').as_posix()}",
        f"--product-name={name}",
        f"--file-version={version}",
        # macOS's default filesystem is case-insensitive: an output filename
        # that is a pure case-variant of the "tilia" package (e.g. "TiLiA")
        # collides with Nuitka's own Contents/MacOS/tilia/ data-files
        # directory - NotADirectoryError partway through the build. Windows
        # and Linux don't have this problem ("TiLiA.exe" has an extension;
        # Linux's filesystem is case-sensitive), so only mac needs a name
        # that isn't just "tilia" with different casing.
        (
            f"--output-filename={name}-bin"
            if "mac" in build_os
            else f"--output-filename={name}"
        ),
        f"--macos-app-icon={icon_path.as_posix()}",
        "--macos-app-mode=gui",
        f"--macos-app-name={name}",
        f"--macos-app-version={version}",
        "--windows-console-mode=attach",
        f"--windows-icon-from-ico={icon_path.as_posix()}",
        f"--linux-icon={icon_path.as_posix()}",
        # macOS always uses app-bundle mode; standalone is for Windows/Linux only.
        "--mode=app" if "mac" in build_os else "--mode=standalone",
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


def _build_exe():
    cfg_path = _write_pkg_cfg()
    main_file = root / "tilia"

    exe_cmd = _get_exe_cmd()
    exe_cmd.extend(_get_nuitka_toml())
    exe_cmd.append(f"--user-package-configuration-file={cfg_path.as_posix()}")
    # Embed the distribution metadata explicitly. The YAML `include-metadata`
    # entry alone is dropped when top_level.txt lists a non-compiled package
    # (e.g. a stray `htmlcov/`) first; the CLI flag uses reason "user requested"
    # which bypasses Nuitka's hasDoneModule gate. See constants.py runtime read.
    exe_cmd.append(f"--include-distribution-metadata={_project_name()}")
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


def _build_velopack(main_exe: str):
    name = _project_name()
    version = _semver_version()
    icon_path = root / "docs" / "img" / "main_icon.ico"
    vpk_out = outdir / "velopack"
    vpk_out.mkdir(parents=True, exist_ok=True)

    if os.environ.get("GH_TOKEN"):
        try:
            tag = check_output(
                [
                    "gh",
                    "release",
                    "list",
                    "--limit",
                    "1",
                    "--exclude-pre-releases",
                    "--json",
                    "tagName",
                    "--jq",
                    ".[0].tagName",
                ],
                text=True,
            ).strip()
            if tag:
                check_call(
                    [
                        "gh",
                        "release",
                        "download",
                        tag,
                        "--pattern",
                        f"*-{build_os}-full.nupkg",
                        "--dir",
                        vpk_out.as_posix(),
                        "--skip-existing",
                    ]
                )
                _print(["Downloaded previous full package for delta generation."], P.OK)
            else:
                _print(["No previous release found; skipping delta generation."])
        except Exception:
            _print(["No previous full package found; skipping delta generation."])

    if "mac" in build_os:
        # Velopack macOS: --packDir is the .app bundle, --mainExe is the binary inside it
        pack_dir = _macos_app_bundle()
    else:
        # Nuitka names the dist dir after the package (tilia.dist/), not the script.
        pack_dir = outdir / "exe" / "tilia.dist"

    vpk_cmd = [
        "vpk",
        "pack",
        "--verbose",
        f"--packId={name}",
        f"--packVersion={version}",
        f"--packDir={pack_dir.as_posix()}",
        f"--outputDir={vpk_out.as_posix()}",
        f"--mainExe={main_exe}",
        f"--channel={build_os}",
    ]
    if "windows" in build_os:
        vpk_cmd.append(f"--icon={icon_path.as_posix()}")
    if "ubuntu" not in build_os:
        vpk_cmd.append("--noPortable")

    _print(["Packaging with Velopack:", vpk_cmd], P.CMD)
    check_call(vpk_cmd)
    _print(["Velopack packaging complete!"], P.OK)

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"vpk-outdir={vpk_out.as_posix()}\n")
            f.write(f"pack-version={version}\n")


def _patch_macos_plist() -> str:
    """Patch Info.plist with .tla file associations. Returns CFBundleExecutable."""
    import plistlib

    from tilia.constants import FILE_EXTENSION

    name = _project_name()
    uti = f"com.{name.lower()}-app.{FILE_EXTENSION}"
    plist_path = _macos_app_bundle() / "Contents" / "Info.plist"

    with open(plist_path, "rb") as f:
        info = plistlib.load(f)

    info.setdefault("CFBundleDocumentTypes", []).append(
        {
            "CFBundleTypeName": f"{name} File",
            "CFBundleTypeRole": "Editor",
            "CFBundleTypeExtensions": [FILE_EXTENSION],
            "LSItemContentTypes": [uti],
        }
    )
    info.setdefault("UTExportedTypeDeclarations", []).append(
        {
            "UTTypeIdentifier": uti,
            "UTTypeDescription": f"{name} File",
            "UTTypeConformsTo": ["public.data"],
            "UTTypeTagSpecification": {"public.filename-extension": [FILE_EXTENSION]},
        }
    )
    with open(plist_path, "wb") as f:
        plistlib.dump(info, f)

    return info["CFBundleExecutable"]


def _dist_dir() -> Path:
    """Path to the Nuitka standalone dist directory (Windows/Linux)."""
    return outdir / "exe" / "tilia.dist"


def _check_python_version():
    # Nuitka 4.3.1 crashes compiling TiLiA on Python 3.14 with
    # AttributeError: 'ExpressionBuiltinSlice2' object has no attribute
    # 'subnode_lower'. Fail up front instead of minutes into the compile.
    from nuitka.Version import getNuitkaVersion

    nuitka_version = getNuitkaVersion()
    parts = tuple(int(n) for n in re.findall(r"\d+", nuitka_version)[:3])
    if sys.version_info >= (3, 14) and parts <= (4, 3, 1):
        raise SystemExit(
            f"Nuitka {nuitka_version} can't compile TiLiA on Python "
            f"{platform.python_version()}. Build with Python 3.12 or 3.13."
        )


def _app_path() -> Path:
    return _macos_app_bundle() if "mac" in build_os else _dist_dir()


def _package(main_exe: str):
    if shutil.which("vpk"):
        _build_velopack(main_exe)
    elif os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError("Velopack's `vpk` CLI is not on PATH.")
    else:
        _print(
            [
                "Skipped the installer: Velopack's `vpk` CLI is not on PATH.",
                "To build one too, install the .NET SDK and run "
                "`dotnet tool install -g vpk --prerelease`.",
            ]
        )


def build():
    _handle_inputs()
    _check_python_version()
    env_file = root / ".tilia.env"
    old_env_var = dotenv.dotenv_values(env_file).get("ENVIRONMENT") or ""
    dotenv.set_key(env_file, "ENVIRONMENT", "prod")
    # Everything after the line above sits in the try, and the restore in the
    # finally: a failed cleanup or a Ctrl+C mid-compile must not leave
    # ENVIRONMENT=prod behind for the next run from source.
    try:
        if buildlib.exists():
            _print(["Cleaning build folder..."], P.ERROR)
            shutil.rmtree(buildlib)
        _build_exe()
        is_mac = "mac" in build_os
        app_path = _app_path()
        stable_exe = _stable_exe_name()
        out_binary_name = _patch_macos_plist() if is_mac else stable_exe
        _package(out_binary_name)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"out-filepath={app_path.as_posix()}\n")
                f.write(f"out-filename={out_filename}\n")
                f.write(f"out-binary-name={out_binary_name}\n")
                f.write(f"stable-exe-name={stable_exe}\n")
        app = app_path if is_mac else app_path / out_binary_name
        _print([f"App: {app}"], P.OK)
    except Exception as e:
        _print(["Build failed!", e.__str__()], P.ERROR)
        _print([traceback.format_exc()])
        raise SystemExit(1) from e
    finally:
        dotenv.set_key(env_file, "ENVIRONMENT", old_env_var)


if __name__ == "__main__":
    build()
