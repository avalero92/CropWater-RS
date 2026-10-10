"""Alpha 5 isolated acquisition and parcel regression tests."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import numpy as np
import pandas as pd
import pytest
from cropwater_rs.acquisition.cdse import stats_response_to_df,build_statistical_request
from cropwater_rs.spatial.parcels import find_column_case_insensitive,normalize_crop_name,prepare_vector_attributes
from baseline_cdse_parcels_exports_snapshot import BaselineV4Methods as BaselineMethods

@pytest.mark.parametrize("response",[{}, {"data":[]}, {"data":[{"interval":{"from":"2024-01-01","to":"2024-01-11"},"outputs":{"ndvi":{"bands":{"B0":{"stats":{"mean":0.5,"sampleCount":100,"noDataCount":20,"percentiles":{"50.0":0.6}}}}}}}]}, {"data":[{"interval":{"from":"2024-03-01","to":"2024-03-11"},"outputs":{}}]}])
def test_stat_parser_baseline(response):
    pd.testing.assert_frame_equal(stats_response_to_df(response),BaselineMethods._stats_response_to_df(response))

@pytest.mark.parametrize('crop,expected', [('cebada','BARLEY'),('TRIGO BLANDO','WHEAT'),('guisante','PEA'),('girasol','SUNFLOWER'),('unknown','OTHER'),('', 'OTHER'),(None,'OTHER')])
def test_crop_aliases(crop,expected):assert normalize_crop_name(crop)==expected

def test_attribute_mapping():
    df=pd.DataFrame({'ID':['1','2'],'CROPS':['cebada','maiz']})
    out,a,b=prepare_vector_attributes(df.copy(),'<Auto>','<Auto>')
    assert out['parcel_id'].tolist()==['1','2']
    assert out['crop'].tolist()==['BARLEY','MAIZE']
    assert 'imported' in a and 'imported' in b

def test_missing_id_generation():
    df=pd.DataFrame({'ID':['1',None,'3'],'crop':['wheat','pea','barley']})
    out,*_=prepare_vector_attributes(df.copy(),'<Auto>','<Auto>')
    assert out['parcel_id'].tolist()==['1','P00001','3']

def test_case_insensitive_columns():assert find_column_case_insensitive([' Parcel_ID ','CROPS'],['parcel_id'])==' Parcel_ID '

class FakeCollection:
    class SENTINEL2_L2A:
        @staticmethod
        def define_from(**kwargs):return kwargs
class FakeStat:
    @staticmethod
    def aggregation(**kwargs):return kwargs
    @staticmethod
    def input_data(*args,**kwargs):return (args,kwargs)
    def __init__(self,**kwargs):self.kwargs=kwargs

def test_request_configuration():
    obj=build_statistical_request('polygon','2024-01-01','2024-02-01','P10D','cfg',statistical_class=FakeStat,data_collection=FakeCollection,base_url='url',evalscript='script')
    a=obj.kwargs['aggregation'];assert a['resolution']==(10,10) and a['aggregation_interval']=='P10D'
    assert obj.kwargs['calculations']['ndvi']['statistics']['default']['percentiles']['k']==[25,50,75]
    assert obj.kwargs['input_data'][0][1]['other_args']['dataFilter']['mosaickingOrder']=='leastCC'

def test_core_without_gui():
    import subprocess
    p=subprocess.run([sys.executable,'-c','import cropwater_rs.acquisition.cdse, cropwater_rs.spatial.parcels; import sys; assert "tkinter" not in sys.modules and "sentinelhub" not in sys.modules'],cwd=Path(__file__).resolve().parents[1]/'src',capture_output=True,text=True)
    assert p.returncode==0,p.stderr
