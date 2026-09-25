; OmniScript Inno Setup installer — works like the Python installer (python.org)
; Build with: iscc /DMyAppVersion=1.0.4 OmniScript.iss
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php
;
; Research — how the Python installer makes `python` work in the terminal after install:
;   1. Default is PER-USER install, NO admin required:
;      installs to %LOCALAPPDATA%\Programs\Python\PythonXY
;   2. "Install for all users" (optional, admin): C:\Program Files\PythonXY
;   3. Adds install dir to PATH — USER PATH always, MACHINE PATH only when all-users
;   4. Registers App Paths (HKCU) so Start-menu search / Win+R find python
;   5. Per-user file association (.py) via HKCU — no admin needed
;   6. After install, open a NEW terminal -> `python` works in CMD, PowerShell,
;      Windows Terminal, Git Bash.
;
; OmniScript does exactly the same:
;   - per-user default: %LOCALAPPDATA%\Programs\OmniScript (no admin, never fails)
;   - always adds {app} to USER PATH (machine PATH only if all-users/admin)
;   - copies omni.exe to %LOCALAPPDATA%\Microsoft\WindowsApps (always in user PATH)
;   - App Paths in HKCU, per-user .omni file association (no admin)
;   - after install, NEW terminal -> `omni` works in every terminal
;   - if all-users (admin): ALSO machine PATH + C:\Windows\omni.exe fallback

#define MyAppName "OmniScript"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.4"
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
; Like Python: per-user default, no admin required (python.org "Install Now")
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\\..\\LICENSE
OutputDir=..\\..\\dist
OutputBaseFilename=OmniScript-{#MyAppVersion}-Windows-x86_64-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
; Like Python: no admin by default, user can choose "all users" if they want
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\\{#MyAppExeName}
InfoAfterFile=..\\..\\README.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "Associate .omni files (double-click to run)"; GroupDescription: "OS integration:"; Flags: checkedonce

[Files]
Source: "..\\..\\omni.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\\..\\README.md"; DestDir: "{app}\\\"; Flags: ignoreversion
Source: "..\\..\\LICENSE"; DestDir: "{app}\\\"; Flags: ignoreversion
Source: "..\\..\\VERSION"; DestDir: "{app}\\\"; Flags: ignoreversion
Source: "..\\..\\examples\\*"; DestDir: "{app}\\examples"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "omni-wrapper.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "fix-path.ps1"; DestDir: "{app}"; Flags: ignoreversion
; Like Python adds its launcher dir to PATH: put real omni.exe in the user dir
; that is ALWAYS in the user PATH on Windows 10/11 — no admin required, never fails
Source: "..\\..\\omni.exe"; DestDir: "{localappdata}\\Microsoft\\WindowsApps"; DestName: "omni.exe"; Flags: ignoreversion

[Icons]
Name: "{group}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\\{#MyAppExeName}"
Name: "{group}\\{#MyAppName} REPL (type omni)"; Filename: "{app}\\{#MyAppExeName}"; WorkingDir: "{userdocs}"; IconFilename: "{app}\\{#MyAppExeName}"
Name: "{group}\\Examples"; Filename: "{app}\\examples"
Name: "{group}\\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Registry]
; App Paths in HKCU (like Python registers App Paths) — no admin needed.
; Makes "omni" work from Start-menu search and Win+Run.
Root: HKCU; Subkey: "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{#MyAppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\omni"; ValueType: string; ValueName: ""; ValueData: "{app}\\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\omni"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
; File association .omni -> OmniScript, PER-USER in HKCU (like Python's .py association, no admin)
Root: HKCU; Subkey: "Software\\Classes\\.omni"; ValueType: string; ValueName: ""; ValueData: "OmniScriptFile"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKCU; Subkey: "Software\\Classes\\OmniScriptFile"; ValueType: string; ValueName: ""; ValueData: "OmniScript File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\\Classes\\OmniScriptFile\\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\\{#MyAppExeName},0"; Tasks: fileassoc
Root: HKCU; Subkey: "Software\\Classes\\OmniScriptFile\\shell\\open\\command"; ValueType: string; ValueName: ""; ValueData: "\"{app}\\{#MyAppExeName}\" \"%1\""; Tasks: fileassoc
Root: HKCU; Subkey: "Software\\Classes\\OmniScriptFile\\shell\\run\\command"; ValueType: string; ValueName: ""; ValueData: "\"{app}\\{#MyAppExeName}\" \"%1\""; Tasks: fileassoc

[Run]
; Test that omni reacts right after install (like Python's test run)
Filename: "{app}\\{#MyAppExeName}"; Parameters: "--version"; Description: "Test: omni --version should react"; Flags: nowait postinstall skipifsilent
; Like Python installer's "close window" message: tell user to open a NEW terminal
Filename: "{cmd}"; Parameters: "/c echo OmniScript installed (like Python). OPEN A NEW TERMINAL, then type: omni --version && echo To run a file: omni examples\01_hello.omni && echo Double-click any .omni file to run it. && pause"; Description: "Show how to use omni"; Flags: nowait postinstall skipifsilent

[Code]
const
  MachineEnvironmentKey = 'SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment';
  UserEnvironmentKey = 'Environment';
  WM_SETTINGCHANGE = $001A;
  SMTO_ABORTIFHUNG = 2;
  HWND_BROADCAST = $FFFF;

function SendMessageTimeout(hWnd: LongInt; Msg: LongInt; wParam: LongInt; lParam: String; fuFlags: LongInt; uTimeout: LongInt; var lpdwResult: LongInt): LongInt;
  external 'SendMessageTimeoutA@user32.dll stdcall';

procedure BroadcastEnvChange;
var
  Res: LongInt;
begin
  SendMessageTimeout(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', SMTO_ABORTIFHUNG, 5000, Res);
end;

function PathHasEntry(Paths, Entry: string): Boolean;
begin
  Result := Pos(';' + Uppercase(Entry) + ';', ';' + Uppercase(Paths) + ';') <> 0;
end;

procedure AppendPath(Root: HKEY; Key, Path: string);
var
  Paths: string;
begin
  if RegQueryStringValue(Root, Key, 'Path', Paths) then
  begin
    if not PathHasEntry(Paths, Path) then
    begin
      if Paths <> '' then
        Paths := Paths + ';' + Path
      else
        Paths := Path;
      RegWriteExpandStringValue(Root, Key, 'Path', Paths);
    end;
  end
  else
  begin
    RegWriteExpandStringValue(Root, Key, 'Path', Path);
  end;
  BroadcastEnvChange;
end;

function RemovePathEntry(Paths, Entry: string): string;
var
  P: Integer;
begin
  Result := Paths;
  P := Pos(';' + Uppercase(Entry) + ';', ';' + Uppercase(Result) + ';');
  while P <> 0 do
  begin
    if P > 1 then
      Delete(Result, P, Length(Entry) + 1)
    else
      Delete(Result, 1, Length(Entry) + 1);
    StringChangeEx(Result, ';;', ';', True);
    P := Pos(';' + Uppercase(Entry) + ';', ';' + Uppercase(Result) + ';');
  end;
end;

procedure UnsetPath(Root: HKEY; Key, Path: string);
var
  Paths: string;
begin
  if RegQueryStringValue(Root, Key, 'Path', Paths) then
  begin
    Paths := RemovePathEntry(Paths, Path);
    RegWriteExpandStringValue(Root, Key, 'Path', Paths);
    BroadcastEnvChange;
  end;
end;

// Like Python: per-user install has no admin — only write machine PATH when all-users
procedure InstallPost(Path: string);
begin
  // USER PATH — always (Python always adds to user PATH for per-user installs)
  AppendPath(HKEY_CURRENT_USER, UserEnvironmentKey, Path);

  if IsAdminRequested then
  begin
    // MACHINE PATH — only for "install for all users" (Python adds machine PATH there)
    AppendPath(HKEY_LOCAL_MACHINE, MachineEnvironmentKey, Path);
    // Extra safety net for all-users: fallback copy like git's C:\Windows copy
    TryCopyFile(ExpandConstant('{app}\omni.exe'), ExpandConstant('{win}\omni.exe'));
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  // Like Python: "install for all users" goes to C:\Program Files, per-user to LOCALAPPDATA
  if IsAdminRequested then
  begin
    if (Wizard.DirValue = '') or
       (Pos('localappdata', LowerCase(ExpandConstant(Wizard.DirValue))) > 0) then
    begin
      Wizard.DirValue := ExpandConstant('{pf}\{#MyAppName}');
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallPost(ExpandConstant('{app}'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    UnsetPath(HKEY_CURRENT_USER, UserEnvironmentKey, ExpandConstant('{app}'));
    if IsAdminRequested then
      UnsetPath(HKEY_LOCAL_MACHINE, MachineEnvironmentKey, ExpandConstant('{app}'));
    DeleteFile(ExpandConstant('{localappdata}\Microsoft\WindowsApps\omni.exe'));
    DeleteFile(ExpandConstant('{win}\omni.exe'));
    DeleteFile(ExpandConstant('{sys}\omni.exe'));
    DeleteFile(ExpandConstant('{win}\omni.bat'));
    DeleteFile(ExpandConstant('{sys}\omni.bat'));
  end;
end;
