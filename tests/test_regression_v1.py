"""Baseline characterization tests: no change to production algorithms."""
import json
from pathlib import Path
import numpy as np
import pytest
from baseline_core_snapshot import calculate_linear_kc, calculate_etc, calculate_net_iwr

@pytest.mark.parametrize('ndvi,a,b,clip,expected',[
    ([0.2,0.5,0.8],1.25,0.1,True,[0.35,0.725,1.1]),
    ([0,0.1,1],1.457,-0.1725,True,[0,0,1.2845]),
    ([0,0.1,1],1.457,-0.1725,False,[-0.1725,-0.0268,1.2845]),
    ([-1,0,1],1,0,True,[0,0,1]),
])
def test_kc_characterization(ndvi,a,b,clip,expected):
    np.testing.assert_allclose(calculate_linear_kc(ndvi,a,b,clip),expected,rtol=1e-12,atol=1e-12)

def test_kc_nan_propagation():
    assert np.isnan(calculate_linear_kc([np.nan],1.25,0.1)[0])

@pytest.mark.parametrize('kc,eto,expected',[
    ([0.5,1],[4,5],[2,5]),
    ([0,1.2,0.75],[5,0,4],[0,0,3]),
])
def test_etc_characterization(kc,eto,expected):
    np.testing.assert_allclose(calculate_etc(kc,eto),expected)

def test_etc_nan_propagation():
    assert np.isnan(calculate_etc([np.nan],[4])[0])

@pytest.mark.parametrize('etc,pe,expected',[
    ([2,5],[0.5,6],[1.5,0]),
    ([0,4,7],[0,0,10],[0,4,0]),
    ([1,2,3],1,[0,1,2]),
])
def test_iwr_characterization(etc,pe,expected):
    np.testing.assert_allclose(calculate_net_iwr(etc,pe),expected)

def test_iwr_nan_propagation():
    assert np.isnan(calculate_net_iwr([np.nan],[1])[0])

def test_catalogue_mirror_and_schema():
    root=Path(__file__).resolve().parents[1]
    a=json.loads((root/'kc_ndvi_library.json').read_text(encoding='utf8'))
    b=json.loads((root/'config/kc_ndvi_library.json').read_text(encoding='utf8'))
    assert a==b, 'Kc catalogue copies diverged'
