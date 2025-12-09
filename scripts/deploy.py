from colorama import Fore
import dotenv
from enum import Enum
from nuitka.distutils.DistutilCommands import build as n_build
import os
from pathlib import Path
from subprocess import check_call
from sys import argv, executable, version_info
import tarfile
import traceback


outdir = Path(__file__).parent.parent / "build"
toml_file = Path(__file__).parent.parent / "pyproject.toml"
pkg_cfg = "tilia.nuitka-package.config.yml"
out_filename = None

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
    if p_type:
        print(p_type.value + "\t".join([t.__str__() for t in text]) + Fore.RESET)
    else:
        print(*text)


def _get_out_filename():
    assert len(argv) == 2, "Incorrect number of inputs"
    global out_filename
    out_filename = argv[1]


def _get_nuitka_toml() -> list[str]:
    toml_cmds = []
    for option, value in options.get("tool", {}).get("nuitka", {}).items():
        toml_cmds.extend(n_build._parseOptionsEntry(option, value))
    return toml_cmds


def _get_exe_cmd() -> list[str]:
    name = options.get("project", {}).get("name", "TiLiA")
    version = options.get("project", {}).get("version", "0")
    icon_path = Path(__file__).parents[1] / "tilia" / "ui" / "img" / "main_icon.ico"
    exe_args = [
        executable,
        "-m",
        "nuitka",
        f"--output-dir={outdir}",
        "--report=compilation-report.xml",
        "--assume-yes-for-downloads",
        f"--product-name={name}",
        f"--file-version={version}",
        "--onefile-tempdir-spec=%CACHE_DIR%/%PRODUCT%/%VERSION%",
        "--mode=onefile",
        f"--output-filename={out_filename}",
        f"--product-name={name}",
        f"--file-version={version}",
    ]
    if "mac" in out_filename:
        exe_args.extend(
            [
                f"--macos-app-icon={icon_path}",
                "--macos-app-mode=gui",
                f"--macos-app-version={version}",
            ]
        )
    elif "windows" in out_filename:
        exe_args.extend(
            [
                "--windows-console-mode=disable",
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
            if x.name.startswith(tilia) or x.name in ext_data
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
        executable,
        "-m",
        "build",
        "--no-isolation",
        "--verbose",
        "--sdist",
        f"--outdir={outdir}",
    ]

    _print(["Building sdist with command:", sdist_cmd], P.CMD)
    check_call(sdist_cmd)


def _build_exe():
    main_file = _get_main_file()
    exe_cmd = _get_exe_cmd()
    exe_cmd.extend(_get_nuitka_toml())
    exe_cmd.append(main_file)

    _print(["Building exe with command:", exe_cmd], P.CMD)
    check_call(exe_cmd)


def build():
    _get_out_filename()
    dotenv.set_key("tilia.env", "ENVIRONMENT", "prod")
    if outdir.exists():
        _print(["Cleaning build folder..."], P.ERROR)
        for root, dirs, files in os.walk(outdir, False):
            r = Path(root)
            print("\t~", r)
            for f in files:
                os.unlink(r / f)
            for d in dirs:
                os.rmdir(r / d)
        os.rmdir(outdir)

    old_dir = os.getcwd()
    try:
        _build_sdist()
        _build_exe()
    except Exception as e:
        _print(["Build failed!", *e.args], P.ERROR)
        traceback.print_exc()
    finally:
        os.chdir(old_dir)


if __name__ == "__main__":
    build()
