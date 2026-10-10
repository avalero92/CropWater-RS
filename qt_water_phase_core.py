"""Independent reporting layer; never modifies scientific daily water calculations."""
import numpy as np
import pandas as pd
from qt_quant_scope import normalize_id
PHASES=('Start','Development','Mid-season','Late-season')
METRICS=('ndvi_reconstructed_daily','kc','eto_mm','pe_mm','etc_mm','iwr_net_mm')

def summarize_water(daily,mode='full',quant=None,sowing=None):
    if mode not in ('full','quant'):raise ValueError('Unknown analysis mode')
    rows=[];annotated=[];issues=[]
    qmap={}
    if quant is not None:
        for _,r in quant.iterrows():
            key=normalize_id(r['parcel_id'])
            if key in qmap:
                issues.append(f'{key}: duplicate QUANT parcel identifier after normalization')
                qmap[key]=None
            else:qmap[key]=r
    normalized_sowing={normalize_id(k):v for k,v in (sowing or {}).items()}
    for pid,g in daily.groupby('parcel_id',sort=True):
        g=g.sort_values('date').copy();g['date']=pd.to_datetime(g['date']).dt.normalize();pid=str(pid)
        if mode=='full':
            g['growth_phase']='Full time series';segments=[('Full time series',g)]
        else:
            q=qmap.get(normalize_id(pid));start=normalized_sowing.get(normalize_id(pid))
            if q is None:issues.append(f'{pid}: missing or ambiguous QUANT parcel result');continue
            if str(q.get('status','')).strip().casefold()!='complete':issues.append(f'{pid}: incomplete QUANT ({q.get("status","unknown")})');continue
            if start is None or pd.isna(start):issues.append(f'{pid}: missing sowing date (vector/manual/Q1 offset)');continue
            try:
                boundaries=[pd.Timestamp(start).normalize()]+[pd.Timestamp(q[f'Q{i}_date']).normalize() for i in range(1,5)]
                if any(pd.isna(t) for t in boundaries) or not all(a<b for a,b in zip(boundaries,boundaries[1:])):raise ValueError('invalid phase chronology')
                if boundaries[0]<g['date'].min() or boundaries[-1]>g['date'].max():raise ValueError('cycle exceeds daily data coverage')
                if g['date'].duplicated().any():raise ValueError('duplicate daily dates')
                expected=pd.date_range(boundaries[0],boundaries[-1],freq='D')
                if not expected.isin(g['date']).all():raise ValueError('missing daily dates in crop cycle')
            except Exception as e:issues.append(f'{pid}: {e}');continue
            g['growth_phase']='Outside crop cycle';segments=[]
            for i,name in enumerate(PHASES):
                mask=(g['date']>=boundaries[i]) & ((g['date']<boundaries[i+1]) if i<3 else (g['date']<=boundaries[i+1]))
                g.loc[mask,'growth_phase']=name;segments.append((name,g.loc[mask].copy()))
            segments.append(('Total crop cycle',g[g['growth_phase'].isin(PHASES)].copy()))
            for i,label in enumerate(('Sowing','Q1','Q2','Q3','Q4')):g[label+'_date']=boundaries[i]
        annotated.append(g)
        for phase,part in segments:
            if part.empty:issues.append(f'{pid}: empty {phase} phase');continue
            rec={'parcel_id':pid,'crop':part['crop'].iloc[0],'kc_relation':part['kc_relation'].iloc[0],
                 'analysis_mode':mode,'phase':phase,'start_date':part['date'].min(),'end_date':part['date'].max(),'days':len(part)}
            for metric in METRICS:
                if metric not in part:continue
                x=pd.to_numeric(part[metric],errors='coerce')
                rec[metric+'_mean']=x.mean();rec[metric+'_min']=x.min();rec[metric+'_max']=x.max()
                if metric in ('eto_mm','pe_mm','etc_mm','iwr_net_mm'):rec[metric+'_total']=x.sum()
            rows.append(rec)
    return pd.DataFrame(rows),pd.concat(annotated,ignore_index=True) if annotated else pd.DataFrame(),issues
