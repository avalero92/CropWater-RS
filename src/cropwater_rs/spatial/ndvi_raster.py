"""On-demand Sentinel-2 L2A NDVI visualization for one selected parcel.

Raster retrieval is separate from the Statistical API used for time-series results.
"""
import hashlib
from datetime import date, timedelta
import numpy as np

SCL_EXCLUDED = (0, 1, 3, 8, 9, 10, 11)

EVALSCRIPT = """//VERSION=3
function setup() { return {input:[{bands:["B04","B08","SCL","dataMask"]}],
 output:{bands:2,sampleType:"FLOAT32"}}; }
function evaluatePixel(s) {
 const valid = s.dataMask === 1 && ![0,1,3,8,9,10,11].includes(s.SCL);
 const den = s.B08+s.B04;
 return [valid && den !== 0 ? (s.B08-s.B04)/den : -9999, valid && den !== 0 ? 1 : 0];
}
"""

def make_cache_key(parcel_id, day, geometry):
    return (str(parcel_id), str(day), hashlib.sha256(geometry.wkb).hexdigest())

def mask_ndvi(data, geometry, extent):
    """Mask nodata/SCL and pixels outside polygon in projected coordinates."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds
    from shapely.geometry import mapping
    arr = np.asarray(data)
    if arr.ndim != 3 or arr.shape[2] != 2:
        raise ValueError("Expected HxWx2 NDVI and validity raster")
    h, w = arr.shape[:2]
    west, east, south, north = extent
    transform = from_bounds(west, south, east, north, w, h)
    inside = geometry_mask([mapping(geometry)], out_shape=(h,w), transform=transform, invert=True)
    ndvi = arr[:,:,0].astype(float)
    valid = (arr[:,:,1] > 0) & inside & np.isfinite(ndvi) & (ndvi >= -1) & (ndvi <= 1)
    return np.ma.array(ndvi, mask=~valid)

def fetch_parcel_ndvi(geometry_3857, day, config, resolution=10, max_pixels=1600000):
    """Fetch a single calendar-day mosaicked image; no temporal interpolation."""
    from sentinelhub import SentinelHubRequest, DataCollection, MimeType, BBox, CRS
    from sentinelhub import bbox_to_dimensions
    from rasterio.transform import from_bounds
    day = date.fromisoformat(str(day))
    bounds = geometry_3857.bounds
    pad = max(10, resolution)
    bbox = BBox((bounds[0]-pad,bounds[1]-pad,bounds[2]+pad,bounds[3]+pad), crs=CRS.POP_WEB)
    width, height = bbox_to_dimensions(bbox, resolution=resolution)
    if width * height > max_pixels:
        raise ValueError("Selected parcel raster exceeds pixel safety limit; choose a smaller parcel")
    # A collection's service_url controls the endpoint chosen by sentinelhub-py.
    # The default SENTINEL2_L2A points to services.sentinel-hub.com, not CDSE.
    # Match the collection routing already used by the Statistical API.
    base_url = str(config.sh_base_url).rstrip("/")
    if not base_url.startswith("https://sh.dataspace.copernicus.eu"):
        raise ValueError("NDVI raster requires the CDSE Sentinel Hub endpoint")
    from cropwater_rs.acquisition.cdse import get_cdse_l2a_collection
    cdse_collection = get_cdse_l2a_collection(DataCollection, base_url)
    request = SentinelHubRequest(
        evalscript=EVALSCRIPT,
        input_data=[SentinelHubRequest.input_data(data_collection=cdse_collection,
                                                  time_interval=(day.isoformat(),(day+timedelta(days=1)).isoformat()),
                                                  mosaicking_order="leastCC")],
        responses=[SentinelHubRequest.output_response("default",MimeType.TIFF)],
        bbox=bbox, size=(width,height), config=config,
    )
    arr = request.get_data()[0]
    extent = (bbox.min_x,bbox.max_x,bbox.min_y,bbox.max_y)
    return {"ndvi":mask_ndvi(arr, geometry_3857, extent), "extent":extent,
            "date":day.isoformat(), "resolution_m":resolution}


def raster_diagnostics(ndvi):
    """Report pixel availability, without confusing all-masked imagery with success."""
    values = np.ma.asarray(ndvi)
    total = int(values.size)
    valid = int(np.ma.count(values))
    return {"valid_pixels": valid, "total_pixels": total,
            "valid_pct": 100.0 * valid / total if total else 0.0}


def search_acquisition_dates(geometry_wgs84, start, end, config, max_items=300):
    """Find real S2 L2A acquisition dates in the CDSE catalog (not reconstruction dates)."""
    from sentinelhub import SentinelHubCatalog, DataCollection, BBox, CRS
    from cropwater_rs.acquisition.cdse import get_cdse_l2a_collection
    from datetime import date as _date, timedelta as _timedelta
    first, last = _date.fromisoformat(start), _date.fromisoformat(end)
    if last < first:
        raise ValueError("End date precedes start date")
    collection = get_cdse_l2a_collection(DataCollection, str(config.sh_base_url).rstrip("/"))
    catalog = SentinelHubCatalog(config=config)
    bbox = BBox(geometry_wgs84.bounds, crs=CRS.WGS84)
    results = catalog.search(collection=collection, bbox=bbox,
                             time=(first.isoformat(), (last + _timedelta(days=1)).isoformat()),
                             fields={"include": ["properties.datetime"], "exclude": []})
    found = set()
    for item in results:
        stamp = item.get("properties", {}).get("datetime", "")
        if stamp:
            found.add(stamp[:10])
        if len(found) >= max_items:
            break
    return sorted(found)
