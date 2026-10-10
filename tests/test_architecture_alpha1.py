"""Alpha 1: extracted production functions must match frozen v1.0.1 snapshots."""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cropwater_rs.core.water import calculate_linear_kc, calculate_etc, calculate_net_iwr
from baseline_core_snapshot import (
    calculate_linear_kc as original_kc,
    calculate_etc as original_etc,
    calculate_net_iwr as original_iwr,
)

@pytest.mark.parametrize("ndvi,a,b,clip", [
    ([-1,0,0.2,0.8,1],1.25,0.1,True),
    ([0,0.5,1],1.457,-0.1725,False),
    ([float("nan"),0.7],1.25,0.1,True),
])
def test_kc_parity(ndvi,a,b,clip):
    np.testing.assert_allclose(calculate_linear_kc(ndvi,a,b,clip),original_kc(ndvi,a,b,clip),equal_nan=True)

@pytest.mark.parametrize("kc,eto", [([0.4,0.7],[3,5]),([float("nan"),1],[4,5])])
def test_etc_parity(kc,eto):
    np.testing.assert_allclose(calculate_etc(kc,eto),original_etc(kc,eto),equal_nan=True)

@pytest.mark.parametrize("etc,pe", [([2,5],[3,1]),([float("nan"),4],[1,8])])
def test_iwr_parity(etc,pe):
    np.testing.assert_allclose(calculate_net_iwr(etc,pe),original_iwr(etc,pe),equal_nan=True)

def test_core_import_without_gui_or_cdse():
    import subprocess
    result=subprocess.run([sys.executable,"-c", "import sys; from cropwater_rs.core.water import calculate_etc; assert 'tkinter' not in sys.modules; assert 'sentinelhub' not in sys.modules"],cwd=Path(__file__).resolve().parents[1] / "src",env={"PYTHONPATH":str(Path(__file__).resolve().parents[1]/"src")},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
