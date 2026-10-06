; Instalador de InventarioApp.
; Compilar con:  compilar.bat   (o  "C:\Program Files\Inno Setup 6\ISCC.exe" instalador.iss)
;
; Los datos del usuario (inventario.json y los respaldos) se guardan junto al
; .exe en la carpeta donde el usuario lo abre, y NO se borran al desinstalar:
; se conservan por si hay que reinstalar.

#define AppNombre "InventarioApp"
#define AppVersion "1.0.0"
#define AppPublisher "SeeingLag"
#define AppExe "InventarioApp.exe"

[Setup]
AppId={{8F3B1C2A-4D5E-4A6B-9C7D-1E2F3A4B5C6D}
AppName={#AppNombre}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppNombre}
DefaultGroupName={#AppNombre}
DisableProgramGroupPage=yes
OutputDir=releases\pc
OutputBaseFilename={#AppNombre}-{#AppVersion}-instalador
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#AppExe}
; Los datos del usuario quedan fuera de la carpeta de instalacion.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
Name: "inicio"; Description: "Iniciar InventarioApp al iniciar Windows"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
; Plantilla de configuracion: la app funciona sin ella (solo local).
Source: "config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#AppNombre}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppNombre}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppNombre}"; Filename: "{app}\{#AppExe}"; Tasks: escritorio

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppNombre}"; Flags: nowait postinstall skipifsilent