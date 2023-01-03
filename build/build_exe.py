import os
import subprocess

from build.create_installer import create_iss_script
from tilia import globals_


def confirm_version_number_update():
    answer = input("Did you remember to update the version number? y/n")

    if answer.lower() == "y":
        return True
    else:
        return False


def make_pyinstaller_build():
    p = subprocess.Popen("pyinstaller build_exe.spec -y")
    p.wait()


def make_installer():
    create_iss_script(globals_.VERSION, globals_.APP_NAME)

    path_to_inno = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

    p = subprocess.Popen(f"{path_to_inno} installer_script.iss")
    p.wait()


def main() -> None:
    if not confirm_version_number_update():
        return

    make_pyinstaller_build()
    make_installer()


if __name__ == "__main__":
    main()
