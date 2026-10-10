"""Sentinel Hub CDSE Process API NDVI GeoTIFF acquisition in a Qt worker.

Single-scene least-cloud mosaic for a user-specified date window, NOT a
multi-date time series. The output is masked to the selected parcel.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import numpy as np
from PySide6.QtCore import QThread, Signal
from qt_cdse_acquisition import CDSE_BASE_URL, CDSE_TOKEN_URL

EVALSCRIPT = '''//VERSION=3
function setup() {
 return {input:[{bands:["B04","B08","SCL","dataMask"]}],
         output:{bands:2,sampleType:"FLOAT32"}};
}
function evaluatePixel(s) {
 let bad=[0,1,3,8,9,10,11].includes(s.SCL);
 let d=s.B08+s.B04;
 let ok=s.dataMask===1 && !bad && d>0;
 return [ok ? (s.B08-s.B04)/d : -9999, ok ? 1 : 0];
}'''

@dataclass(frozen=True)
class RasterSettings:
    client_id: str
    client_secret: str
    start: str
    end: str
    resolution: int
    output_path: str

def validate_raster_settings(s: RasterSettings):
    if not s.client_id.strip() or not s.client_secret.strip():
        raise ValueError('CDSE Client ID and secret are required.')
    if date.fromisoformat(s.start) > date.fromisoformat(s.end):
        raise ValueError('Start date is after end date.')
    if s.resolution not in (10,20,30):
        raise ValueError('Resolution must be 10, 20 or 30 metres.')
    if Path(s.output_path).suffix.lower() not in ('.tif','.tiff'):
        raise ValueError('Output must be a GeoTIFF (.tif).')

def raster_shape(bounds, resolution, max_pixels=8_000_000):
    x0,y0,x1,y1=map(float,bounds)
    if not np.isfinite([x0,y0,x1,y1]).all() or x1<=x0 or y1<=y0:
        raise ValueError('Invalid parcel bounds.')
    w=max(1,int(np.ceil((x1-x0)/resolution)))
    h=max(1,int(np.ceil((y1-y0)/resolution)))
    if w*h>max_pixels:
        raise ValueError(f'Request is too large ({w*h:,} pixels). Select a smaller parcel or coarser resolution.')
    return w,h

def write_masked_geotiff(path, array, bounds, parcel_geometry, resolution):
    """Mask parcel in EPSG:3857; atomic output prevents partial TIFFs."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds
    from shapely.geometry import mapping
    arr=np.asarray(array)
    if arr.ndim!=3 or arr.shape[2]<2:
        raise ValueError('Unexpected CDSE response; expected NDVI and validity bands.')
    h,w=arr.shape[:2]
    transform=from_bounds(*bounds,w,h)
    inside=geometry_mask([mapping(parcel_geometry)],out_shape=(h,w),transform=transform,invert=True)
    valid=inside & (arr[:,:,1]>0) & np.isfinite(arr[:,:,0]) & (arr[:,:,0]>=-1) & (arr[:,:,0]<=1)
    ndvi=np.where(valid,arr[:,:,0],-9999).astype('float32')
    dst=Path(path);dst.parent.mkdir(parents=True,exist_ok=True)
    tmp=dst.with_name(dst.stem+'.partial.tif')
    try:
        with rasterio.open(tmp,'w',driver='GTiff',height=h,width=w,count=1,dtype='float32',crs='EPSG:3857',transform=transform,nodata=-9999,compress='deflate') as out:
            out.write(ndvi,1)
            out.update_tags(product='NDVI',source='CDSE Sentinel-2 L2A Process API',valid_pixels=int(valid.sum()))
        tmp.replace(dst)
    finally:
        if tmp.exists():tmp.unlink()
    return int(valid.sum())

class RasterWorker(QThread):
    progress=Signal(int,str)
    completed=Signal(str,int)
    failed=Signal(str)
    def __init__(self,parcel,settings):
        super().__init__()
        # Shapely Polygon/MultiPolygon objects are immutable and have no .copy().
        # Keep the original geometry: no mutation occurs in the raster worker.
        self.parcel = parcel
        self.settings = settings
    def run(self):
        try:
            validate_raster_settings(self.settings)
            from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, BBox, CRS, MimeType
            from cropwater_rs.acquisition.cdse import get_cdse_l2a_collection
            from geopandas import GeoSeries
            s=self.settings
            if self.parcel is None or self.parcel.is_empty:
                raise ValueError('Selected parcel has no valid geometry.')
            geo=GeoSeries([self.parcel],crs='EPSG:3857').iloc[0]
            bounds=tuple(map(float,geo.bounds))
            w,h=raster_shape(bounds,s.resolution)
            config=SHConfig();config.sh_client_id=s.client_id;config.sh_client_secret=s.client_secret
            config.sh_base_url=CDSE_BASE_URL;config.sh_token_url=CDSE_TOKEN_URL
            self.progress.emit(15,f'CDSE Process API · requesting {w} × {h} pixels')
            req=SentinelHubRequest(evalscript=EVALSCRIPT,
                input_data=[SentinelHubRequest.input_data(data_collection=get_cdse_l2a_collection(DataCollection,CDSE_BASE_URL),time_interval=(s.start,s.end),mosaicking_order='leastCC')],
                responses=[SentinelHubRequest.output_response('default',MimeType.TIFF)],
                bbox=BBox(bounds,crs=CRS.POP_WEB),size=(w,h),config=config)
            data=req.get_data()[0]
            self.progress.emit(85,'Masking parcel and writing GeoTIFF')
            # Raster pixels correspond to the exact requested BBox and size.
            count=write_masked_geotiff(s.output_path,data,bounds,geo,s.resolution)
            self.progress.emit(100,'NDVI raster saved')
            self.completed.emit(s.output_path,count)
        except Exception as exc:
            self.failed.emit(str(exc))
