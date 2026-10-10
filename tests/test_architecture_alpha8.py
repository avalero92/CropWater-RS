"""Alpha 8 offline application integration and Windows acceptance artifacts."""
from pathlib import Path
import subprocess,sys,ast
import pytest
ROOT=Path(__file__).resolve().parents[1]

def test_offline_integration_smoke():
    p=subprocess.run([sys.executable,'scripts/smoke_alpha8.py'],cwd=ROOT,capture_output=True,text=True)
    assert p.returncode==0,p.stdout+'\n'+p.stderr
    assert 'PASS: Alpha 8 offline integration' in p.stdout

def test_windows_smoke_script_exists():
    assert (ROOT/'scripts/windows_acceptance_alpha8.py').is_file()

def test_manual_acceptance_documented():
    s=(ROOT/'WINDOWS_ALPHA8_ACCEPTANCE.md').read_text(encoding='utf-8')
    for phrase in ['GUI','CDSE','GeoPackage','QUANT','CSV']:
        assert phrase in s

def test_entrypoint_ast_compiles():
    s=(ROOT/'cropwater_rs.py').read_text(encoding='utf-8')
    compile(s,'cropwater_rs.py','exec')

@pytest.mark.parametrize('p', ['src/cropwater_rs/core/water.py','src/cropwater_rs/core/temporal.py','src/cropwater_rs/core/quant.py','src/cropwater_rs/acquisition/cdse.py','src/cropwater_rs/spatial/parcels.py','src/cropwater_rs/io/exports.py','src/cropwater_rs/io/provenance.py'])
def test_critical_modules_compile(p):
    compile((ROOT/p).read_text(encoding='utf-8'),p,'exec')
