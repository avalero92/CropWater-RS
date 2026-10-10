"""Qt worker for native CDSE Sentinel-2 L2A Statistical API acquisition."""
from __future__ import annotations
from dataclasses import dataclass
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from datetime import date
import time
import pandas as pd
from PySide6.QtCore import QThread, Signal

CDSE_BASE_URL = 'https://sh.dataspace.copernicus.eu'
CDSE_TOKEN_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'

# Scientific evalscript matches the validated Tk application.
NDVI_EVALSCRIPT = r'''//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL", "dataMask"]}],
    output: [{id: "ndvi", bands: 1, sampleType: "FLOAT32"}, {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let invalidSCL = [0, 1, 3, 8, 9, 10, 11].includes(sample.SCL);
  let valid = sample.dataMask === 1 && !invalidSCL;
  if (!valid) return {ndvi: [NaN], dataMask: [0]};
  let den = sample.B08 + sample.B04;
  return {ndvi: [den === 0 ? NaN : (sample.B08 - sample.B04) / den], dataMask: [1]};
}'''

@dataclass(frozen=True)
class CDSESettings:
    client_id: str
    client_secret: str
    start: str
    end: str
    interval: str = 'P10D'

def validate_cdse_inputs(settings: CDSESettings):
    if not settings.client_id.strip() or not settings.client_secret.strip():
        raise ValueError('Enter a CDSE Sentinel Hub Client ID and Client Secret.')
    if date.fromisoformat(settings.start) > date.fromisoformat(settings.end):
        raise ValueError('Start date must be on or before end date.')
    if settings.interval not in ('P1D','P5D','P10D','P1M'):
        raise ValueError('Unsupported aggregation interval.')

class CDSEWorker(QThread):
    progress = Signal(int,str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, parcels, settings: CDSESettings):
        super().__init__()
        self.parcels = parcels.copy()
        self.settings = settings

    def run(self):
        try:
            validate_cdse_inputs(self.settings)
            from sentinelhub import SHConfig, Geometry, CRS, DataCollection, SentinelHubStatistical
            from cropwater_rs.acquisition.cdse import build_statistical_request, stats_response_to_df
            from geopandas import GeoSeries
            config = SHConfig()
            config.sh_client_id = self.settings.client_id
            config.sh_client_secret = self.settings.client_secret
            config.sh_base_url = CDSE_BASE_URL
            config.sh_token_url = CDSE_TOKEN_URL
            total = len(self.parcels)
            if total == 0: raise ValueError('No parcels selected.')
            id_columns = [c for c in self.parcels.columns if c.lower() in ('id','parcel_id','id_parcela','parcela','name')]
            id_field = id_columns[0] if id_columns else None
            results=[]; errors=[]
            for pos,(_,row) in enumerate(self.parcels.iterrows(),start=1):
                parcel_id = str(row[id_field]) if id_field else str(pos)
                self.progress.emit(int(100*(pos-1)/total),f'CDSE · parcel {pos}/{total}: {parcel_id}')
                try:
                    geo = GeoSeries([row.geometry],crs=self.parcels.crs).to_crs(4326).iloc[0]
                    req = build_statistical_request(
                        Geometry(geo, CRS.WGS84), self.settings.start, self.settings.end,
                        self.settings.interval, config,
                        statistical_class=SentinelHubStatistical, data_collection=DataCollection,
                        base_url=CDSE_BASE_URL, evalscript=NDVI_EVALSCRIPT)
                    response=None
                    for attempt in range(3):
                        try:
                            response=req.get_data();break
                        except Exception:
                            if attempt==2:raise
                            time.sleep((2,5)[attempt])
                    if not response:raise RuntimeError('Empty Statistical API response')
                    df=stats_response_to_df(response[0])
                    if not df.empty:
                        df['parcel_id']=parcel_id
                        if 'crop' in row.index:df['crop']=str(row['crop'])
                        results.append(df)
                except Exception as exc:
                    errors.append(f'{parcel_id}: {exc}')
            if errors:
                # Avoid silently claiming success when a subset failed.
                if not results:raise RuntimeError('All parcel requests failed:\n'+'\n'.join(errors[:8]))
                self.progress.emit(99,f'{len(errors)} parcel(s) failed; partial results returned')
            result=pd.concat(results,ignore_index=True) if results else pd.DataFrame()
            if errors:result.attrs['errors']=errors
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
