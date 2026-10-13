#define AppName "CropWater-RS"
#define AppVersion "2.0.1"
#define AppExe "CropWater-RS.exe"

[Setup]
AppId={{A89C51E3-1D58-4BE2-B1B7-9658D8B0D4B1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName=CropWater-RS 2.0.1
DefaultDirName={localappdata}\Programs\CropWater-RS
DefaultGroupName=CropWater-RS
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=installer_output
OutputBaseFilename=CropWater-RS_2.0.1_Setup
SetupIconFile=installer_assets\cropwater_rs.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=installer_assets\LICENSE.txt
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\CropWater-RS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CropWater-RS"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\CropWater-RS"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir CropWater-RS"; Flags: nowait postinstall skipifsilent

