from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
def test_spatial_source_compiles():
    ast.parse((ROOT/'qt_spatial_view.py').read_text(encoding='utf-8'))
def test_qt_shell_connects_native_viewer():
    source=(ROOT/'cropwater_rs_qt.py').read_text(encoding='utf-8')
    assert 'from qt_spatial_view import SpatialViewer' in source
    assert 'self.spatial_viewer=SpatialViewer(parcel_store=self.parcel_store,cdse_provider=self._cdse_settings)' in source
def test_spatial_crs_and_ndvi_limits():
    source=(ROOT/'qt_spatial_view.py').read_text(encoding='utf-8')
    assert "to_crs(epsg=3857)" in source
    assert "vmin=-1,vmax=1" in source
    assert "src_nodata=src.nodata" in source
