import os
import subprocess

from build.create_installer import create_iss_script
from tilia import globals_

os.environ['VERSION'] = "0.1.0"

p = subprocess.Popen('pyinstaller build_exe.spec -y')
p.wait()

create_iss_script(os.environ['VERSION'], globals_.APP_NAME)

path_to_inno = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

p = subprocess.Popen(f'{path_to_inno} installer_script.iss')
p.wait()
