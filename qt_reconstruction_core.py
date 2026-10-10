"""Adapter for the original CropWater-RS temporal reconstruction core.

No reconstruction algorithms are implemented here; this calls core.temporal.
"""
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from cropwater_rs.core.temporal import process_one_temporal_series
METHODS=('Linear interpolation','Whittaker','Savitzky-Golay','Kalman')

def reconstruct_qc(frame, method='Whittaker', lam=100.0, sg_window=21, constrain_ndvi=True):
    if method not in METHODS: raise ValueError('Unsupported reconstruction method: '+str(method))
    required={'parcel_id','date_start','ndvi_p50','accepted'}
    if not required.issubset(frame.columns): raise ValueError('Run Quality Control before reconstruction; missing: '+', '.join(sorted(required-set(frame.columns))))
    records=[]; failures=[]; diagnostics=[]
    for pid, part in frame.groupby('parcel_id',dropna=True):
        good=part.loc[part['accepted'] & part['ndvi_p50'].notna()].copy()
        if len(good)<2:
            failures.append((str(pid),'Fewer than two accepted observations'));continue
        dates=pd.to_datetime(good['date_start'],utc=True,errors='coerce').dropna()
        if len(dates)<2:
            failures.append((str(pid),'Fewer than two valid dates'));continue
        start=dates.min().tz_convert(None).normalize();end=dates.max().tz_convert(None).normalize()
        try:
            result=process_one_temporal_series(part,method,float(lam),int(sg_window),start,end,bool(constrain_ndvi),'Daily')
            daily=result['daily'].copy();daily.insert(0,'parcel_id',str(pid));records.append(daily)
            diagnostics.append({'parcel_id':str(pid),'method':method,**result['diagnostics'],**result['quality']})
        except Exception as exc:failures.append((str(pid),str(exc)))
    if not records:raise ValueError('No parcel could be reconstructed. '+ '; '.join(f'{p}: {e}' for p,e in failures[:5]))
    return pd.concat(records,ignore_index=True),pd.DataFrame(diagnostics),failures
