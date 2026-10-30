; =============================================================================
;  installateur.iss : installateur Windows du programme « Filtres de Butterworth »
;
;  Il crée dist\Installer_FiltresButterworth_2.1.exe (numéro de la version ci-dessous),
;  à distribuer aux utilisateurs.
;  À compiler avec Inno Setup 7 ou 6 (https://jrsoftware.org/isdl.php), APRÈS PyInstaller :
;  construire_windows.bat fait les deux étapes.
;
;  L'installation ne demande pas de droits administrateur : le programme va dans le
;  profil de l'utilisateur, avec un raccourci dans le menu Démarrer et (au choix) sur
;  le bureau. Les fichiers .filtre (filtres enregistrés) s'ouvrent d'un double-clic.
;  Il se désinstalle depuis Paramètres > Applications.
;
;  Le numéro de version est aussi dans commun.py (VERSION) : changer les deux.
; =============================================================================

#define Nom "Filtres de Butterworth"
#define Version "2.1"
#define Exe "FiltresButterworth.exe"

[Setup]
; Identifiant unique du programme : ne pas le changer d'une version à l'autre
AppId={{5D518B3E-1B4D-4A41-97D4-117D24520745}
AppName={#Nom}
AppVersion={#Version}
AppVerName={#Nom} {#Version}
AppPublisher=Axel Sanou
AppPublisherURL=https://github.com/nouxel00/filtres-butterworth
AppSupportURL=https://github.com/nouxel00/filtres-butterworth
AppUpdatesURL=https://github.com/nouxel00/filtres-butterworth/releases
; Propriétés du fichier de l'installateur (onglet Détails de l'Explorateur)
VersionInfoVersion={#Version}
VersionInfoProductName={#Nom}
VersionInfoProductVersion={#Version}
VersionInfoCompany=Axel Sanou
VersionInfoCopyright=© 2026 Axel Sanou – licence MIT
VersionInfoDescription=Installateur de {#Nom}
DefaultDirName={autopf}\{#Nom}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Installer_FiltresButterworth_{#Version}
SetupIconFile=..\icone.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nom}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Association des fichiers .filtre au programme (double-clic dans l'Explorateur)
ChangesAssociations=yes
; Mise à jour lancée par le programme : c'est l'entrée MiseAJour de [Run] qui le rouvre (pas de
; deuxième lancement par le gestionnaire de redémarrage de Windows)
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Tout le dossier construit par PyInstaller
Source: "..\dist\FiltresButterworth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; HKA : profil de l'utilisateur (installation sans droits administrateur), sinon tout l'ordinateur
Root: HKA; Subkey: "Software\Classes\.filtre"; ValueType: string; ValueName: ""; ValueData: "FiltresButterworth.Filtre"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\FiltresButterworth.Filtre"; ValueType: string; ValueName: ""; ValueData: "Filtre de Butterworth"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\FiltresButterworth.Filtre\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#Exe},0"
Root: HKA; Subkey: "Software\Classes\FiltresButterworth.Filtre\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#Exe}"" ""%1"""

[Icons]
Name: "{autoprograms}\{#Nom}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Nom}"; Filename: "{app}\{#Exe}"; Tasks: bureau

[Run]
; Préparation du premier lancement (liste des polices de matplotlib, longue à construire la
; première fois) : faite pendant l'installation, le programme démarre ensuite plus vite.
; La liste est gardée dans %LOCALAPPDATA%\FiltresButterworth\matplotlib (voir main.py).
Filename: "{app}\{#Exe}"; Parameters: "--preparer"; StatusMsg: "Préparation du premier lancement..."; Flags: waituntilterminated
; Mise à jour lancée par le programme (/SILENT ... /MISEAJOUR=1, voir mise_a_jour.py) : une fois
; la nouvelle version en place, le programme est rouvert, au nom de l'utilisateur.
Filename: "{app}\{#Exe}"; Flags: nowait runasoriginaluser; Check: MiseAJour
Filename: "{app}\{#Exe}"; Description: "{cm:LaunchProgram,{#Nom}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; La liste des polices préparée pour matplotlib (les préférences et la dernière séance, dans
; %APPDATA%\FiltresButterworth, restent : une réinstallation les retrouve)
Type: filesandordirs; Name: "{localappdata}\FiltresButterworth\matplotlib"
Type: dirifempty; Name: "{localappdata}\FiltresButterworth"

[Code]
// Vrai quand l'installateur est lancé par le programme pour une mise à jour (/MISEAJOUR=1)
function MiseAJour: Boolean;
begin
  Result := ExpandConstant('{param:MISEAJOUR|0}') = '1';
end;
