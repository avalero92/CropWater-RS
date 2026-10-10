# CropWater-RS v2.0.0 — Windows build and release guide

This kit updates version identifiers and packaging metadata of the previously tested desktop code. Scientific algorithms were not intentionally changed.

1. Extract this ZIP to a NEW folder, e.g. `C:\CropWater-RS_2.0.0`.
2. Run `build_windows_v2.0.0.bat` using Python 3.11 x64 as in the previously validated build.
3. Verify `dist\CropWater-RS\CropWater-RS.exe` opens and displays `2.0.0` in the title and status bar.
4. Run `build_installer_v2.0.0.bat` with Inno Setup 6 installed.
5. Verify `installer_output\CropWater-RS_2.0.0_Setup.exe` exists.
6. Install and smoke-test a `.cwrs` project, QUANT restoration, Water Analysis, and exports.
7. Commit the reviewed source and documentation to the EXISTING `avalero92/CropWater-RS` repository; do not overwrite historic tags `v1.0.0` and `v1.0.1`.
8. Create a new Git tag and GitHub Release `v2.0.0` from that commit, attaching the tested Windows installer.
9. Check the existing Zenodo–GitHub integration and confirm a new version record is created in the SAME software lineage. Add the resulting version DOI to README and citation metadata in a subsequent documentation commit.

Important: do not upload CDSE credentials, secrets, `.cwrs` private projects or local scientific datasets. This source ZIP is NOT a Windows installer. The version metadata does not imply the v2.0.0 DOI has already been issued.
