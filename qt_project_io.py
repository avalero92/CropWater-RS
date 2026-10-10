"""Portable, versioned and non-executable .cwrs project archive."""
from __future__ import annotations
import io, json, zipfile
from pathlib import Path
import pandas as pd

FORMAT_VERSION = 1
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 32
MAX_MEMBER_BYTES = 600 * 1024 * 1024
TABLES = ('pre_raw','pre_cleaned','pre_summary','pre_reconstructed','pre_diagnostics',
          'quant_data','quant_results','water_ndvi','water_weather','water_results',
          'water_phase_summary','water_phase_daily')
DATE_COLUMNS = {'date_start','date_end','acquisition_date','date','sowing_date','q1_date','q2_date','q3_date','q4_date','cycle_start_date',
                'Q1','Q2','Q3','Q4','SOS','EOS'}

def save_archive(path, tables, state, parcels=None):
    """Write into a temporary file; caller atomically replaces destination."""
    path=Path(path)
    manifest={'format':'CropWater-RS project','schema':FORMAT_VERSION,'application':'3.8',
              'tables':[], 'has_parcels':parcels is not None, 'state':state}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name in TABLES:
            frame=tables.get(name)
            if frame is None:continue
            if not isinstance(frame,pd.DataFrame):raise TypeError(name+' must be a DataFrame')
            # Explicitly retain empty tables (including column-less DataFrames).
            z.writestr('tables/'+name+'.csv',frame.to_csv(index=False))
            manifest['tables'].append(name)
        if parcels is not None:
            if not hasattr(parcels,'to_json'):raise ValueError('Parcel geometry cannot be serialized as GeoJSON')
            z.writestr('parcels.geojson',parcels.to_json())
            manifest['parcel_crs']=str(parcels.crs) if getattr(parcels,'crs',None) else None
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2,default=str))

def load_archive(path):
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('Damaged project archive')
        member_names=z.namelist()
        if len(member_names)>MAX_MEMBERS or len(set(member_names))!=len(member_names):
            raise ValueError('Invalid project archive: too many or duplicate members')
        names=set(member_names)
        allowed={'manifest.json','parcels.geojson'} | {'tables/'+name+'.csv' for name in TABLES}
        if names-allowed:raise ValueError('Unexpected project archive members')
        if sum(info.file_size for info in z.infolist())>MAX_ARCHIVE_UNCOMPRESSED:
            raise ValueError('Project archive exceeds uncompressed size limit')
        if 'manifest.json' not in names:raise ValueError('Not a CropWater-RS project')
        for info in z.infolist():
            if info.file_size>MAX_MEMBER_BYTES:raise ValueError('Archive member exceeds safety limit')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('format')!='CropWater-RS project':raise ValueError('Invalid project format')
        if manifest.get('schema')!=FORMAT_VERSION:raise ValueError('Unsupported project schema: '+str(manifest.get('schema')))
        tables={}
        for name in manifest.get('tables',[]):
            if name not in TABLES:raise ValueError('Unknown table '+str(name))
            entry='tables/'+name+'.csv'
            if entry not in names:raise ValueError('Missing '+entry)
            raw=z.read(entry)
            try:df=pd.read_csv(io.BytesIO(raw),low_memory=False,dtype={'parcel_id':'string'})
            except pd.errors.EmptyDataError:df=pd.DataFrame()
            for col in df.columns:
                if col in DATE_COLUMNS or col.lower().endswith('_date'):
                    if col!='date' and col in ('Q1','Q2','Q3','Q4'):continue
                    parsed=pd.to_datetime(df[col],errors='coerce')
                    if parsed.notna().any():df[col]=parsed
            tables[name]=df
        parcels=None
        if manifest.get('has_parcels'):
            if 'parcels.geojson' not in names:raise ValueError('Missing parcel geometries')
            import geopandas as gpd
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as temp:
                geo=Path(temp)/'parcels.geojson';geo.write_bytes(z.read('parcels.geojson'))
                parcels=gpd.read_file(geo)
                if manifest.get('parcel_crs') and parcels.crs is None:parcels=parcels.set_crs(manifest['parcel_crs'])
        return tables,manifest.get('state',{}),parcels
