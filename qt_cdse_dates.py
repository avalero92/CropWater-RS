"""CDSE public STAC catalogue: bounded, paginated Sentinel-2 L2A date discovery."""
import traceback
from datetime import date
from PySide6.QtCore import QThread, Signal

STAC_SEARCH = 'https://stac.dataspace.copernicus.eu/v1/search'

def distinct_dates(items):
    dates=set()
    for item in items:
        stamp=item.get('properties',{}).get('datetime') or item.get('properties',{}).get('start_datetime')
        if stamp:
            dates.add(date.fromisoformat(stamp[:10]).isoformat())
    return sorted(dates,reverse=True)

def query_dates(geometry, start, end, session=None, max_pages=25):
    """Search CDSE STAC in EPSG:4326. Raises on HTTP, JSON, timeout or pagination errors."""
    import requests
    from shapely.ops import transform
    from pyproj import Transformer
    if date.fromisoformat(start)>date.fromisoformat(end):
        raise ValueError('Start date must precede end date.')
    wgs84=transform(Transformer.from_crs('EPSG:3857','EPSG:4326',always_xy=True).transform,geometry)
    if wgs84.is_empty or not wgs84.is_valid:
        raise ValueError('Parcel geometry is empty or invalid.')
    bbox=list(map(float,wgs84.bounds))
    if bbox[0]<-180 or bbox[2]>180 or bbox[1]<-90 or bbox[3]>90:
        raise ValueError('Parcel coordinates are outside longitude/latitude limits. Check CRS.')
    body={'collections':['sentinel-2-l2a'],'bbox':bbox,
          'datetime':f'{start}T00:00:00Z/{end}T23:59:59Z',
          'limit':100,'fields':{'include':['id','properties.datetime','properties.start_datetime']}}
    http=session or requests.Session()
    url=STAC_SEARCH
    method='POST'
    payload=body
    dates=set()
    seen=set()
    for page in range(max_pages):
        key=(method,url,str(payload))
        if key in seen:raise RuntimeError('CDSE returned a repeated pagination link.')
        seen.add(key)
        if method=='POST':resp=http.post(url,json=payload,timeout=(10,25))
        else:resp=http.get(url,timeout=(10,25))
        resp.raise_for_status()
        data=resp.json()
        if not isinstance(data,dict) or not isinstance(data.get('features'),list):
            raise ValueError('Unexpected CDSE STAC response (missing features).')
        dates.update(distinct_dates(data['features']))
        next_link=next((x for x in data.get('links',[]) if x.get('rel')=='next'),None)
        if not next_link:return sorted(dates,reverse=True)
        url=next_link['href']
        method=next_link.get('method','GET').upper()
        if method not in ('GET','POST'):raise ValueError('Unsupported CDSE pagination method.')
        payload=next_link.get('body',body) if method=='POST' else None
    raise RuntimeError(f'CDSE catalogue search exceeded {max_pages} pages. Narrow the date interval.')

class DateCatalogWorker(QThread):
    completed=Signal(list)
    failed=Signal(str)
    def __init__(self,geometry,client_id,client_secret,start,end):
        super().__init__()
        self.geometry=geometry;self.start_date=start;self.end_date=end
    def run(self):
        try:self.completed.emit(query_dates(self.geometry,self.start_date,self.end_date))
        except Exception as exc:
            self.failed.emit(traceback.format_exc())
