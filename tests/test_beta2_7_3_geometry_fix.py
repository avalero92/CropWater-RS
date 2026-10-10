"""Regression: Shapely geometries do not expose .copy()."""
import pytest
from shapely.geometry import Polygon, MultiPolygon
from qt_cdse_raster import RasterWorker, RasterSettings

@pytest.mark.parametrize('geometry', [
    Polygon([(0,0),(10,0),(10,10),(0,10)]),
    MultiPolygon([Polygon([(0,0),(10,0),(10,10),(0,10)])]),
])
def test_raster_worker_accepts_shapely_geometry(geometry, tmp_path):
    settings=RasterSettings('id','secret','2023-01-01','2023-01-02',10,str(tmp_path/'ndvi.tif'))
    worker=RasterWorker(geometry,settings)
    assert worker.parcel is geometry
    assert callable(worker.start)
