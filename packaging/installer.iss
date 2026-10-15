; JARVIS Orbit — Inno Setup installer (G13 packaging, delivery layer only).
;
; Prerequisites (Windows, build machine):
;   1. python -m PyInstaller --noconfirm --clean packaging/orbit_bridge.spec
;   2. An unbranded Chromium build placed under dist\chromium\ (or install
;      path passed via /DCHROMIUM=...) — never the user's Chrome profile.
;   3. Compile: ISCC.exe packaging\installer.iss
;
; The extension is NOT packaged as an .crx: unbranded Chromium 137+ dropped
; --load-extension, so the installer places the unpacked extension on disk
; and the first-run shortcut opens chrome://extensions for the one-time
; "Load unpacked" step (mirrors scripts/jbrowser-launcher.ps1).

#define MyAppName "JARVIS Orbit"
#define MyAppVersion "0.13.0"
#define MyAppPublisher "JARVIS"
#define MyAppExeName "JARVISOrbitBridge.exe"

[Setup]
AppId={{8F1B2C4A-5D7E-4A3B-9C21-2D6E0A1B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\JARVIS Orbit
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=JARVISOrbit-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
SetupLogging=yes
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Bridge daemon (PyInstaller build output).
Source: "..\dist\JARVISOrbitBridge\*"; DestDir: "{app}\bridge"; Flags: recursesubdirs ignoreversion
; MV3 extension (loaded once via chrome://extensions -> Load unpacked).
Source: "..\extensions\jbrowser\*"; DestDir: "{app}\extension\jbrowser"; Flags: recursesubdirs ignoreversion
; Optional bundled Chromium runtime (unbranded) if prepared.
Source: "..\dist\chromium\*"; DestDir: "{app}\chromium"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\bridge\{#MyAppExeName}"
Name: "{group}\Load JARVIS extension"; Filename: "{app}\extension\jbrowser\manifest.json"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\bridge\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\bridge\{#MyAppExeName}"; Description: "Start the JARVIS bridge"; Flags: nowait postinstall skipifsilent
Filename: "{app}\extension\jbrowser\manifest.json"; Description: "Open the extension for one-time load"; Flags: nowait postinstall skipifsilent
