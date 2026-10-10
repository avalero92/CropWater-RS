from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "cropwater_rs.py").read_text(encoding="utf-8")


def test_fixed_spatial_axes_footprint():
    assert 'self.ax_spatial.set_aspect("auto")' in SOURCE
    assert 'self._spatial_match_viewport()' in SOURCE
    assert 'self.ax_spatial.set_aspect("equal", adjustable="box")' not in SOURCE


def test_zoom_out_guard():
    assert 'if factor > 1 and self.gdf is not None and not self.gdf.empty:' in SOURCE
    assert '>= 8:' in SOURCE
