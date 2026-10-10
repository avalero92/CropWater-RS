import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from baseline_temporal_quant_snapshot import BaselineMethods

class DummyVar:
    def __init__(self, value): self.value=value
    def get(self): return self.value

def engine(start='2024-01-01',end='2024-01-21',constrain=True,resolution='Daily'):
    x=BaselineMethods(); x.start_var=DummyVar(start); x.end_var=DummyVar(end)
    x.constrain_ndvi_var=DummyVar(constrain); x.output_resolution_var=DummyVar(resolution)
    x.quant_q1_var=DummyVar(10); x.quant_q2_var=DummyVar(90)
    x.quant_q3_var=DummyVar(90); x.quant_q4_var=DummyVar(50)
    x.gdf=None; x.temporal_results={}
    return x

def observations(dates=('2024-01-03','2024-01-11','2024-01-19'),values=(.2,.8,.3)):
    return pd.DataFrame({'date_start':pd.to_datetime(list(dates),utc=True), 'ndvi_p50':values,'accepted':True})

@pytest.mark.parametrize('method', ['Raw observations','Linear interpolation','Whittaker','Savitzky-Golay','Kalman'])
def test_temporal_methods_finite_or_sparse(method):
    x=engine(); result=x._process_one_temporal_series(observations(),method,10,7)
    daily=result['daily']['ndvi_reconstructed_daily'].to_numpy()
    assert len(daily)==21
    if method=='Raw observations': assert np.isnan(daily).sum()==21
    else: assert np.isfinite(daily).all()
    assert result['quality']['n_accepted']==3

@pytest.mark.parametrize('resolution,expected', [('Daily',21),('5 days',5),('10 days',3)])
def test_output_sampling(resolution,expected):
    x=engine(resolution=resolution); result=x._process_one_temporal_series(observations(),'Linear interpolation',10,7)
    assert len(result['output'])==expected

def test_linear_interpolation_exact():
    x=engine(); r=x._process_one_temporal_series(observations(),'Linear interpolation',10,7)
    vals=r['daily']['ndvi_reconstructed_daily'].to_numpy()
    assert vals[0]==pytest.approx(.2); assert vals[6]==pytest.approx(.5); assert vals[-1]==pytest.approx(.3)

def test_utc_dates_and_duplicate_median():
    x=engine(); df=observations(('2024-01-03','2024-01-03','2024-01-19'),(.2,.4,.8))
    r=x._process_one_temporal_series(df,'Linear interpolation',10,7)
    assert r['quality']['n_accepted']==2
    assert r['daily']['ndvi_observed'].iloc[2]==pytest.approx(.3)

def test_reject_single_observation():
    with pytest.raises(ValueError,match='At least two'):
        engine()._process_one_temporal_series(observations(('2024-01-03',),(.2,)),'Kalman',10,7)

def test_invalid_temporal_method():
    with pytest.raises(ValueError,match='Unknown temporal method'):
        engine()._process_one_temporal_series(observations(),'NoSuchMethod',10,7)

def test_savgol_even_window_adjustment():
    x=engine(); a=x._process_one_temporal_series(observations(),'Savitzky-Golay',10,6)
    b=x._process_one_temporal_series(observations(),'Savitzky-Golay',10,7)
    np.testing.assert_allclose(a['daily']['ndvi_reconstructed_daily'],b['daily']['ndvi_reconstructed_daily'])

def test_kalman_insufficient_data_returns_nan():
    assert np.isnan(BaselineMethods._kalman_smooth_local_level([np.nan,.5,np.nan])).all()

def test_ndvi_clipping():
    x=engine(); r=x._process_one_temporal_series(observations(values=(-.2,1.2,.3)),'Linear interpolation',10,7)
    assert r['daily']['ndvi_reconstructed_daily'].min()>=0
    assert r['daily']['ndvi_reconstructed_daily'].max()<=1

def test_quant_crossing_interpolation():
    d=pd.date_range('2024-01-01',periods=3)
    assert BaselineMethods._quant_crossing_date(d,[0,.5,1],.25,'rising')==pd.Timestamp('2024-01-01 12:00:00')

def test_quant_no_crossing():
    assert pd.isna(BaselineMethods._quant_crossing_date(pd.date_range('2024-01-01',periods=3),[.2,.3,.4],.9,'rising'))

@pytest.mark.parametrize('q1,q2,q3,q4',[(0,90,90,50),(90,10,90,50),(10,90,50,90),(10,100,90,50)])
def test_quant_reject_invalid_thresholds(q1,q2,q3,q4):
    x=engine(); [setattr(x,'quant_q'+str(i)+'_var',DummyVar(v)) for i,v in enumerate((q1,q2,q3,q4),1)]
    with pytest.raises(ValueError): x._validate_quant_thresholds()

def quant_daily(values):
    return pd.DataFrame({'date':pd.date_range('2024-01-01',periods=len(values)), 'ndvi_reconstructed_daily':values})

def test_quant_complete_triangular_cycle():
    x=engine(); vals=[.2,.3,.4,.5,.6,.7,.8,.9,1.,.9,.8,.7,.6,.5,.4,.3,.2]
    x.temporal_results={'P1':{'daily':quant_daily(vals)}}
    r=x._calculate_quant_one('P1')
    assert r['status']=='Complete'; assert r['NDVI_amplitude']==pytest.approx(.8)
    assert r['Q1_date']<r['Q2_date']<r['Q3_date']<r['Q4_date']
    assert r['Total_days']==pytest.approx(12)

def test_quant_low_amplitude_rejected():
    x=engine(); x.temporal_results={'P1':{'daily':quant_daily([.2,.21,.22,.23,.24,.23,.22])}}
    with pytest.raises(ValueError,match='Insufficient seasonal NDVI amplitude'): x._calculate_quant_one('P1')

def test_quant_boundary_peak_rejected():
    x=engine(); x.temporal_results={'P1':{'daily':quant_daily([.9,.8,.7,.6,.5,.4,.3])}}
    with pytest.raises(ValueError,match='temporal boundary'): x._calculate_quant_one('P1')

def test_quant_short_series_rejected():
    x=engine(); x.temporal_results={'P1':{'daily':quant_daily([.2,.5,.4,.2])}}
    with pytest.raises(ValueError,match='Too few'): x._calculate_quant_one('P1')
