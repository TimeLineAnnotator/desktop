import sys
from pathlib import Path
import platform
import subprocess
import traceback
import webbrowser

sys.path[0] = Path(__file__).parents[1].__str__()


def deps_debug(exc: ImportError):
    root_path = Path(
        [*traceback.walk_tb(exc.__traceback__)][0][0].f_code.co_filename
    ).parent
    lib_path = root_path / "PySide6/qt-plugins/platforms/libqxcb.so"
    if not lib_path.exists():
        print(
            "Could not find libqxcb.so file.\nDumping all files in tree for debug...\n",
            subprocess.getoutput(f"ls {root_path.as_posix()} -ltraR"),
        )
        raise RuntimeError(
            "Could not locate the necessary libraries to run TiLiA."
        ) from exc

    _, result = subprocess.getstatusoutput(f"ldd {lib_path.as_posix()}")
    if "=> not found" in result:
        missing_deps = []
        for line in result.splitlines():
            if "=> not found" in line:
                dep = line.strip().rstrip(" => not found")
                missing_deps.append(dep)

        from tilia.constants import WEBSITE_URL  # noqa: E402

        distro = platform.freedesktop_os_release().get("ID_LIKE", "").split()[0]
        link = f"{WEBSITE_URL}/help/installation?distro={distro}#troubleshooting-linux"
        if missing_deps:
            print(
                f"""TiLiA could not start due to missing system dependencies.
Visit <{link}> for help on installation.
Missing libraries:
{missing_deps}"""
            )
            webbrowser.open(link)

    raise RuntimeError("Install the necessary dependencies then restart.") from exc


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
