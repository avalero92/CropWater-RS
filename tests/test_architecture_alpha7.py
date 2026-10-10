"""Alpha 7: packaging, import order, startup contracts, and smoke checks."""
import ast
import subprocess
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'cropwater_rs.py').read_text(encoding='utf-8')
TREE=ast.parse(SOURCE)

def test_legacy_script_compiles():
    compile(SOURCE,'cropwater_rs.py','exec')

def test_bootstrap_precedes_modular_imports():
    assert SOURCE.index('_sys.path.insert(0, _src_dir)') < SOURCE.index('from cropwater_rs.acquisition.cdse')

def test_no_src_package_imports_in_launcher():
    assert 'from src.cropwater_rs.' not in SOURCE

def test_launcher_has_main_guard():
    assert any(isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__' for n in TREE.body)

def test_gui_constructor_preserved():
    assert any(isinstance(n,ast.ClassDef) and n.name=='CropWaterRSApp' for n in TREE.body)

@pytest.mark.parametrize('module',[
'cropwater_rs.core.water','cropwater_rs.core.temporal','cropwater_rs.core.quant',
'cropwater_rs.core.meteorology','cropwater_rs.core.kc_library',
'cropwater_rs.acquisition.cdse','cropwater_rs.spatial.parcels',
'cropwater_rs.io.exports','cropwater_rs.io.provenance'])
def test_package_module_import_from_repo_root(module):
    code=f'import sys; sys.path.insert(0, "src"); import {module}; assert "sentinelhub" not in sys.modules and "tkinter" not in sys.modules'
    r=subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True)
    assert r.returncode==0,r.stderr

def test_smoke_script():
    r=subprocess.run([sys.executable,'scripts/smoke_alpha7.py'],cwd=ROOT,text=True,capture_output=True)
    assert r.returncode==0,r.stderr
    assert 'PASS: syntax and nine independent modules' in r.stdout
