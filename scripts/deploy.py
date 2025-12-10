from colorama import Fore
import dotenv
from enum import Enum
from nuitka.distutils.DistutilCommands import build as n_build
import os
from pathlib import Path
from subprocess import CalledProcessError, Popen, PIPE, STDOUT
from sys import argv, version_info
import tarfile
import traceback


ref_name = ""
build_os = ""
buildlib = Path(__file__).parents[1] / "build"
toml_file = Path(__file__).parents[1] / "pyproject.toml"
pkg_cfg = "tilia.nuitka-package.config.yml"
outdir = ""
out_filename = ""

if not toml_file.exists():
    options = {}
else:
    if version_info >= (3, 11):
        from tomllib import load
    else:
        from tomli import load

    with open(toml_file, "rb") as f:
        options = load(f)


class P(Enum):
    CMD = Fore.BLUE
    ERROR = Fore.RED


def _print(text: list[str | list[str]], p_type: P | None = None):
    if len(text) == 0 or (len(text) == 1 and not text[0]):
        return
    if p_type:
        print(
            "echo " + p_type.value + "\n".join([t.__str__() for t in text]) + Fore.RESET
        )
    else:
        print("echo ", *text)


def _run_command(cmd: list[str]):
    with Popen(cmd, stdout=PIPE, stderr=STDOUT, bufsize=1, text=True) as p:
        for line in p.stdout:
            _print([line.rstrip("\n")])

    if p.returncode != 0:
        raise CalledProcessError(p.returncode, p.args)


def _handle_inputs():
    assert len(argv) == 3, "Incorrect number of inputs"
    global ref_name, build_os, outdir
    ref_name = argv[1]
    build_os = "-".join(
        [x for x in argv[2].split("-") if not x.isdigit() and x != "latest"]
    )
    outdir = buildlib / build_os


def _get_nuitka_toml() -> list[str]:
    toml_cmds = []
    for option, value in options.get("tool", {}).get("nuitka", {}).items():
        toml_cmds.extend(n_build._parseOptionsEntry(option, value))
    return toml_cmds


def _set_out_filename(name: str, version: str):
    def _clean_version(v: str) -> tuple[str]:
        return v.strip("v ").split(".")

    global out_filename
    if _clean_version(version) == _clean_version(ref_name):
        out_filename = f"{name}-v{version}-{build_os}"
    else:
        out_filename = f"{name}-v{version}[{ref_name}]-{build_os}"


def _get_exe_cmd() -> list[str]:
    name = options.get("project", {}).get("name", "TiLiA")
    version = options.get("project", {}).get("version", "0")
    _set_out_filename(name, version)
    icon_path = Path(__file__).parents[1] / "tilia" / "ui" / "img" / "main_icon.ico"
    exe_args = [
        "python",
        "-m",
        "nuitka",
        f"--output-dir={outdir}",
        "--report=compilation-report.xml",
        "--assume-yes-for-downloads",
        f"--product-name={name}",
        f"--file-version={version}",
        f"--output-filename={out_filename}",
        "--onefile-tempdir-spec={CACHE_DIR}/{PRODUCT}/{VERSION}",
        "--mode=onefile",
    ]
    if "mac" in build_os:
        exe_args.extend(
            [
                f"--macos-app-icon={icon_path}",
                "--macos-app-mode=gui",
                f"--macos-app-version={version}",
            ]
        )
    elif "windows" in build_os:
        exe_args.extend(
            [
                "--windows-console-mode=attach",
                f"--windows-icon-from-ico={icon_path}",
            ]
        )
    else:
        exe_args.extend([f"--linux-icon={icon_path}"])

    return exe_args


def _get_sdist() -> str:
    for f in outdir.iterdir():
        if "".join(f.suffixes[-2:]) == ".tar.gz":
            return f
    raise Exception(f"Could not find sdist in {outdir}:", [*outdir.iterdir()])


def _get_main_file() -> tuple[bool, str]:
    main = _create_lib()
    _update_yml()
    return main


def _create_lib() -> tuple[Path, str, str]:
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
            filter=lambda x, _: x
            if x.name.startswith(tilia)
            or x.name.startswith("TiLiA.egg-info")
            or x.name in ext_data
            else None,
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
        "python",
        "-m",
        "build",
        "--no-isolation",
        "--verbose",
        "--sdist",
        f"--outdir={outdir}",
    ]

    _print(["Building sdist with command:", sdist_cmd], P.CMD)
    _run_command(sdist_cmd)


def _build_exe():
    main_file = _get_main_file()
    exe_cmd = _get_exe_cmd()
    exe_cmd.extend(_get_nuitka_toml())
    exe_cmd.append(main_file)

    _print(["Building exe with command:", exe_cmd], P.CMD)
    _run_command(exe_cmd)


def build():
    _handle_inputs()
    dotenv.set_key("tilia.env", "ENVIRONMENT", "prod")
    if buildlib.exists():
        _print(["Cleaning build folder..."], P.ERROR)
        for root, dirs, files in os.walk(buildlib, False):
            r = Path(root)
            _print(["\t~", r])
            for f in files:
                os.unlink(r / f)
            for d in dirs:
                os.rmdir(r / d)
        os.rmdir(buildlib)

    old_dir = os.getcwd()
    try:
        _build_sdist()
        _build_exe()
        os.chdir(old_dir)
        print(f'export out_filename="{out_filename}"')
    except Exception as e:
        _print(["Build failed!", e.__str__()], P.ERROR)
        _print([traceback.format_exc()])
        os.chdir(old_dir)
        exit(1)


if __name__ == "__main__":
    build()
