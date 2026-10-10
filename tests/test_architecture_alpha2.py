"""Alpha 2 parity, import isolation, and meteorology boundary tests."""
import ast
import io
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cropwater_rs.core.meteorology import parse_meteorology_csv
from cropwater_rs.core.kc_library import KC_CATALOG
from cropwater_rs.core.temporal import _kalman_smooth_local_level, _temporal_diagnostics


def test_kc_catalog_models():
    assert len(KC_CATALOG) == 6
    assert KC_CATALOG['kamble_2013_general']['a'] == 1.457


def test_kc_catalog_default_metadata():
    assert all(model['kc_type'] == 'Kc' for model in KC_CATALOG.values())


def test_kalman_reference_parity():
    source = (ROOT/'tests/baseline_temporal_quant_snapshot.py').read_text()
    tree = ast.parse(source)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_kalman_smooth_local_level')
    node.decorator_list = []
    namespace = {'np': np}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline>', 'exec'), namespace)
    for x in [[0.2, np.nan, 0.7, 0.5], [np.nan, np.nan], [0.4,0.4,0.4]]:
        np.testing.assert_allclose(_kalman_smooth_local_level(x), namespace['_kalman_smooth_local_level'](x), equal_nan=True)


def test_meteo_european_date(tmp_path):
    f=tmp_path/'meteo.csv'; f.write_text('Date;ETo;Pe\n03/04/2023;3.2;0.4\n04/04/2023;4.1;0\n')
    df, high_eto, high_pe = parse_meteorology_csv(f)
    assert df.Date.iloc[0] == pd.Timestamp('2023-04-03')
    assert (high_eto,high_pe)==(0,0)


def test_meteo_parcel_specific(tmp_path):
    f=tmp_path/'meteo.csv'; f.write_text('Date,ETo,parcel_id\n2023-04-03,3,A\n2023-04-03,4,B\n')
    df,_,_=parse_meteorology_csv(f)
    assert len(df)==2

@pytest.mark.parametrize('content', [
    'Date,ETo\n2023-04-03,-1\n',
    'Date,ETo\n2023-04-03,abc\n',
    'Date,ETo\n2023-04-03,2\n2023-04-03,3\n',
    'Date,ETo\n04/31/2023,3\n',
    'Date,Pe\n2023-04-03,2\n',
])
def test_meteo_rejects_invalid(tmp_path,content):
    f=tmp_path/'meteo.csv'; f.write_text(content)
    with pytest.raises(ValueError): parse_meteorology_csv(f)


def test_meteo_high_value_warnings(tmp_path):
    f=tmp_path/'meteo.csv'; f.write_text('Date,ETo,Pe\n2023-04-03,16,201\n')
    _,e,p=parse_meteorology_csv(f)
    assert (e,p)==(1,1)


def test_modules_no_tkinter_import():
    import subprocess
    result=subprocess.run([sys.executable,'-c', 'import cropwater_rs.core.meteorology, cropwater_rs.core.kc_library, cropwater_rs.core.temporal; import sys; assert "tkinter" not in sys.modules and "sentinelhub" not in sys.modules'],cwd=ROOT/'src',capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_compatibility_bridge_present():
    code=(ROOT/'cropwater_rs.py').read_text()
    assert 'parse_meteorology_csv(path)' in code
    assert '_kalman_smooth_local_level = staticmethod(kalman_smooth_local_level_core)' in code
    assert '_temporal_diagnostics = staticmethod(temporal_diagnostics_core)' in code
