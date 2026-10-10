"""Offline checks of Process API raster validation and georeferencing."""
from pathlib import Path
import sys
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
pytest.importorskip("PySide6")
from qt_cdse_raster import RasterSettings, validate_raster_settings, raster_shape, write_masked_geotiff

def test_raster_bounds_and_limit():
    assert raster_shape((0,0,100,200),10)==(10,20)
    with pytest.raises(ValueError,match='too large'):
        raster_shape((0,0,100000,100000),10)

def test_raster_settings():
    s=RasterSettings('client','secret','2025-09-21','2025-09-22',10,'output.tif')
    validate_raster_settings(s)
    with pytest.raises(ValueError):
        validate_raster_settings(RasterSettings('client','secret','2025-09-23','2025-09-22',10,'output.tif'))

def test_raster_mask_geotiff(tmp_path):
    import rasterio
    from shapely.geometry import box
    arr=np.zeros((4,4,2),dtype=np.float32)
    arr[:,:,0]=0.55;arr[:,:,1]=1
    arr[0,0,1]=0
    output=tmp_path/'ndvi.tif'
    count=write_masked_geotiff(output,arr,(0,0,40,40),box(10,0,30,40),10)
    assert count==8
    with rasterio.open(output) as ds:
        assert ds.crs.to_epsg()==3857
        assert ds.nodata==-9999
        assert ds.bounds==(0,0,40,40)
        assert (ds.read(1)!=-9999).sum()==8
