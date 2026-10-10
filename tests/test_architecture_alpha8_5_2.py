from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / 'cropwater_rs.py').read_text(encoding='utf8')
PLOT = SOURCE.split('    def _plot_spatial_view(self, preserve_extent=True):', 1)[1].split('    def _on_spatial_click', 1)[0]
SCROLL = SOURCE.split('    def _on_spatial_scroll(self, event):', 1)[1].split('    def _on_spatial_mode_change', 1)[0]


def test_map_axes_persist_across_product_redraws():
    assert 'self.ax_spatial.clear()' in PLOT
    assert 'fig.clear()' not in PLOT
    assert 'fig.add_subplot(111)' not in PLOT


def test_map_viewport_has_fixed_figure_coordinates():
    assert 'self.ax_spatial.set_position([0.015, 0.045, 0.88, 0.885])' in PLOT
    assert 'fig.subplots_adjust(' not in PLOT


def test_raster_colorbar_has_separate_axes():
    assert 'fig.add_axes([0.925, 0.19, 0.014, 0.61])' in PLOT
    assert 'fig.colorbar(raster_artist, cax=colorbar_ax)' in PLOT


def test_zoom_only_updates_limits():
    assert 'set_xlim(' in SCROLL and 'set_ylim(' in SCROLL
    assert 'set_position(' not in SCROLL
