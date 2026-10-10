"""Offline smoke test for the actual v2 PySide6 entry point."""
import importlib
import os
from pathlib import Path


def test_qt_entry_point_and_dependencies():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    assert (Path(__file__).resolve().parents[1] / "cropwater_rs_qt.py").is_file()
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication.instance() or QApplication([])
    module = importlib.import_module("cropwater_rs_qt")
    assert issubclass(module.QMainWindow, QMainWindow)
    assert module.ROOT.is_dir()
    assert app is not None


def test_qt_components_import_offline():
    for name in ("qt_quant_page", "qt_water_page", "qt_preprocessing_page", "qt_spatial_view", "qt_cdse_raster"):
        importlib.import_module(name)
