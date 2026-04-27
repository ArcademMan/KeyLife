[Setup]
; Info applicazione
AppName=KeyLife
AppVersion=0.1.0
AppPublisher=ArcademMan
AppPublisherURL=https://github.com/ArcademMan/KeyLife
DefaultDirName={autopf}\KeyLife
DefaultGroupName=KeyLife
OutputDir=installer_output
OutputBaseFilename=KeyLife_Setup_0.1.0
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
