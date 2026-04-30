; La versione è iniettata dallo script di build (run.spec) che la legge
; da pyproject.toml e la passa a ISCC via /DMyAppVersion=x.y.z. Il default
; qui sotto serve solo se ISCC viene invocato a mano senza override.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
; Info applicazione
AppName=KeyLife
AppVersion={#MyAppVersion}
AppPublisher=ArcademMan
AppPublisherURL=https://github.com/ArcademMan/KeyLife
DefaultDirName={autopf}\KeyLife
DefaultGroupName=KeyLife
OutputDir=installer_output
OutputBaseFilename=KeyLife_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\keylife.exe
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
WizardStyle=modern

; Permessi (installa senza admin se possibile)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Avvia KeyLife all'accesso a Windows"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copia tutto il contenuto della cartella PyInstaller onedir (build via run.spec)
Source: "dist\keylife\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menu Start
Name: "{group}\KeyLife"; Filename: "{app}\keylife.exe"
Name: "{group}\Uninstall KeyLife"; Filename: "{uninstallexe}"
; Desktop (opzionale)
Name: "{userdesktop}\KeyLife"; Filename: "{app}\keylife.exe"; Tasks: desktopicon
; Avvio automatico (opzionale)
Name: "{userstartup}\KeyLife"; Filename: "{app}\keylife.exe"; Tasks: startupicon

[Run]
; Lancia l'app dopo l'installazione (opzionale)
Filename: "{app}\keylife.exe"; Description: "Avvia KeyLife"; Flags: nowait postinstall skipifsilent
