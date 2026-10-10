# Installation — CropWater-RS v2.0.0

## Windows distribution (recommended)

Download [CropWater-RS_2.0.0_Setup.exe](https://github.com/avalero92/CropWater-RS/releases/download/v2.0.0/CropWater-RS_2.0.0_Setup.exe) from the [official v2.0.0 release](https://github.com/avalero92/CropWater-RS/releases/tag/v2.0.0). A matching `.sha256` checksum is also provided in the release assets. Run the application through its installed shortcut and retain a copy of the installer and release identifier for reproducibility.

## Source-code execution

On Windows, install Python 3.11 (64-bit) and run from the repository root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-qt.txt
python cropwater_rs_qt.py
```

The v2.0.0 application entry point is `cropwater_rs_qt.py` (PySide6), **not** the legacy v1.x Tkinter entry point. Dependencies are defined in `requirements-qt.txt` and `requirements.txt`.

## Copernicus access

Sentinel-2 retrieval requires user-owned CDSE access credentials. Do not commit OAuth Client Secrets or embed them in shared datasets, screenshots or project archives.

## Input data

Provide parcel polygons in a supported vector format and daily meteorological CSV inputs. For scientific definitions and required units, see [Scientific methodology](../SCIENTIFIC_METHODOLOGY.md).
