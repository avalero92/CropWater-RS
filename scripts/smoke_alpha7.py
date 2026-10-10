"""Check installation/imports without opening a window or connecting to CDSE."""
import ast
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
source = ROOT / "cropwater_rs.py"
ast.parse(source.read_text(encoding="utf-8"))
compile(source.read_text(encoding="utf-8"), str(source), "exec")
for name in ("cropwater_rs.core.water", "cropwater_rs.core.temporal",
             "cropwater_rs.core.quant", "cropwater_rs.core.meteorology",
             "cropwater_rs.core.kc_library", "cropwater_rs.acquisition.cdse",
             "cropwater_rs.spatial.parcels", "cropwater_rs.io.exports",
             "cropwater_rs.io.provenance"):
    importlib.import_module(name)
print("PASS: syntax and nine independent modules import successfully")
for name in ("tkinter", "sentinelhub"):
    try:
        importlib.import_module(name)
    except ImportError as exc:
        print(f"MISSING optional/full-app dependency: {name}: {exc}")
    else:
        print(f"AVAILABLE full-app dependency: {name}")
print("NOTE: GUI, CDSE network and Windows executable were not tested")
