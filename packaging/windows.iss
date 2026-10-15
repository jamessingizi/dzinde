; Inno Setup script for the Windows installer. Built by CI after PyInstaller:
;   iscc /DVersion=1.0.0 packaging\windows.iss   ->  dist\Dzinde-1.0.0-setup.exe
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{8D3C5B1E-4C3A-4E8B-9C55-2B7D6F0A9E41}
AppName=Dzinde
AppVersion={#Version}
AppPublisher=Dzinde
DefaultDirName={autopf}\Dzinde
DefaultGroupName=Dzinde
UninstallDisplayIcon={app}\Dzinde.exe
OutputDir=..\dist
OutputBaseFilename=Dzinde-{#Version}-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
WizardStyle=modern

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Dzinde\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Dzinde"; Filename: "{app}\Dzinde.exe"
Name: "{autodesktop}\Dzinde"; Filename: "{app}\Dzinde.exe"; Tasks: desktopicon

[Registry]
; Offer Dzinde under "Open with" for .rmtree without taking the default away from RootsMagic.
Root: HKA; Subkey: "Software\Classes\.rmtree\OpenWithProgids"; ValueType: string; ValueName: "Dzinde.rmtree"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Dzinde.rmtree"; ValueType: string; ValueName: ""; ValueData: "RootsMagic Database"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Dzinde.rmtree\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Dzinde.exe,0"
Root: HKA; Subkey: "Software\Classes\Dzinde.rmtree\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Dzinde.exe"" ""%1"""

[Run]
Filename: "{app}\Dzinde.exe"; Description: "Launch Dzinde"; Flags: nowait postinstall skipifsilent
