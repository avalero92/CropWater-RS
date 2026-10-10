import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_catalog_and_spatial_modules_parse():
    for name in ('qt_cdse_dates.py','qt_spatial_view.py','cropwater_rs_qt.py'):
        ast.parse((ROOT/name).read_text(encoding='utf-8'))
def test_catalog_search_and_date_selector_wired():
    catalog=(ROOT/'qt_cdse_dates.py').read_text(encoding='utf-8')
    spatial=(ROOT/'qt_spatial_view.py').read_text(encoding='utf-8')
    assert 'https://stac.dataspace.copernicus.eu/v1/search' in catalog
    assert 'query_dates(self.geometry,self.start,self.end)' in catalog
    assert 'self.date_selector.currentIndexChanged.connect(self._date_changed)' in spatial
    assert 'self.parcel_selector.currentIndexChanged.connect(self._parcel_changed)' in spatial
    assert 'cache.mkdir(parents=True,exist_ok=True)' in spatial
