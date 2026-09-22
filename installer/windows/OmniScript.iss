; OmniScript Inno Setup installer — OS integrated, type 'omni' in terminal and it reacts, runs .omni files
; Build with: iscc /DMyAppVersion=1.0.2 OmniScript.iss
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php

#define MyAppName "OmniScript"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.2"
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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "envPath"; Description: "Add to PATH (so you can type 'omni' in any terminal)"; GroupDescription: "OS integration:"; Flags: checkedonce
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "Associate .omni files with OmniScript (double-click to run)"; GroupDescription: "OS integration:"; Flags: checkedonce

[Files]
Source: "..\..\omni.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}\"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}\"; Flags: ignoreversion
Source: "..\..\VERSION"; DestDir: "{app}\"; Flags: ignoreversion
Source: "..\..\examples\*"; DestDir: "{app}\examples"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "omni-wrapper.bat"; DestDir: "{app}"; Flags: ignoreversion
; Fallback copies so 'omni' works immediately even before PATH reload — always in PATH
Source: "..\..\omni.exe"; DestDir: "{win}"; DestName: "omni.exe"; Flags: ignoreversion; Permissions: everyone-modify
Source: "..\..\omni.exe"; DestDir: "{sys}"; DestName: "omni.exe"; Flags: ignoreversion; Permissions: everyone-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} REPL (type omni)"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{userdocs}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Examples"; Filename: "{app}\examples"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Registry]
; App Paths for Windows search and Start -> Run
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\omni"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\omni"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
; File association .omni -> OmniScript
Root: HKCR; Subkey: ".omni"; ValueType: string; ValueName: ""; ValueData: "OmniScriptFile"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile"; ValueType: string; ValueName: ""; ValueData: "OmniScript File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc
Root: HKCR; Subkey: "OmniScriptFile\shell\run\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--version"; Description: "Test: run 'omni --version' (should react)"; Flags: nowait postinstall skipifsilent
Filename: "{cmd}"; Parameters: "/c echo OmniScript installed! REOPEN terminal, then type: omni --version && echo And to run files: omni examples\01_hello.omni && pause"; Description: "Show how to use omni in terminal"; Flags: nowait postinstall skipifsilent

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
  // Try SYSTEM path first (needs admin)
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
  begin
    if Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';') = 0 then
    begin
      if Paths <> '' then
        Paths := Paths + ';' + Path
      else
        Paths := Path;
      if RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
      begin
        BroadcastEnvChange();
      end;
    end;
  end;

  // Always also add to USER path to ensure it works without admin and immediately
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
  // Remove from SYSTEM
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
  begin
    P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    while P <> 0 do
    begin
      if P > 1 then
        Delete(Paths, P, Length(Path) + 1)
      else
        Delete(Paths, 1, Length(Path) + 1);
      StringChangeEx(Paths, ';;', ';', True);
      P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    end;
    RegWriteExpandStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths);
    BroadcastEnvChange();
  end;
  // Remove from USER
  if RegQueryStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Paths) then
  begin
    P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    while P <> 0 do
    begin
      if P > 1 then
        Delete(Paths, P, Length(Path) + 1)
      else
        Delete(Paths, 1, Length(Path) + 1);
      StringChangeEx(Paths, ';;', ';', True);
      P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
    end;
    RegWriteExpandStringValue(HKEY_CURRENT_USER, UserEnvironmentKey, 'Path', Paths);
    BroadcastEnvChange();
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Always add to PATH on install to ensure 'omni' works in any terminal
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
    DeleteFile(ExpandConstant('{sys}\omni.exe'));
  end;
end;
