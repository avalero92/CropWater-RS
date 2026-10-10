@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo =============================================
echo  CropWater-RS 2.0.0 - Windows build
 echo =============================================
where py >nul 2>nul
if errorlevel 1 (echo ERROR: Python launcher py not found. & pause & exit /b 1)
py -3.11 --version >nul 2>nul
if errorlevel 1 (echo ERROR: Install Python 3.11 x64 and retry. & pause & exit /b 1)
if not exist ".venv-build\Scripts\python.exe" py -3.11 -m venv .venv-build
if errorlevel 1 (echo ERROR: venv creation failed. & pause & exit /b 1)
call ".venv-build\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 (pause & exit /b 1)
python -m pip install -r requirements-qt.txt "pyinstaller>=6.10,<7"
if errorlevel 1 (echo ERROR: Dependency installation failed. & pause & exit /b 1)
python -m PyInstaller --noconfirm --clean --onedir --windowed --name "CropWater-RS" --icon "assets\cropwater_rs.ico" --add-data "assets;assets" --add-data "src;src" --add-data "software_metadata.json;." --add-data "kc_ndvi_library.json;." --collect-all rasterio --collect-all pyproj --collect-all geopandas --collect-all sentinelhub --collect-all contextily --collect-all pyogrio --collect-all shapely --collect-all matplotlib --collect-all scipy --collect-all pandas --collect-all numpy --hidden-import PySide6.QtSvg --hidden-import PySide6.QtSvgWidgets cropwater_rs_qt.py
if errorlevel 1 (echo ERROR: PyInstaller build failed. & pause & exit /b 1)
if not exist "dist\CropWater-RS\CropWater-RS.exe" (echo ERROR: EXE not found. & pause & exit /b 1)
echo.
echo BUILD COMPLETE: dist\CropWater-RS\CropWater-RS.exe
echo Keep the whole dist\CropWater-RS folder when moving the app.
pause
exit /b 0
