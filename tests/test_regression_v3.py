"""Baseline characterization of original GUI-bound methods without opening Tk."""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import baseline_water_snapshot as mod
from baseline_core_snapshot import calculate_linear_kc

class Var:
    def __init__(self,v=''): self.v=v
    def get(self): return self.v
    def set(self,v): self.v=v
class Msg:
    def __init__(self): self.errors=[]; self.warnings=[]; self.infos=[]
    def showerror(self,*x): self.errors.append(x)
    def showwarning(self,*x): self.warnings.append(x)
    def showinfo(self,*x): self.infos.append(x)
@pytest.fixture
def ui(monkeypatch,tmp_path):
    m=Msg(); monkeypatch.setattr(mod,'messagebox',m,raising=False)
    obj=mod.BaselineWaterMethods(); obj.meteo_df=None; obj.meteo_file_var=Var(); obj.water_mode_var=Var('Net IWR'); obj.kc_results={}; obj.water_results={}; obj._invalidate_water=lambda:None; obj._plot_selected_water=lambda:None; obj._update_water_summary=lambda:None; obj._write_analysis_summary=lambda *_:None
    monkeypatch.setattr(mod,'filedialog',type('D',(),{'askopenfilename':lambda self, **kw: str(tmp_path/'met.csv')})(),raising=False)
    return obj,m,tmp_path

def load(ui,text):
    obj,m,tmp=ui; (tmp/'met.csv').write_text(text,encoding='utf-8'); obj.load_meteo_csv(); return obj,m

@pytest.mark.parametrize('text,expected',[
 ('Date,ETo,Pe\n2024-01-01,4,1\n2024-01-02,5,2\n',2),
 (' date ; eto ; pe \n01/02/2024;4;1\n02/02/2024;5;2\n',2),
 ('Date,ETo\n2024-01-01,4\n2024-01-02,5\n',2),
 ('Date,ETo,parcel_id\n2024-01-01,4,A\n2024-01-01,5,B\n',2),
])
def test_meteorology_valid(ui,text,expected):
    obj,m=load(ui,text); assert not m.errors; assert len(obj.meteo_df)==expected

@pytest.mark.parametrize('text,fragment',[
 ('Date,Pe\n2024-01-01,1\n','Date and ETo'),
 ('Date,ETo\n2024/01/01,4\n','could not be parsed'),
 ('Date,ETo\n2024-01-01,-1\n','negative'),
 ('Date,ETo\n2024-01-01,abc\n','non-numeric'),
 ('Date,ETo,Pe\n2024-01-01,4,-2\n','negative'),
 ('Date,ETo\n2024-01-01,4\n2024-01-01,5\n','Duplicate'),
])
def test_meteorology_rejected(ui,text,fragment):
    obj,m=load(ui,text); assert m.errors and fragment.lower() in str(m.errors[-1]).lower(); assert obj.meteo_df is None

def test_meteorology_high_values_warn_not_reject(ui):
    obj,m=load(ui,'Date,ETo,Pe\n2024-01-01,16,201\n'); assert not m.errors; assert 'Warning:' in str(m.infos)

def test_meteorology_european_day_month(ui):
    obj,m=load(ui,'Date,ETo\n02/03/2024,4\n'); assert obj.meteo_df['Date'].iloc[0]==pd.Timestamp('2024-03-02')

def test_library_metadata_and_coefficients(ui):
    obj,m,tmp=ui; obj.kc_library_path=Path(__file__).resolve().parents[1]/'config/kc_ndvi_library.json'; obj._load_kc_library(); assert not m.warnings
    lib=mod.KC_CATALOG; assert lib
    for key,item in lib.items():
        assert item['kc_type']=='Kc'; assert item['crops']; assert item['reference']; assert isinstance(item['a'],float)
        assert isinstance(item['b'],float); assert 'verification_status' in item
        assert np.isfinite(calculate_linear_kc([0.5],item['a'],item['b'])).all()

def test_library_invalid_fallback(ui):
    obj,m,tmp=ui; obj.kc_library_path=tmp/'invalid.json'; obj.kc_library_path.write_text('{"x":{"a":1}}'); obj._load_kc_library(); assert m.warnings

def setup_water(ui,mode='Net IWR',missing=False,source='Processed Linear'):
    obj,m,tmp=ui; dates=pd.date_range('2024-01-01',periods=3)
    obj.kc_results={'A':pd.DataFrame({'date':dates,'Kc':[.5,1.,1.5],'NDVI_source':[source]*3})}
    obj.meteo_df=pd.DataFrame({'Date':dates[:2] if missing else dates,'ETo':[4.,5.] if missing else [4.,5.,6.],'Pe':[1.,6.] if missing else [1.,6.,2.]})
    obj.water_mode_var.set(mode)
    return obj,m

def test_water_daily_and_cumulative(ui):
    obj,m=setup_water(ui); obj.calculate_water_all(); assert not m.errors; w=obj.water_results['A']
    np.testing.assert_allclose(w.ETc,[2,5,9]); np.testing.assert_allclose(w.CWR_cumulative,[2,7,16]); np.testing.assert_allclose(w.IWR_net,[1,0,7]); np.testing.assert_allclose(w.IWR_net_cumulative,[1,1,8])

def test_water_cwr_only(ui):
    obj,m=setup_water(ui,'CWR / ETc only'); obj.calculate_water_all(); w=obj.water_results['A']; assert 'IWR_net' not in w; assert w.CWR.sum()==16

def test_water_reject_raw_source(ui):
    obj,m=setup_water(ui,source='Raw observations'); obj.calculate_water_all(); assert m.warnings and not obj.water_results

def test_water_missing_day(ui):
    obj,m=setup_water(ui,missing=True); obj.calculate_water_all(); assert not obj.water_results; assert m.errors or m.warnings

def test_water_missing_pe(ui):
    obj,m=setup_water(ui); obj.meteo_df=obj.meteo_df.drop(columns=['Pe']); obj.calculate_water_all(); assert m.errors and not obj.water_results

def test_water_per_parcel(ui):
    obj,m=setup_water(ui); obj.meteo_df['parcel_id']='B'; obj.calculate_water_all(); assert not obj.water_results; assert m.errors or m.warnings
