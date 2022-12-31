from pathlib import Path


def create_iss_script(version: str, app_name: str) -> None:
    iss_script = f"""#define MyAppName "{app_name}"
#define MyAppVersion "{version}"
#define MyAppURL "https://www.timelineannotator.com/"
#define MyAppExeName "tilia.exe"
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
ChangesAssociations=yes
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
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
Source: "{{#SourcePath}}\settings.toml"; DestDir: "{{autoappdata}}\\{{#MyAppName}}\\{{#MyAppName}}"; Flags: ignoreversion
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

    with open('installer_script.iss', 'w') as f:
        f.write(iss_script)
