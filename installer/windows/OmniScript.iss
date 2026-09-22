; OmniScript Inno Setup installer — works like git CLI, type 'omni' in any terminal and it reacts
; Build with: iscc /DMyAppVersion=1.0.3 OmniScript.iss
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php
; Research: git CLI works because it adds to PATH + fallback in C:\Windows + App Paths + broadcast

#define MyAppName "OmniScript"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.3"
#endif
#define MyAppPublisher "OmniNodeCo"
#define MyAppURL "https://github.com/OmniNodeCo/OmniScript"
#define MyAppExeName "omni.exe"

[Setup]
AppId={{8F0A2E0D-4B0A-4F0A-8F0A-2E0D4B0A8F0A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=OmniScript-{#MyAppVersion}-Windows-x86_64-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ChangesEnvironment=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
InfoAfterFile=..\..\README.md
; Like git, require admin to ensure PATH and Windows dir copy works
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "envPath"; Description: "Add to PATH (so you can type 'omni' in any terminal like git)"; GroupDescription: "OS integration:"; Flags: checkedonce
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "Associate .omni files (double-click to run)"; GroupDescription: "OS integration:"; Flags: checkedonce

[Files]
Source: "..\..\omni.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}\"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}\"; Flags: ignoreversion
Source: "..\..\VERSION"; DestDir: "{app}\"; Flags: ignoreversion
Source: "..\..\examples\*"; DestDir: "{app}\examples"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "omni-wrapper.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "fix-path.ps1"; DestDir: "{app}"; Flags: ignoreversion
; Git-like: copy to locations always in PATH so 'omni' works immediately even before PATH reload
Source: "..\..\omni.exe"; DestDir: "{win}"; DestName: "omni.exe"; Flags: ignoreversion; Permissions: everyone-modify
Source: "..\..\omni.exe"; DestDir: "{sys}"; DestName: "omni.exe"; Flags: ignoreversion; Permissions: everyone-modify
; Also create omni.bat wrappers in Windows dirs (like git does with cmd\git.exe)
Source: "omni-wrapper.bat"; DestDir: "{win}"; DestName: "omni.bat"; Flags: ignoreversion; Permissions: everyone-modify
Source: "omni-wrapper.bat"; DestDir: "{sys}"; DestName: "omni.bat"; Flags: ignoreversion; Permissions: everyone-modify
; Copy to WindowsApps user dir which is always in user PATH (like python, etc)
Source: "..\..\omni.exe"; DestDir: "{localappdata}\Microsoft\WindowsApps"; DestName: "omni.exe"; Flags: ignoreversion; Permissions: everyone-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} REPL (type omni)"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{userdocs}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Examples"; Filename: "{app}\examples"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Registry]
; App Paths for Start -> Run, Windows search, like git
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\omni"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\omni"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\omni.exe"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
; File association .omni -> OmniScript (double-click runs file)
Root: HKCR; Subkey: ".omni"; ValueType: string; ValueName: ""; ValueData: "OmniScriptFile"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile"; ValueType: string; ValueName: ""; ValueData: "OmniScript File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile\shell\run\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc

[Run]
; Test that omni reacts after install
Filename: "{app}\{#MyAppExeName}"; Parameters: "--version"; Description: "Test: omni --version should react"; Flags: nowait postinstall skipifsilent
; Like git, show message to reopen terminal
Filename: "{cmd}"; Parameters: "/c echo OmniScript installed like git! REOPEN terminal, then type: omni --version && echo To run files: omni examples\01_hello.omni && pause"; Description: "Show how to use omni like git"; Flags: nowait postinstall skipifsilent
; Ensure PATH via setx as extra safety (like git does)
Filename: "{cmd}"; Parameters: "/c setx PATH ""%PATH%;{app}"" /M"; Flags: runhidden; Tasks: envPath
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""$p=[Environment]::GetEnvironmentVariable('Path','Machine'); if($p -notlike '*{app}*'){ [Environment]::SetEnvironmentVariable('Path', $p+';{app}', 'Machine') }"""; Flags: runhidden; Tasks: envPath

[Code]
const
    EnvironmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
    UserEnvironmentKey = 'Environment';
    WM_SETTINGCHANGE = $001A;
    SMTO_ABORTIFHUNG = 2;
    HWND_BROADCAST = $FFFF;

function SendMessageTimeout(hWnd: LongInt; Msg: LongInt; wParam: LongInt; lParam: String; fuFlags: LongInt; uTimeout: LongInt; var lpdwResult: LongInt): LongInt;
  external 'SendMessageTimeoutA@user32.dll stdcall';

procedure BroadcastEnvChange();
var
  Res: LongInt;
begin
  SendMessageTimeout(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', SMTO_ABORTIFHUNG, 5000, Res);
end;

procedure EnvAddPath(Path: string);
var
  Paths: string;
begin
  // SYSTEM path (admin) — like git
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
  begin
    if Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';') = 0 then
    begin
      if Paths <> '' then
        Paths := Paths + ';' + Path
      else
        Paths := Path;
      RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths);
      BroadcastEnvChange();
    end;
  end else
  begin
    RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Path);
    BroadcastEnvChange();
  end;

  // USER path — always, for non-admin and immediate use like git
  if RegQueryStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Paths) then
  begin
    if Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';') = 0 then
    begin
      if Paths <> '' then
        Paths := Paths + ';' + Path
      else
        Paths := Path;
      RegWriteExpandStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Paths);
      BroadcastEnvChange();
    end;
  end else
  begin
    RegWriteExpandStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Path);
    BroadcastEnvChange();
  end;
end;

procedure EnvRemovePath(Path: string);
var
  Paths: string;
  P: Integer;
begin
  // SYSTEM
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
  begin
    P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    while P <> 0 do
    begin
      if P > 1 then Delete(Paths, P, Length(Path) + 1) else Delete(Paths, 1, Length(Path) + 1);
      StringChangeEx(Paths, ';;', ';', True);
      P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    end;
    RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths);
    BroadcastEnvChange();
  end;
  // USER
  if RegQueryStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Paths) then
  begin
    P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    while P <> 0 do
    begin
      if P > 1 then Delete(Paths, P, Length(Path) + 1) else Delete(Paths, 1, Length(Path) + 1);
      StringChangeEx(Paths, ';;', ';', True);
      P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    end;
    RegWriteExpandStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Paths);
    BroadcastEnvChange();
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Always add to PATH like git does, regardless of task
  if CurStep = ssPostInstall then
  begin
    EnvAddPath(ExpandConstant('{app}'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    EnvRemovePath(ExpandConstant('{app}'));
    DeleteFile(ExpandConstant('{win}\omni.exe'));
    DeleteFile(ExpandConstant('{win}\omni.bat'));
    DeleteFile(ExpandConstant('{sys}\omni.exe'));
    DeleteFile(ExpandConstant('{sys}\omni.bat'));
    DeleteFile(ExpandConstant('{localappdata}\Microsoft\WindowsApps\omni.exe'));
  end;
end;
