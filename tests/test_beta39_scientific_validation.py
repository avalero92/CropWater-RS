"""Beta 3.9: deterministic scientific and project-integrity regression tests."""
import io
import json
import zipfile
import numpy as np
import pandas as pd
import pytest
from src.cropwater_rs.core.water import calculate_linear_kc, calculate_etc, calculate_net_iwr
from src.cropwater_rs.core.quant import validate_quant_thresholds, quant_crossing_date
from qt_project_io import save_archive, load_archive


def test_water_equations_reference_vector():
    ndvi=np.array([0.0,0.2,0.5,0.8]); eto=np.array([4.,4.,4.,4.]); pe=np.array([0.,2.,4.,10.])
    kc=calculate_linear_kc(ndvi,1.25,0.1)
    np.testing.assert_allclose(kc,[.1,.35,.725,1.1])
    etc=calculate_etc(kc,eto)
    np.testing.assert_allclose(etc,[.4,1.4,2.9,4.4])
    np.testing.assert_allclose(calculate_net_iwr(etc,pe),[.4,0,0,0])
    assert np.all(calculate_net_iwr(etc,pe)>=0)


def test_negative_kc_clipping_and_unclipped_mode():
    assert calculate_linear_kc([0.],1.,-.5)[0]==0
    assert calculate_linear_kc([0.],1.,-.5,constrain_nonnegative=False)[0]==-.5


@pytest.mark.parametrize('thresholds',[(0,90,90,50),(10,100,90,50),(90,10,90,50),(10,90,40,50)])
def test_invalid_quant_thresholds(thresholds):
    with pytest.raises(ValueError):validate_quant_thresholds(*thresholds)


def test_quant_defaults_and_crossing_direction():
    assert validate_quant_thresholds(10,90,90,50)==[10.,90.,90.,50.]
    dates=pd.date_range('2024-01-01',periods=5,freq='D')
    rising=quant_crossing_date(dates,[0,.25,.5,.75,1.],.5,'rising')
    falling=quant_crossing_date(dates,[1.,.75,.5,.25,0.],.5,'falling')
    assert rising==dates[2] and falling==dates[2]


def test_project_roundtrip_preserves_tables_and_state(tmp_path):
    path=tmp_path/'trial.cwrs'
    tables={'pre_raw':pd.DataFrame({'parcel_id':['103.0','128.0'],'ndvi':[.4,.6]}),
            'water_results':pd.DataFrame({'date':['2024-03-01'],'etc_mm':[2.4],'iwr_mm':[1.1]}),
            'quant_results':pd.DataFrame()}
    state={'quant':{'start_overrides':{'103.0':'2024-02-14'}},'water':{'sowing_offsets':{'Barley':30}}}
    save_archive(path,tables,state)
    restored,meta,parcels=load_archive(path)
    assert parcels is None and meta==state
    assert restored['pre_raw']['parcel_id'].tolist()==tables['pre_raw']['parcel_id'].tolist()
    np.testing.assert_allclose(restored['pre_raw']['ndvi'],tables['pre_raw']['ndvi'])
    assert restored['quant_results'].empty
    assert restored['water_results']['iwr_mm'].iloc[0]==1.1


def test_reject_nonproject_archive(tmp_path):
    path=tmp_path/'invalid.cwrs'
    with zipfile.ZipFile(path,'w') as z:z.writestr('other.txt','bad')
    with pytest.raises(ValueError):load_archive(path)


def test_reject_duplicate_archive_members(tmp_path):
    path=tmp_path/'duplicate.cwrs'
    manifest={'format':'CropWater-RS project','schema':1,'tables':[],'state':{}}
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            z.writestr('manifest.json',json.dumps(manifest))
    with pytest.raises(ValueError,match='duplicate'):load_archive(path)


def test_reject_unexpected_archive_members(tmp_path):
    path=tmp_path/'unexpected.cwrs'
    manifest={'format':'CropWater-RS project','schema':1,'tables':[],'state':{}}
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest))
        z.writestr('../unexpected.txt','bad')
    with pytest.raises(ValueError,match='Unexpected'):load_archive(path)
