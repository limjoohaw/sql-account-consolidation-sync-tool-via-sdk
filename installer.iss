; Inno Setup script for SQL Consol Sync
; Build: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "SQL Consol Sync"
#define MyAppExeName "SQLAccConsolSync.exe"
#define MyAppVersion "1.2.1"
#define MyAppPublisher ""
#define MyAppURL ""

[Setup]
AppId={{E8F3A2C1-5B4F-4C7D-9A1E-2D3F6B8C0E5A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName=C:\eStream\Utilities\SQLAccConsolSync
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Setup_SQLAccConsolSync
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Main exe
Source: "dist\SQLAccConsolSync\SQLAccConsolSync.exe"; DestDir: "{app}"; Flags: ignoreversion
; Internal dependencies folder
Source: "dist\SQLAccConsolSync\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\icon.ico"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
