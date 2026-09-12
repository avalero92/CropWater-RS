@echo off
setlocal
python -m pip install --upgrade pyinstaller
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name CropWater-RS ^
  --icon assets\cropwater_rs.ico ^
  --add-data "assets;assets" ^
  --add-data "software_metadata.json;." ^
  --add-data "kc_ndvi_library.json;." ^
  cropwater_rs.py
echo.
echo Build complete. Check dist\CropWater-RS
pause
