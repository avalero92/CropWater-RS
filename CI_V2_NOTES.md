# v2 CI migration notes

- `tests.yml` runs on Ubuntu and Windows with Python 3.12, installs `requirements-qt.txt`, and sets Qt to offscreen.
- The command explicitly selects v2-compatible scientific and Qt tests; the legacy Tkinter suite is preserved but excluded from the release gate.
- Scientific source and numerical coefficients have not been modified.
- The Qt smoke test imports the actual v2 entry point without contacting CDSE or opening a window.
- Validate the workflow on GitHub Actions after pushing the complete v2 source to the release branch; local runtime does not have PySide6.
- The explicit test list in the workflow takes precedence over `pytest-v2.ini`; the ini avoids accidental collection of legacy tests in manual `pytest -c pytest-v2.ini` runs.
