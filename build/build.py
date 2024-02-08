import subprocess

import tilia.constants

from pathlib import Path

README_PATH = Path(Path().absolute().resolve().parent, "README.md")
LICENSE_PATH = Path(Path().absolute().resolve().parent, "LICENSE")


def confirm_version_number_update():
    answer = input(
        f"Did you remember to update the version number (current version number is {tilia.constants.VERSION})? y/n "
    )

    if answer.lower() == "y":
        return True
    else:
        return False


def make_pyinstaller_build():
    p = subprocess.Popen("pyinstaller tilia.spec -y")
    p.wait()


def make_installer():
    create_iss_script(tilia.constants.VERSION, tilia.constants.APP_NAME)

    path_to_inno = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

    p = subprocess.Popen(f"{path_to_inno} installer_script.iss")
    p.wait()


def create_iss_script(version: str, app_name: str) -> None:
    iss_script = f"""#define MyAppName "{app_name}"
#define MyAppVersion "{version}"
#define MyAppURL "https://www.timelineannotator.com/"
#define MyAppExeName "TLA.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".tla"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
; NOTE: The value of AppId uniquely identifies this application. Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{{{AE59AA29-2E75-4C12-8D8A-DBE3C8EBF527}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
;AppVerName={{#MyAppName}} {{#MyAppVersion}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DisableDirPage=auto
ChangesAssociations=yes
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
OutputBaseFilename={{#MyAppName}}_{{#MyAppVersion}}_setup
OutputDir=.
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{{#SourcePath}}\\dist\\{{#MyAppName}}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{{#SourcePath}}\\ffmpeg\*"; DestDir: "{{app}}\\ffmpeg"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{README_PATH}"; DestDir: "{{app}}"; Flags: ignoreversion isreadme
Source: "{LICENSE_PATH}"; DestDir: "{{app}}"; Flags: ignoreversion
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Dirs]
Name: "{{autoappdata}}\\{{#MyAppName}}\\{{#MyAppName}}\\autosaves"

[Registry]
Root: HKA; Subkey: "Software\Classes\\{{#MyAppAssocExt}}\OpenWithProgids"; ValueType: string; ValueName: "{{#MyAppAssocKey}}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\\{{#MyAppAssocKey}}"; ValueType: string; ValueName: ""; ValueData: "{{#MyAppAssocName}}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\\{{#MyAppAssocKey}}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{{app}}\\{{#MyAppExeName}},0"
Root: HKA; Subkey: "Software\Classes\\{{#MyAppAssocKey}}\\shell\open\command"; ValueType: string; ValueName: ""; ValueData: ""\"{{app}}\\{{#MyAppExeName}}\"" "\"%1\"""
Root: HKA; Subkey: "Software\Classes\Applications\\{{#MyAppExeName}}\SupportedTypes"; ValueType: string; ValueName: ".myp"; ValueData: ""

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent
"""

    with open("installer_script.iss", "w") as f:
        f.write(iss_script)


def main() -> None:
    if not confirm_version_number_update():
        return

    make_pyinstaller_build()
    make_installer()


if __name__ == "__main__":
    main()
