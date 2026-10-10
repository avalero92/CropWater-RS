"""Alpha 8 offline integration check; no GUI display or CDSE credentials required."""
from pathlib import Path
import ast, importlib, json, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from cropwater_rs.core.water import calculate_linear_kc, calculate_etc, calculate_net_iwr
from cropwater_rs.io.exports import combined_parcel_frames, metadata_rows
from cropwater_rs.io.provenance import metadata_text
from cropwater_rs.spatial.parcels import normalize_crop_name
from cropwater_rs.acquisition.cdse import stats_response_to_df
source=(ROOT/'cropwater_rs.py').read_text(encoding='utf-8')
ast.parse(source)
assert any(isinstance(n,ast.ClassDef) and n.name=='CropWaterRSApp' for n in ast.parse(source).body)
assert normalize_crop_name('cebada')=='BARLEY'
dates=pd.date_range('2023-05-01',periods=3,freq='D')
ndvi=np.array([.2,.5,.7])
kc=calculate_linear_kc(ndvi,1.25,.1)
etc=calculate_etc(kc,np.array([4.,5.,6.]))
iwr=calculate_net_iwr(etc,np.array([0.,1.,2.]))
assert np.allclose(kc,[.35,.725,.975])
assert np.allclose(etc,[1.4,3.625,5.85])
assert np.allclose(iwr,[1.4,2.625,3.85])
frame=pd.DataFrame({'Date':dates,'NDVI':ndvi,'Kc':kc,'ETc':etc,'IWRnet':iwr})
combined=combined_parcel_frames({'parcel-001':frame},inject_id=True)
assert len(combined)==3 and set(combined['parcel_id'])=={'parcel-001'}
assert list(metadata_rows({'version':'1.0.1'})[0])==['parameter','value']
with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/'daily.csv'
    combined.to_csv(p,index=False)
    reread=pd.read_csv(p)
    assert np.allclose(reread['IWRnet'],iwr)
    assert reread['parcel_id'].tolist()==['parcel-001']*3
print('PASS: Alpha 8 offline integration (launcher AST, crop, Kc, ETc, IWR, CSV, provenance)')
print('NOT TESTED: actual Tk window, CDSE authenticated acquisition, Windows binary')
