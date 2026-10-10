from pathlib import Path
SOURCE = (Path(__file__).resolve().parents[1] / 'cropwater_rs.py').read_text(encoding='utf8')

def test_map_frame_is_constant_and_aspect_is_in_geographic_limits():
    assert 'self.ax_spatial.set_aspect("auto")' in SOURCE
    assert 'def _spatial_match_viewport(self):' in SOURCE
    assert 'ax.set_xlim(x0-delta, x1+delta)' in SOURCE
    assert 'ax.set_ylim(y0-delta, y1+delta)' in SOURCE

def test_esri_tiles_refreshed_after_navigation():
    assert 'def _spatial_schedule_tiles(self):' in SOURCE
    assert 'def _spatial_refresh_tiles(self):' in SOURCE
    assert 'self._spatial_schedule_tiles()' in SOURCE
    assert 'old.remove()' in SOURCE

def test_tiles_do_not_reset_navigation_limits():
    method = SOURCE.split('    def _spatial_refresh_tiles(self):',1)[1].split('    def _fit_spatial_extent',1)[0]
    assert 'ax.set_xlim(*limits[0]); ax.set_ylim(*limits[1])' in method
