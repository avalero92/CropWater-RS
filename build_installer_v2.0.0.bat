@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo =============================================
echo  CropWater-RS 2.0.0 - Windows Installer
 echo =============================================
if not exist "dist\CropWater-RS\CropWater-RS.exe" (
  echo ERROR: No se encuentra dist\CropWater-RS\CropWater-RS.exe
  echo Copia los archivos de este kit a la carpeta raiz del proyecto WindowsBuildKit, donde existe dist.
  pause
  exit /b 1
)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  where ISCC.exe >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Inno Setup 6 no encontrado. Instala Inno Setup desde https://jrsoftware.org/isinfo.php
    pause
    exit /b 1
  )
  set "ISCC=ISCC.exe"
)
"%ISCC%" "CropWater-RS_2.0.0.iss"
if errorlevel 1 (echo ERROR: Fallo la compilacion del instalador. & pause & exit /b 1)
if not exist "installer_output\CropWater-RS_2.0.0_Setup.exe" (echo ERROR: No se genero el instalador. & pause & exit /b 1)
echo.
echo INSTALADOR GENERADO: installer_output\CropWater-RS_2.0.0_Setup.exe
pause
exit /b 0
