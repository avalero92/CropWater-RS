# Integration verification — v2.0.0 (pre-commit)

This package combines the v2.0.0 Final BuildKit source tree with Group A and Group B documentation. No numerical source algorithms or coefficient values were intentionally modified.

- Entry point: `cropwater_rs_qt.py` (PySide6).
- The old Tkinter `cropwater_rs.py` was intentionally excluded from the v2.0.0 publication tree; the historical v1.x releases remain accessible in Git history.
- Legacy engineering notes and previous build scripts were omitted from the public-facing package; retained scientific source modules, tests, assets, Windows v2.0.0 build scripts and examples.
- `kc_ndvi_library.json` is unchanged from the Final BuildKit. Kcb/Kc scientific limitations are documented, not automatically corrected.
- This is a source/documentation package, **not** a Windows installer.
- GitHub has **not** been changed; the v2.0.0 tag/release and version DOI remain to be confirmed.
- Tests are shipped but a full GUI/Windows runtime regression was not executed in this Linux environment.
- Existing tests from development phases may require review or adaptation to the v2.0.0 entry point.
- Verify the Windows installer against this exact source commit before release.
