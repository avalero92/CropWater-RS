from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "cropwater_rs.py").read_text(encoding="utf-8")


def test_exclusive_spatial_modes():
    assert 'values=["Parcel statistics", "Sentinel-2 NDVI"]' in SOURCE
    assert 'if raster_mode:' in SOURCE
    assert 'Never paint thematic parcel fills' in SOURCE


def test_raster_has_independent_continuous_colorbar():
    assert 'fig.colorbar(raster_artist' in SOURCE
    assert 'cb.set_label("Sentinel-2 NDVI (pixel)"' in SOURCE
    assert 'vmin=-1, vmax=1' in SOURCE


def test_only_esri_basemap_available():
    assert 'values=["None", "Satellite (Esri)"]' in SOURCE
