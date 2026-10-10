import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cropwater_rs.spatial.ndvi_raster import make_cache_key, mask_ndvi, EVALSCRIPT
from shapely.geometry import box

def test_cache_key_date_and_geometry():
    a = box(0, 0, 20, 20)
    assert make_cache_key("p", "2024-06-01", a) != make_cache_key("p", "2024-06-02", a)
    assert make_cache_key("p", "2024-06-01", a) != make_cache_key("p", "2024-06-01", box(0, 0, 30, 30))

def test_mask_nodata_and_polygon():
    raster = np.zeros((4, 4, 2), dtype="float32")
    raster[:, :, 0] = 0.6
    raster[:, :, 1] = 1
    raster[0, 0, 1] = 0
    result = mask_ndvi(raster, box(0, 0, 2, 4), (0, 4, 0, 4))
    assert result.mask[0, 0]
    assert result.mask[0, 3]
    assert result[1, 1] == pytest.approx(0.6)

def test_invalid_shapes():
    with pytest.raises(ValueError):
        mask_ndvi(np.zeros((2, 2)), box(0, 0, 1, 1), (0, 2, 0, 2))

def test_scl_matches_statistical_mask():
    for code in (0, 1, 3, 8, 9, 10, 11):
        assert str(code) in EVALSCRIPT
