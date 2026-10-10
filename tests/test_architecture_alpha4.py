"""Differential QUANT tests against frozen v1.0.1 behavior."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cropwater_rs.core.quant import calculate_quant_one, validate_quant_thresholds, quant_crossing_date
from test_regression_v2 import engine,quant_daily

@pytest.mark.parametrize('thresholds',[(10,90,90,50),(5,80,85,40),(20,95,95,60),(1,99,99,1)])
def test_thresholds_match_baseline(thresholds):
    from test_regression_v2 import DummyVar
    x=engine()
    for i,v in enumerate(thresholds,1):setattr(x,f'quant_q{i}_var',DummyVar(v))
    assert validate_quant_thresholds(*thresholds)==x._validate_quant_thresholds()

@pytest.mark.parametrize('thresholds',[(0,90,90,50),(90,10,90,50),(10,90,50,90),(10,100,90,50)])
def test_invalid_thresholds(thresholds):
    with pytest.raises(ValueError):validate_quant_thresholds(*thresholds)

@pytest.mark.parametrize('direction,values,threshold',[('rising',[0,.5,1],.25),('falling',[1,.5,0],.25),('rising',[.2,.3,.4],.9),('falling',[.9,.6,.4,.7,.3],.5)])
def test_crossings_match_baseline(direction,values,threshold):
    from baseline_temporal_quant_snapshot import BaselineMethods
    d=pd.date_range('2024-01-01',periods=len(values))
    a=BaselineMethods._quant_crossing_date(d,values,threshold,direction)
    b=quant_crossing_date(d,values,threshold,direction)
    assert (pd.isna(a) and pd.isna(b)) or a==b

@pytest.mark.parametrize('values',[
    [.2,.3,.4,.5,.6,.7,.8,.9,1.,.9,.8,.7,.6,.5,.4,.3,.2],
    [.2,.21,.22,.23,.24,.23,.22],
    [.9,.8,.7,.6,.5,.4,.3],
    [.2,.5,.4,.2],
    [.1,.2,.3,.4,.5,.6,.7,.8,.7,.6,.5,.4,.3],
    [.2,.3,.4,.5,.6,.7,.8,.9,.8,.7,.6,.5,.4,.3,.2],
])
def test_quant_differential(values):
    x=engine();x.temporal_results={'P1':{'daily':quant_daily(values)}}
    try: a=x._calculate_quant_one('P1')
    except ValueError as exc:
        with pytest.raises(ValueError,match=str(exc).split('(')[0].replace('.',r'\.')):calculate_quant_one('P1',x.temporal_results)
        return
    b=calculate_quant_one('P1',x.temporal_results)
    assert a.keys()==b.keys()
    for key in a:
        va,vb=a[key],b[key]
        if pd.isna(va):assert pd.isna(vb),key
        elif isinstance(va,(float,np.floating)):assert vb==pytest.approx(va),key
        else:assert va==vb,key

def test_quant_core_no_gui_import():
    import subprocess
    proc=subprocess.run([sys.executable,'-c','import cropwater_rs.core.quant; import sys; assert "tkinter" not in sys.modules and "sentinelhub" not in sys.modules'],cwd=Path(__file__).resolve().parents[1]/'src',capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
