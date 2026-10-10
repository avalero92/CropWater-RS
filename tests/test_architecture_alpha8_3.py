import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cropwater_rs.spatial.ndvi_raster import raster_diagnostics, make_cache_key

def test_all_masked_raster_is_detected():
    x = np.ma.masked_all((4, 5))
    assert raster_diagnostics(x) == {'valid_pixels': 0, 'total_pixels': 20, 'valid_pct': 0.0}

def test_partial_masked_raster_counts_only_valid_pixels():
    x = np.ma.array([[0.2, 0.4], [0.1, 0.5]], mask=[[False, True], [True, False]])
    assert raster_diagnostics(x)['valid_pct'] == 50.0

def test_catalog_and_raster_are_independent_of_reconstruction():
    code = (Path(__file__).resolve().parents[1] / 'cropwater_rs.py').read_text(encoding='utf8')
    assert 'def _search_spatial_acquisitions(self)' in code
    assert 'search_acquisition_dates(geom, start.isoformat(), end.isoformat(), config)' in code
    assert 'self.spatial_date_combo.configure(state="normal")' in code
