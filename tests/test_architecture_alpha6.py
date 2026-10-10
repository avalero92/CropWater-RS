"""Alpha 6: isolated exports, provenance and integration guards."""
import ast
import hashlib
import subprocess
import sys
from pathlib import Path
import pandas as pd
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cropwater_rs.io.exports import metadata_rows, combined_parcel_frames, temporal_quality_rows, model_assignment_rows
from cropwater_rs.io.provenance import sha256_file,metadata_text

def test_entrypoint_ast():
    ast.parse((ROOT/'cropwater_rs.py').read_text(encoding='utf-8'))

def test_entrypoint_compile():
    p=subprocess.run([sys.executable,'-m','py_compile',str(ROOT/'cropwater_rs.py')],capture_output=True,text=True)
    assert p.returncode==0,p.stderr

def test_core_import_isolation():
    p=subprocess.run([sys.executable,'-c','import sys; from cropwater_rs.io.exports import metadata_rows; from cropwater_rs.io.provenance import sha256_file; assert "tkinter" not in sys.modules and "sentinelhub" not in sys.modules'],cwd=ROOT/'src',capture_output=True,text=True)
    assert p.returncode==0,p.stderr

@pytest.mark.parametrize('metadata',[{}, {'app_version':'1.0.1','temporal_method':'Kalman'}, {'missing':None,'flag':False,'num':1.5}])
def test_metadata_rows(metadata):
    assert metadata_rows(metadata)==[{'parameter':k,'value':v} for k,v in metadata.items()]

@pytest.mark.parametrize('metadata',[{}, {'app_version':'1.0.1','valid':False}, {'name':'CWR','n':5}])
def test_metadata_text(metadata):
    assert metadata_text(metadata)==[f'{k}: {v}' for k,v in metadata.items()]

def test_temporal_quality():
    data={'p1':{'n_accepted':8,'longest_gap_days':10},'p2':{'n_accepted':None}}
    assert temporal_quality_rows(data)==[{'parcel_id':'p1','n_accepted':8,'longest_gap_days':10},{'parcel_id':'p2','n_accepted':None,'longest_gap_days':None}]

def test_empty_frames():
    assert combined_parcel_frames({'a':None,'b':pd.DataFrame()}) is None

def test_frame_combination_and_order():
    data={'a':pd.DataFrame({'Kc':[0.5,0.6]}),'b':pd.DataFrame({'Kc':[0.8]})}
    pd.testing.assert_frame_equal(combined_parcel_frames(data),pd.DataFrame({'Kc':[0.5,0.6,0.8]}))

def test_frame_injection_does_not_mutate():
    data={'a':pd.DataFrame({'ndvi':[0.2]}),'b':pd.DataFrame({'ndvi':[0.7]})}
    result=combined_parcel_frames(data,inject_id=True)
    assert result['parcel_id'].tolist()==['a','b']
    assert 'parcel_id' not in data['a'].columns

def test_existing_parcel_id_not_overwritten():
    data={'a':pd.DataFrame({'parcel_id':['original'],'ndvi':[0.3]})}
    assert combined_parcel_frames(data,inject_id=True)['parcel_id'].tolist()==['original']

def test_model_assignments_empty():
    assert model_assignment_rows(None,{}, {})==[]

def test_model_assignments_fields():
    gdf=pd.DataFrame({'parcel_id':['p1','p2'],'crop':['BARLEY','MAIZE']})
    cat={'linear':{'label':'L','equation':'Kc=NDVI','reference':'R'}}
    rows=model_assignment_rows(gdf,{'p1':'linear','p2':'invalid'},cat)
    assert len(rows)==1 and rows[0]['Kc_model_id']=='linear'
    assert rows[0]['kc_type']=='Kc' and rows[0]['verification_status']==''

def test_fingerprint(tmp_path):
    file=tmp_path/'input.csv'; file.write_bytes(b'abc')
    assert sha256_file(file)==hashlib.sha256(b'abc').hexdigest()

def test_fingerprint_detects_changes(tmp_path):
    file=tmp_path/'input.csv'; file.write_bytes(b'abc'); first=sha256_file(file)
    file.write_bytes(b'abd'); assert sha256_file(file)!=first

def test_adapters_wired():
    tree=ast.parse((ROOT/'cropwater_rs.py').read_text(encoding='utf-8'))
    calls={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    assert {'metadata_rows','metadata_text','model_assignment_rows','temporal_quality_rows'}<=calls
