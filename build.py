import subprocess

import tilia.constants

from pathlib import Path

PATH_TO_INNO = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
PATH_TO_INSTALL_SCRIPT_TEMPLATE = Path("tilia", "installers", "win", "template.iss")
PATH_TO_INSTALL_SCRIPT = Path(
    "tilia", "installers", "win", f"tilia_{tilia.constants.VERSION}.iss"
)


def confirm_version_number_update():
    answer = input(
        f"Did you remember to update the version number (current version number is {tilia.constants.VERSION})? y/n "
    )

    if answer.lower() == "y":
        return True
    else:
        return False


def build():
    p = subprocess.Popen("pyinstaller tilia.spec -y")
    p.wait()


def make_installer():
    create_install_script()

    p = subprocess.Popen(f"{PATH_TO_INNO} {PATH_TO_INSTALL_SCRIPT.resolve()}")
    p.wait()


def create_install_script() -> None:
    with open(PATH_TO_INSTALL_SCRIPT_TEMPLATE, "r") as f:
        template = f.read()

    install_script = template.replace("$VERSION$", tilia.constants.VERSION)
    install_script = install_script.replace(
        "$SOURCE_PATH$", Path("").resolve().__str__()
    )

    with open(PATH_TO_INSTALL_SCRIPT, "w") as f:
        f.write(install_script)


def main() -> None:
    if not confirm_version_number_update():
        return

    # build()
    make_installer()


if __name__ == "__main__":
    main()
