@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo =============================================
echo  CropWater-RS 2.0.1 - Windows build
echo =============================================
where py >nul 2>nul
if errorlevel 1 (echo ERROR: Python launcher py not found. & exit /b 1)
py -3.11 --version >nul 2>nul
if errorlevel 1 (echo ERROR: Install Python 3.11 x64 and retry. & exit /b 1)
if not exist ".venv-build\Scripts\python.exe" py -3.11 -m venv .venv-build
if errorlevel 1 (echo ERROR: Build virtual environment creation failed. & exit /b 1)
call ".venv-build\Scripts\activate.bat"
if errorlevel 1 (echo ERROR: Could not activate build environment. & exit /b 1)
python -m pip install --upgrade pip
if errorlevel 1 (echo ERROR: pip upgrade failed. & exit /b 1)
python -m pip install -r requirements-qt.txt "pyinstaller>=6.10,<7" "tomli==2.5.0"
if errorlevel 1 (echo ERROR: Dependency installation failed. & exit /b 1)
set "MYPYC_FILE="
set "MYPYC_MODULE="
for /f "usebackq delims=" %%F in (`python -c "import importlib.metadata as m,pathlib; d=m.distribution('tomli'); fs=[pathlib.Path(d.locate_file(f)).resolve() for f in (d.files or []) if pathlib.Path(str(f)).name.endswith('.pyd') and '__mypyc' in pathlib.Path(str(f)).name]; print(fs[0] if len(fs)==1 else '')"`) do set "MYPYC_FILE=%%F"
if not defined MYPYC_FILE (
 echo ERROR: No unique tomli mypyc .pyd found in .venv-build.
 exit /b 1
)
if not exist "!MYPYC_FILE!" (echo ERROR: Missing !MYPYC_FILE! & exit /b 1)
for %%F in ("!MYPYC_FILE!") do set "MYPYC_FILENAME=%%~nxF"
for /f "tokens=1 delims=." %%M in ("!MYPYC_FILENAME!") do set "MYPYC_MODULE=%%M"
if not defined MYPYC_MODULE (echo ERROR: Could not derive mypyc module name. & exit /b 1)
echo Detected tomli extension: !MYPYC_FILE!
python -m PyInstaller --noconfirm --clean --onedir --windowed --name "CropWater-RS" --icon "assets\cropwater_rs.ico" --add-data "assets;assets" --add-data "src;src" --add-data "software_metadata.json;." --add-data "kc_ndvi_library.json;." --collect-all rasterio --collect-all pyproj --collect-all geopandas --collect-all sentinelhub --collect-all contextily --collect-all pyogrio --collect-all shapely --collect-all matplotlib --collect-all scipy --collect-all pandas --collect-all numpy --collect-all tomli --add-binary "!MYPYC_FILE!;." --hidden-import "!MYPYC_MODULE!" --hidden-import PySide6.QtSvg --hidden-import PySide6.QtSvgWidgets cropwater_rs_qt.py
if errorlevel 1 (echo ERROR: PyInstaller build failed. & exit /b 1)
if not exist "dist\CropWater-RS\CropWater-RS.exe" (echo ERROR: EXE not found. & exit /b 1)
set "BUNDLED_MYPYC="
if exist "dist\CropWater-RS\_internal\!MYPYC_FILENAME!" set "BUNDLED_MYPYC=dist\CropWater-RS\_internal\!MYPYC_FILENAME!"
if not defined BUNDLED_MYPYC if exist "dist\CropWater-RS\!MYPYC_FILENAME!" set "BUNDLED_MYPYC=dist\CropWater-RS\!MYPYC_FILENAME!"
if not defined BUNDLED_MYPYC (
 echo ERROR: tomli mypyc extension is NOT present in the build output.
 exit /b 1
)
echo BUILD VERIFIED - binary file present
echo Executable: dist\CropWater-RS\CropWater-RS.exe
echo Compiled module: !BUNDLED_MYPYC!
echo NOTE: Test CDSE acquisition in the EXE before building/publishing the installer.
exit /b 0
