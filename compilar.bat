# Compila InventarioApp en un .exe y luego el instalador.
# Uso:  compilar.bat
#
# Requiere Python con PyInstaller (pip install -r requirements.txt).
# El instalador requiere Inno Setup 6 (https://jrsoftware.org/isinfo.php).

setlocal
cd /d "%~dp0"

echo.
echo === 1/3  Compilando el ejecutable ===
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name InventarioApp ^
    --hidden-import=tkinter ^
    inventario.py
if errorlevel 1 (
    echo ERROR: fallo PyInstaller.
    exit /b 1
)

echo.
echo === 2/3  Copiando config.example.json a config.json ===
if not exist "config.json" (
    copy /y "config.example.json" "config.json" >nul
    echo Se creo config.json. La app arranca sin nube hasta que la configures.
) else (
    echo config.json ya existe: no se toca.
)

echo.
echo === 3/3  Instalador ===
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if defined ISCC (
    echo Compilando instalador con Inno Setup...
    "%ISCC%" instalador.iss
    if errorlevel 1 (
        echo ERROR: fallo Inno Setup.
        exit /b 1
    )
    echo Instalador listo en releases\pc\
) else (
    echo Inno Setup 6 no esta instalado: se omite el instalador.
    echo El .exe quedo en dist\InventarioApp.exe y ya se puede usar.
)

echo.
echo Terminado.
endlocal