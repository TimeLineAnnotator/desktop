import sys
from pathlib import Path
import platform
import subprocess
import traceback
import webbrowser

sys.path[0] = Path(__file__).parents[1].__str__()


def deps_debug(exc: ImportError):
    from tilia.constants import EMAIL, GITHUB_URL, WEBSITE_URL  # noqa: E402

    def _raise_deps_error(exc: ImportError, message: list[str]):
        raise RuntimeError("\n".join(message)) from exc

    distro = platform.freedesktop_os_release().get("ID_LIKE", "").split()[0]
    link = f"{WEBSITE_URL}/help/installation?distro={distro}#troubleshooting-linux"
    root_path = Path(
        [*traceback.walk_tb(exc.__traceback__)][0][0].f_code.co_filename
    ).parent
    lib_path = root_path / "PySide6/qt-plugins/platforms/libqxcb.so"

    if not lib_path.exists():
        if "__compiled__" not in globals():
            msg = [
                "Could not locate the necessary libraries to run TiLiA. libqxcb.so file not found.",
                "Did you forget to install python dependencies?",
            ]
        else:
            msg = [
                "Could not locate the necessary libraries to run TiLiA. libqxcb.so file not found.",
                f"Open an issue on our repo at <{GITHUB_URL}> or contact us at <{EMAIL}> for help.\n"
                "Dumping all files in tree for debug...",
                subprocess.getoutput(f"ls {root_path.as_posix()} -ltraR"),
            ]
        _raise_deps_error(exc, msg)

    deps = subprocess.getoutput(f"ldd {lib_path.as_posix()}")
    if "=> not found" in deps:
        missing_deps = []
        for line in deps.splitlines():
            if "=> not found" in line:
                dep = line.strip().rstrip(" => not found")
                missing_deps.append(dep)

        if missing_deps:
            deps = f"Missing libraries:\n{missing_deps}"

    msg = [
        "TiLiA could not start due to missing system dependencies.",
        f"Visit <{link}> for help on installation.",
        "Install the necessary dependencies then restart.\n",
        deps,
    ]
    webbrowser.open(link)
    _raise_deps_error(exc, msg)


def main():
    try:
        from tilia.boot import boot  # noqa: E402

        boot()
    except ImportError as exc:
        if sys.platform != "linux":
            raise exc
        deps_debug(exc)


if __name__ == "__main__":
    main()
