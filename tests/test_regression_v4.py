"""Offline characterization tests of literal original methods (no CDSE requests)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import geopandas as gpd
from shapely.geometry import box
sys.path.insert(0,str(Path(__file__).parent))
import baseline_cdse_parcels_exports_snapshot as original

class Var:
    def __init__(self, v): self.v=v
    def get(self): return self.v

@pytest.fixture
def app():
    a=original.BaselineV4Methods()
    a.software_metadata={'author':'Example','orcid':'','repository_url':'','zenodo_doi':'','license':'GPL-3.0'}
    a.meteo_file=None
    a.gdf=None
    a.ndvi_results={}; a.kc_results={}; a.water_results={}; a.kc_assignments={}; a.temporal_results={}; a.temporal_quality={}
    a.quant_results={}; a.quant_water_summary={}
    return a

def test_cdse_stats_sorted_and_percentiles(app):
    response={'data':[
        {'interval':{'from':'2024-02-01','to':'2024-02-11'},'outputs':{'ndvi':{'bands':{'B0':{'stats':{'mean':.4,'sampleCount':10,'noDataCount':2,'percentiles':{'25.0':.2,'50.0':.45,'75.0':.6}}}}}}},
        {'interval':{'from':'2024-01-01','to':'2024-01-11'},'outputs':{'ndvi':{'bands':{'B0':{'stats':{'mean':.5,'sampleCount':20,'noDataCount':0,'percentiles':{'25':.3,'50':.5,'75':.7}}}}}}},
    ]}
    df=app._stats_response_to_df(response)
    assert len(df)==2
    assert df.date_start.is_monotonic_increasing
    assert df.ndvi_p50.tolist()==[.5,.45]
    assert df.valid_fraction_pct.tolist()==[100.,80.]
    assert df.sample_count.tolist()==[20,10]

def test_cdse_empty_response(app):
    assert app._stats_response_to_df({'data':[]}).empty

def test_cdse_missing_stats_are_nan(app):
    df=app._stats_response_to_df({'data':[{'interval':{'from':'2024-01-01','to':'2024-01-10'},'outputs':{}}]})
    assert np.isnan(df.ndvi_p50.iloc[0]); assert np.isnan(df.valid_fraction_pct.iloc[0])

def test_cdse_zero_samples(app):
    df=app._stats_response_to_df({'data':[{'interval':{'from':'2024-01-01'},'outputs':{'ndvi':{'bands':{'B0':{'stats':{'sampleCount':0,'noDataCount':0}}}}}}]})
    assert np.isnan(df.valid_fraction_pct.iloc[0])

@pytest.mark.parametrize('column, candidates,expected',[
    (' ID ',['id'],' ID '),('CROPS',['crop','crops'],'CROPS'),('parcel_id',['ID','parcel_id'],'parcel_id')])
def test_case_insensitive_column(app,column,candidates,expected):
    assert app._find_column_case_insensitive([column],candidates)==expected

def test_column_not_found(app):
    assert app._find_column_case_insensitive(['foo'],['bar']) is None

@pytest.mark.parametrize('crop,expected', [(' cebada ','BARLEY'),('Trigo Blando','WHEAT'),('maíz','MAIZE'),('guisantes','PEA'),('nonsense','OTHER'),(None,'OTHER'),('','OTHER')])
def test_crop_normalization(app,crop,expected):
    assert app._normalize_crop_name(crop)==expected

def test_parcel_auto_id_crop_preserves_source(app):
    gdf=gpd.GeoDataFrame({' ID ':[' A ','B'], 'CROPS':['cebada','maíz']},geometry=[box(0,0,1,1),box(2,0,3,1)],crs='EPSG:4326')
    out,_,_=app._prepare_vector_attributes(gdf,id_field=' ID ',crop_field='<Auto>')
    assert out.parcel_id.tolist()==['A','B']; assert out.crop.tolist()==['BARLEY','MAIZE']
    assert out.crop_source.tolist()==['cebada','maíz']

def test_parcel_generated_ids(app):
    gdf=pd.DataFrame({'foo':[1,2]})
    out,_,_=app._prepare_vector_attributes(gdf,id_field='<Generate>')
    assert out.parcel_id.tolist()==['P00001','P00002']
    assert out.crop.tolist()==['OTHER','OTHER']

def test_parcel_missing_ids_generated_without_collision(app):
    gdf=pd.DataFrame({'ID':['P00001',None,'X']})
    out,_,_=app._prepare_vector_attributes(gdf,id_field='<Auto>')
    assert out.parcel_id.tolist()==['P00001','P00002','X']

def test_parcel_missing_selected_field_raises(app):
    with pytest.raises(ValueError,match='not present'):
        app._prepare_vector_attributes(pd.DataFrame({'ID':[1]}),id_field='missing')

def test_parcel_manual_mode_uses_other(app):
    out,_,_=app._prepare_vector_attributes(pd.DataFrame({'ID':['1'],'CROPS':['maíz']}),crop_field='<Manual / OTHER>')
    assert out.crop.iloc[0]=='OTHER' and out.crop_source.iloc[0]==''

def test_metadata_core_fields_and_version(app):
    app.start_var=Var('2024-01-01'); app.end_var=Var('2024-12-31'); app.quant_q1_var=Var(10)
    m=app._build_run_metadata()
    assert m['app_version']=='1.0.1'
    assert m['parcel_statistic']=='P50'
    assert m['scl_excluded_classes']=='0,1,3,8,9,10,11'
    assert m['quant_q1_percent']==10
    assert m['date_start']=='2024-01-01'
    assert m['generated_at']

def test_spatial_export_values_and_crs(app):
    app.gdf=gpd.GeoDataFrame({'parcel_id':['A','B'],'crop':['BARLEY','MAIZE'],'area_ha':[1.,2.]},geometry=[box(0,0,1,1),box(2,0,3,1)],crs='EPSG:4326')
    app.ndvi_results={'A':pd.DataFrame({'accepted':[True,False,True],'ndvi_p50':[.2,.9,.6]})}
    app.kc_results={'A':pd.DataFrame({'Kc':[.5,1.]})}
    app.water_results={'A':pd.DataFrame({'ETc':[2.,3.],'IWR_net':[1.,2.]})}
    out=app._build_spatial_export_gdf()
    assert out.crs==app.gdf.crs
    assert out.ndvi_p50_mean.iloc[0]==pytest.approx(.4)
    assert out.ndvi_p50_last.iloc[0]==pytest.approx(.6)
    assert out.cwr_total_mm.iloc[0]==pytest.approx(5.)
    assert out.iwr_net_total_mm.iloc[0]==pytest.approx(3.)
    assert np.isnan(out.cwr_total_mm.iloc[1]); assert out.app_version.tolist()==['1.0.1']*2

def test_spatial_export_no_parcels(app):
    with pytest.raises(ValueError,match='No parcels'):
        app._build_spatial_export_gdf()

def test_analysis_summary_file(app,tmp_path):
    app.gdf=gpd.GeoDataFrame({'parcel_id':['A'],'crop':['BARLEY'],'area_ha':[1.25]},geometry=[box(0,0,1,1)],crs='EPSG:4326')
    app.kc_results={'A':pd.DataFrame({'Kc':[.5,1.]})}
    app.water_results={'A':pd.DataFrame({'ETc':[2.,3.],'IWR_net':[1.,2.]})}
    app._write_analysis_summary(tmp_path)
    s=(tmp_path/'analysis_summary.txt').read_text()
    assert 'CropWater-RS v1.0.1' in s
    assert 'A | crop=BARLEY | area=1.25 ha' in s
    assert 'CWR=5.0 mm' in s and 'net IWR=3.0 mm' in s

def test_metadata_generation_is_dynamic(app):
    a=app._build_run_metadata()
    assert 'generated_at' in a and 'software_license' in a and 'iwr_definition' in a

class Dialog:
    def __init__(self, path): self.path=path
    def askdirectory(self, **kwargs): return str(self.path)

class Messages:
    def __init__(self): self.errors=[]; self.warnings=[]; self.infos=[]
    def showerror(self,*args): self.errors.append(args)
    def showwarning(self,*args): self.warnings.append(args)
    def showinfo(self,*args): self.infos.append(args)

@pytest.fixture
def exports(app,tmp_path,monkeypatch):
    messages=Messages()
    monkeypatch.setattr(original,'filedialog',Dialog(tmp_path),raising=False)
    monkeypatch.setattr(original,'messagebox',messages,raising=False)
    app.gdf=gpd.GeoDataFrame({'parcel_id':['A'],'crop':['BARLEY'],'area_ha':[1.2]},geometry=[box(0,0,1,1)],crs='EPSG:4326')
    app.ndvi_results={'A':pd.DataFrame({'date_start':pd.to_datetime(['2024-01-01']), 'ndvi_p50':[.5],'accepted':[True]})}
    app.temporal_results={}
    app.kc_results={'A':pd.DataFrame({'parcel_id':['A'],'date':pd.to_datetime(['2024-01-01']),'Kc':[.75]})}
    app.water_results={'A':pd.DataFrame({'parcel_id':['A'],'date':pd.to_datetime(['2024-01-01']),'ETc':[3.],'IWR_net':[2.]})}
    app.kc_assignments={'A':'kamble_2013_general'}
    return app,messages,tmp_path

def test_water_export_files_and_provenance(exports):
    app,msg,out=exports
    app.export_water_results()
    assert not msg.errors, msg.errors
    expected=['Kc_by_parcel/A_Kc.csv','Kc_all_parcels.csv','Water_by_parcel/A_CWR_IWR.csv','CWR_IWR_all_parcels.csv','Kc_model_assignments.csv','run_metadata.csv','analysis_summary.txt']
    for name in expected: assert (out/name).is_file(),name
    models=pd.read_csv(out/'Kc_model_assignments.csv')
    assert models.loc[0,'Kc_model_id']=='kamble_2013_general'
    meta=pd.read_csv(out/'run_metadata.csv')
    assert meta.set_index('parameter').loc['app_version','value']=='1.0.1'
    assert pd.read_csv(out/'CWR_IWR_all_parcels.csv').IWR_net.iloc[0]==2.

def test_ndvi_export_raw_files(exports):
    app,msg,out=exports
    app.export_all_results()
    assert not msg.errors,msg.errors
    assert (out/'NDVI_all_parcels_raw.csv').is_file()
    assert (out/'raw_by_parcel/A_NDVI_raw.csv').is_file()
    assert (out/'run_metadata.csv').is_file()

def test_export_empty_water_warns(exports):
    app,msg,out=exports; app.kc_results={}
    app.export_water_results()
    assert msg.warnings
    assert not (out/'Kc_all_parcels.csv').exists()
