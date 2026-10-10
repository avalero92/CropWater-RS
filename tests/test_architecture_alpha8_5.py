from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / 'cropwater_rs.py').read_text(encoding='utf8')


def test_single_product_selector_includes_raster():
    assert 'self.spatial_product_combo = ttk.Combobox(' in SOURCE
    assert '"Sentinel-2 NDVI"],' in SOURCE
    assert 'self.spatial_metric_combo.grid_remove()' in SOURCE


def test_date_change_auto_loads_raster():
    section = SOURCE.split('    def _on_spatial_date_change(self):', 1)[1].split('    def _auto_refresh_spatial_raster', 1)[0]
    assert 'self._load_selected_ndvi_raster()' in section


def test_parcel_selection_refreshes_raster():
    section = SOURCE.split('    def _on_parcel_selected(self, _event=None):', 1)[1].split('    def ', 1)[0]
    assert 'self._auto_refresh_spatial_raster()' in section


def test_advanced_options_collapsible():
    assert 'self.spatial_advanced_widgets' in SOURCE
    assert 'widget.grid() if visible else widget.grid_remove()' in SOURCE


def test_spatial_layout_no_tight_layout():
    section = SOURCE.split('    def _plot_spatial_view(self, preserve_extent=True):', 1)[1].split('    def _on_spatial_click', 1)[0]
    assert 'self.ax_spatial.set_position(' in section
    assert 'fig.tight_layout()' not in section
