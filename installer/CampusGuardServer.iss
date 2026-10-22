; Separate school-server installer. Model weights are intentionally not bundled.
; Compile with: ISCC.exe /DAppVersion=<build number> installer\CampusGuardServer.iss

#ifndef AppVersion
  #define AppVersion "0"
#endif

[Setup]
AppId={{8B1E6D25-8D27-4F7C-9D8C-5F0A3D4E7B61}
AppName=CampusGuard Server
AppVersion={#AppVersion}
AppVerName=CampusGuard Server {#AppVersion}
AppPublisher=CampusGuard
AppPublisherURL=https://campusguardweb.vercel.app
AppSupportURL=https://campusguardweb.vercel.app
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\CampusGuard Server
DefaultGroupName=CampusGuard Server
DisableProgramGroupPage=yes
LicenseFile=terms.txt
SetupIconFile=..\assets\campusguard.ico
UninstallDisplayIcon={app}\CampusGuard.exe
OutputDir=..\dist
OutputBaseFilename=CampusGuard-Server-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{userappdata}\CampusGuard\CampusGuard\models"; Flags: uninsneveruninstall
Name: "{userappdata}\CampusGuard\CampusGuard\footage"; Flags: uninsneveruninstall

[Files]
; Keep the existing PyInstaller runtime, but omit detector/pose/fight model files.
; Schools must provide weights they are licensed to use.
Source: "..\dist\CampusGuard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "models\*;models\*\*;_internal\models\*;_internal\models\*\*"

[Icons]
Name: "{autoprograms}\CampusGuard Server Status"; Filename: "{app}\CampusGuard.exe"; Parameters: "--server-status"; WorkingDir: "{app}"
Name: "{autoprograms}\CampusGuard Server Sign In"; Filename: "{app}\CampusGuard.exe"; Parameters: "--server-login"; WorkingDir: "{app}"
Name: "{autoprograms}\CampusGuard Show Server Token"; Filename: "{app}\CampusGuard.exe"; Parameters: "--show-token"; WorkingDir: "{app}"
Name: "{autoprograms}\Start CampusGuard Server"; Filename: "{app}\CampusGuard.exe"; Parameters: "--server"; WorkingDir: "{app}"
Name: "{autoprograms}\Install CampusGuard Start-at-Boot Task"; Filename: "{app}\CampusGuard.exe"; Parameters: "--install-task"; WorkingDir: "{app}"
Name: "{autoprograms}\Remove CampusGuard Start-at-Boot Task"; Filename: "{app}\CampusGuard.exe"; Parameters: "--remove-task"; WorkingDir: "{app}"

[Code]
var
  FootagePage: TInputDirWizardPage;
  ServerPage: TWizardPage;
  PortEdit: TNewEdit;
  MaxFootageEdit: TNewEdit;
  TaskCheck: TNewCheckBox;
  FirewallCheck: TNewCheckBox;
  StartServerCheck: TNewCheckBox;
  WarningText: TNewStaticText;
  DeleteServerData: Boolean;

function GetFootageDir(Param: String): String;
begin
  Result := Trim(FootagePage.Values[0]);
end;

function GetServerHost(Param: String): String;
begin
  if FirewallCheck.Checked then
    Result := '0.0.0.0'
  else
    Result := '127.0.0.1';
end;

function GetServerPort(Param: String): String;
begin
  Result := Trim(PortEdit.Text);
end;

function GetMaxFootageGB(Param: String): String;
begin
  Result := Trim(MaxFootageEdit.Text);
end;

procedure InitializeWizard;
var
  LabelText: TNewStaticText;
begin
  FootagePage := CreateInputDirPage(
    wpSelectDir,
    'Incident footage storage',
    'Choose where saved incident clips will be stored',
    'Choose an empty folder dedicated to CampusGuard clips. This can be a separate drive.',
    False,
    'CampusGuard footage'
  );
  FootagePage.Add('');
  FootagePage.Values[0] := ExpandConstant('{userappdata}\CampusGuard\CampusGuard\footage');

  ServerPage := CreateCustomPage(
    FootagePage.ID,
    'Server options',
    'Choose the network and storage limits for this school server'
  );

  LabelText := TNewStaticText.Create(ServerPage);
  LabelText.Parent := ServerPage.Surface;
  LabelText.Left := ScaleX(0);
  LabelText.Top := ScaleY(4);
  LabelText.Width := ServerPage.SurfaceWidth;
  LabelText.Height := ScaleY(24);
  LabelText.Caption := 'API port (default 8765):';

  PortEdit := TNewEdit.Create(ServerPage);
  PortEdit.Parent := ServerPage.Surface;
  PortEdit.Left := ScaleX(0);
  PortEdit.Top := ScaleY(28);
  PortEdit.Width := ScaleX(120);
  PortEdit.Text := '8765';

  LabelText := TNewStaticText.Create(ServerPage);
  LabelText.Parent := ServerPage.Surface;
  LabelText.Left := ScaleX(0);
  LabelText.Top := ScaleY(66);
  LabelText.Width := ServerPage.SurfaceWidth;
  LabelText.Height := ScaleY(24);
  LabelText.Caption := 'Maximum footage storage (GB; oldest clips are removed first):';

  MaxFootageEdit := TNewEdit.Create(ServerPage);
  MaxFootageEdit.Parent := ServerPage.Surface;
  MaxFootageEdit.Left := ScaleX(0);
  MaxFootageEdit.Top := ScaleY(90);
  MaxFootageEdit.Width := ScaleX(120);
  MaxFootageEdit.Text := '200';

  TaskCheck := TNewCheckBox.Create(ServerPage);
  TaskCheck.Parent := ServerPage.Surface;
  TaskCheck.Left := ScaleX(0);
  TaskCheck.Top := ScaleY(132);
  TaskCheck.Width := ServerPage.SurfaceWidth;
  TaskCheck.Height := ScaleY(24);
  TaskCheck.Caption := 'Register the server to start at Windows boot (same Windows user)';
  TaskCheck.Checked := True;

  FirewallCheck := TNewCheckBox.Create(ServerPage);
  FirewallCheck.Parent := ServerPage.Surface;
  FirewallCheck.Left := ScaleX(0);
  FirewallCheck.Top := ScaleY(164);
  FirewallCheck.Width := ServerPage.SurfaceWidth;
  FirewallCheck.Height := ScaleY(32);
  FirewallCheck.Caption := 'Allow connections from other PCs on the trusted school LAN';
  FirewallCheck.Checked := False;

  StartServerCheck := TNewCheckBox.Create(ServerPage);
  StartServerCheck.Parent := ServerPage.Surface;
  StartServerCheck.Left := ScaleX(0);
  StartServerCheck.Top := ScaleY(204);
  StartServerCheck.Width := ServerPage.SurfaceWidth;
  StartServerCheck.Height := ScaleY(24);
  StartServerCheck.Caption := 'Start the server now after sign-in';
  StartServerCheck.Checked := True;

  WarningText := TNewStaticText.Create(ServerPage);
  WarningText.Parent := ServerPage.Surface;
  WarningText.Left := ScaleX(0);
  WarningText.Top := ScaleY(238);
  WarningText.Width := ServerPage.SurfaceWidth;
  WarningText.Height := ScaleY(88);
  WarningText.WordWrap := True;
  WarningText.Caption :=
    'Security warning: enabling LAN access makes the server listen on 0.0.0.0 and asks Windows to open the selected TCP port. ' +
    'Use only a trusted school LAN or VPN. Plain HTTP does not encrypt the token; configure HTTPS or use a VPN. ' +
    'Never expose this server directly to the public internet. Cancelling the Windows firewall permission keeps the server local-only.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  PortValue: Integer;
  SizeValue: Integer;
  Folder: String;
begin
  Result := True;
  if CurPageID = ServerPage.ID then begin
    if (not TryStrToInt(Trim(PortEdit.Text), PortValue)) or (PortValue < 1) or (PortValue > 65535) then begin
      MsgBox('Enter a port between 1 and 65535.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    if (not TryStrToInt(Trim(MaxFootageEdit.Text), SizeValue)) or (SizeValue < 1) or (SizeValue > 100000) then begin
      MsgBox('Enter a footage size limit between 1 and 100000 GB.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    Folder := Trim(FootagePage.Values[0]);
    if Folder = '' then begin
      MsgBox('Choose a dedicated footage folder.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    if not ForceDirectories(Folder) then begin
      MsgBox('CampusGuard could not create the footage folder. Choose a writable folder.', mbError, MB_OK);
      Result := False;
      exit;
    end;
  end;
end;

procedure ConfigureServer(Host: String);
var
  ResultCode: Integer;
  Params: String;
begin
  Params :=
    '--configure-server --host "' + Host + '" --port "' + Trim(PortEdit.Text) +
    '" --footage-dir "' + Trim(FootagePage.Values[0]) +
    '" --max-footage-gb "' + Trim(MaxFootageEdit.Text) + '"';
  if (not Exec(ExpandConstant('{app}\CampusGuard.exe'), Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    RaiseException('CampusGuard could not save the server configuration. The installer cannot continue safely.');
end;

procedure AddFirewallRule;
var
  ScriptPath: String;
  PowerShellPath: String;
  ScriptText: String;
  ResultCode: Integer;
begin
  ScriptPath := ExpandConstant('{tmp}\CampusGuardFirewall.ps1');
  PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  ScriptText :=
    '$ErrorActionPreference = "Stop"' + #13#10 +
    '$port = ' + Trim(PortEdit.Text) + #13#10 +
    '$arguments = "advfirewall firewall add rule name=CampusGuardServer$port dir=in action=allow protocol=TCP localport=$port profile=private"' + #13#10 +
    '$p = Start-Process -FilePath "$env:SystemRoot\System32\netsh.exe" -Verb RunAs -ArgumentList $arguments -Wait -PassThru' + #13#10 +
    'exit $p.ExitCode' + #13#10;
  SaveStringToFile(ScriptPath, ScriptText, False);
  if (not Exec(PowerShellPath, '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then begin
    MsgBox('Windows Firewall permission was not granted. CampusGuard will be returned to local-only listening mode.', mbInformation, MB_OK);
    ConfigureServer('127.0.0.1');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  AppExe: String;
begin
  if CurStep <> ssPostInstall then
    exit;

  AppExe := ExpandConstant('{app}\CampusGuard.exe');
  ConfigureServer(GetServerHost(''));
  RegWriteStringValue(HKCU, 'Software\CampusGuard\Server', 'FootageDir', Trim(FootagePage.Values[0]));

  if (not Exec(AppExe, '--server-login', ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then begin
    MsgBox('Sign-in was not completed. The server is installed but will not be started. Use the CampusGuard Server Sign In shortcut after your school account is approved.', mbInformation, MB_OK);
    exit;
  end;

  if TaskCheck.Checked then begin
    if (not Exec(AppExe, '--install-task', ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      MsgBox('The start-at-boot task was not registered. You can retry from the Start Menu shortcut.', mbInformation, MB_OK);
  end;

  if FirewallCheck.Checked then
    AddFirewallRule;

  if StartServerCheck.Checked then begin
    Exec(AppExe, '--server', ExpandConstant('{app}'), SW_HIDE, ewNoWait, ResultCode);
    Sleep(1200);
    Exec(AppExe, '--show-token', ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ResultCode);
    Exec(AppExe, '--server-status', ExpandConstant('{app}'), SW_SHOW, ewNoWait, ResultCode);
  end;
end;

function InitializeUninstall: Boolean;
begin
  DeleteServerData := MsgBox(
    'Delete CampusGuard server settings, incidents, alerts, and the selected footage folder? This cannot be undone. Choose No to keep the data.',
    mbConfirmation,
    MB_YESNO or MB_DEFBUTTON2
  ) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  FootageFolder: String;
begin
  if CurUninstallStep = usUninstall then begin
    Exec(ExpandConstant('{sys}\schtasks.exe'), '/Delete /TN "CampusGuard Server" /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  if (CurUninstallStep = usPostUninstall) and DeleteServerData then begin
    DelTree(ExpandConstant('{userappdata}\CampusGuard\CampusGuard'), True, True, True);
    if RegQueryStringValue(HKCU, 'Software\CampusGuard\Server', 'FootageDir', FootageFolder) then begin
      if (FootageFolder <> '') and DirExists(FootageFolder) then
        DelTree(FootageFolder, True, True, True);
    end;
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\CampusGuard\Server');
  end;
end;
