; NEXORA v2.0 — Script Inno Setup
; Prerequis : Inno Setup 6.x (https://jrsoftware.org/isinfo.php)

#define MyAppName "NEXORA"
#define MyAppVersion "2.0"
#define MyAppPublisher "Hamadou Youssouf — GTC Bertoua"
#define MyAppURL "https://github.com/piala00/vps-"
#define MyAppExeName "NEXORA.exe"

[Setup]
AppId={{NEXORA-ERP-2026-YOUSSOUF-HAMADOU}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\NEXORA
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=NEXORA_v2_Setup
SetupIconFile=..\static\img\nexora.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau"; \
      GroupDescription: "Icones supplementaires :"; Flags: unchecked
Name: "startupicon"; Description: "Demarrer NEXORA avec Windows"; \
      GroupDescription: "Options :"; Flags: unchecked

[Files]
Source: "..\dist\NEXORA.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs
Source: "..\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs
Source: "..\DEMARRER.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
      Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
      Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer NEXORA maintenant"; \
          Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Verification de version precedente
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption :=
    'Cette procedure va installer NEXORA v2.0 sur votre ordinateur.' + #13#10 +
    #13#10 +
    'Editeur : Hamadou Youssouf' + #13#10 +
    'GTC Bertoua — Cameroun' + #13#10 +
    #13#10 +
    'Il est recommande de fermer toutes les autres applications avant de continuer.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpWelcome then begin
    // Verifier si une version precedente est installee
    if RegKeyExists(HKLM, 'SOFTWARE\NEXORA') then begin
      if MsgBox('Une version precedente de NEXORA est detectee.' + #13#10 +
                'Voulez-vous la mettre a jour ?',
                mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end;
  end;
end;
