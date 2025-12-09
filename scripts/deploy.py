from colorama import Fore
import dotenv
from enum import Enum
from lxml import etree
from nuitka.distutils.DistutilsCommands import build as n_build
import os
from pathlib import Path
from subprocess import check_call
import sys
import tarfile
import traceback


ref_name = ""
build_os = ""
buildlib = Path(__file__).parents[1] / "build"
toml_file = Path(__file__).parents[1] / "pyproject.toml"
pkg_cfg = "tilia.nuitka-package.config.yml"
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
        out_filename = f"{name}-v{version}-{ref_name}-{build_os}"


def _get_exe_cmd() -> list[str]:
    name = options.get("project", {}).get("name", "TiLiA")
    version = options.get("project", {}).get("version", "0")
    _set_out_filename(name, version)
    icon_path = Path(__file__).parents[1] / "tilia" / "ui" / "img" / "main_icon.ico"
    exe_args = [
        sys.executable,
        "-m",
        "nuitka",
        f"--output-dir={outdir}/exe",
        f"--product-name={name}",
        f"--file-version={version}",
        f"--output-filename={out_filename}",
        # "--onefile-tempdir-spec={CACHE_DIR}/{PRODUCT}/{VERSION}",
        f"--macos-app-icon={icon_path}",
        "--macos-app-mode=gui",
        f"--macos-app-version={version}",
        "--windows-console-mode=attach",
        f"--windows-icon-from-ico={icon_path}",
        f"--linux-icon={icon_path}",
    ]
    if "macos" in build_os:
        exe_args.append("--mode=app")
    else:
        exe_args.append("--mode=onefile")

    return exe_args


def _get_sdist() -> Path:
    for f in outdir.iterdir():
        if "".join(f.suffixes[-2:]) == ".tar.gz":
            return f
    raise Exception(f"Could not find sdist in {outdir}:", [*outdir.iterdir()])


def _get_main_file() -> Path:
    main = _create_lib()
    _update_yml()
    return main


def _create_lib() -> Path:
    sdist = _get_sdist()
    base = ".".join(sdist.name.split(".")[:-2])
    tilia = f"{base}/tilia"
    lib = outdir / "Lib"

    ext_data = [
        f"{base}/{e[3:]}"
        for e in options.get("tool", {})
        .get("setuptools", {})
        .get("package-data", {})
        .get("tilia", [])
        if e.split("/")[0] == ".."
    ]

    with tarfile.open(sdist) as f:
        main = f"{tilia}/__main__.py"
        assert main in f.getnames(), f"Could not locate {main}"
        f.extractall(
            lib,
            filter=lambda x, _: (
                x
                if x.name.startswith(tilia)
                or x.name.startswith("TiLiA.egg-info")
                or x.name in ext_data
                else None
            ),
        )

    os.chdir(lib / base)
    return lib / tilia


def _update_yml():
    if not Path(pkg_cfg).exists():
        return

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
                        if pkg_cfg not in e
                    ]
                },
                {"include-metadata": ["TiLiA"]},
            ],
        }
    )

    with open(pkg_cfg, "w") as f:
        yaml.dump(yml, f)


def _build_sdist():
    sdist_cmd = [
        sys.executable,
        "-m",
        "build",
        "--no-isolation",
        "--verbose",
        "--sdist",
        f"--outdir={outdir.as_posix()}",
    ]

    _print(["Building sdist with command:", sdist_cmd], P.CMD)
    check_call(sdist_cmd)


def _build_exe():
    main_file = _get_main_file()
    exe_cmd = _get_exe_cmd()
    exe_cmd.extend(_get_nuitka_toml())
    exe_cmd.append(main_file.as_posix())

    _print(["Building exe with command:", exe_cmd], P.CMD)
    check_call(exe_cmd)
    _print(["Build complete!"], P.OK)
    _print(["Compilation report:"])
    _print(
        [
            etree.tostring(
                etree.parse(main_file.parent / "compilation-report.xml"),
                pretty_print=True,
                encoding=str,
            )
        ]
    )


def build():
    _handle_inputs()
    old_env_var = dotenv.dotenv_values(".tilia.env").get("ENVIRONMENT", "")
    dotenv.set_key(".tilia.env", "ENVIRONMENT", "prod")
    if buildlib.exists():
        _print(["Cleaning build folder..."], P.ERROR)
        for root, dirs, files in os.walk(buildlib, False):
            r = Path(root)
            _print([f"\t~{r}"])
            for f in files:
                os.unlink(r / f)
            for d in dirs:
                os.rmdir(r / d)
        os.rmdir(buildlib)

    old_dir = os.getcwd()
    try:
        _build_sdist()
        _build_exe()
        if os.environ.get("GITHUB_OUTPUT"):
            if "mac" in build_os:
                global outdir
                outdir = outdir / "tilia.app" / "Contents" / "MacOS"
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"out-filepath={(outdir / 'exe' / out_filename).as_posix()}\n")
                f.write(f"out-filename={out_filename}\n")
        os.chdir(old_dir)
        dotenv.set_key(".tilia.env", "ENVIRONMENT", old_env_var)
    except Exception as e:
        _print(["Build failed!", e.__str__()], P.ERROR)
        _print([traceback.format_exc()])
        os.chdir(old_dir)
        dotenv.set_key(".tilia.env", "ENVIRONMENT", old_env_var)
        raise SystemExit(1) from e


if __name__ == "__main__":
    build()
