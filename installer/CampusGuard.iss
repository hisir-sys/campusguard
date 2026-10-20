; CampusGuard Windows installer (Inno Setup 6).
; Built by .github/workflows/windows-release.yml:
;   iscc /DAppVersion=<build number> installer\CampusGuard.iss

#ifndef AppVersion
  #define AppVersion "0"
#endif

[Setup]
AppId={{6F1C7B3E-4A52-4D8B-9E37-2B0A5C91D4F8}
AppName=CampusGuard
AppVersion={#AppVersion}
AppVerName=CampusGuard {#AppVersion}
AppPublisher=CampusGuard
AppPublisherURL=https://campusguardweb.vercel.app
AppSupportURL=https://campusguardweb.vercel.app
; Per-user install: no administrator prompt, so silent auto-updates just work.
PrivilegesRequired=lowest
DefaultDirName={autopf}\CampusGuard
DefaultGroupName=CampusGuard
DisableProgramGroupPage=yes
LicenseFile=terms.txt
SetupIconFile=..\assets\campusguard.ico
UninstallDisplayIcon={app}\CampusGuard.exe
OutputDir=..\dist
OutputBaseFilename=CampusGuard-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\CampusGuard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CampusGuard"; Filename: "{app}\CampusGuard.exe"
Name: "{autodesktop}\CampusGuard"; Filename: "{app}\CampusGuard.exe"; Tasks: desktopicon

[Run]
; Interactive install: offer to start CampusGuard on the last page.
Filename: "{app}\CampusGuard.exe"; Description: "Launch CampusGuard"; Flags: nowait postinstall skipifsilent
; Silent update (started by the app itself): reopen CampusGuard automatically.
Filename: "{app}\CampusGuard.exe"; Flags: nowait; Check: WizardSilent
