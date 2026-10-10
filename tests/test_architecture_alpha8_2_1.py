"""Regression: Process API must route to CDSE, not the commercial endpoint."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
import numpy as np
from shapely.geometry import box
from cropwater_rs.spatial.ndvi_raster import fetch_parcel_ndvi


def test_process_api_uses_cdse_collection(monkeypatch):
    collection = MagicMock()
    collection.define_from.return_value = "CDSE_L2A"
    request_class = MagicMock()
    request_class.input_data.return_value = "input"
    request_class.output_response.return_value = "response"
    request_class.return_value.get_data.return_value = [np.zeros((3, 3, 2))]
    bbox_class = MagicMock()
    bbox_class.return_value = SimpleNamespace(min_x=0, max_x=30, min_y=0, max_y=30)
    fake = SimpleNamespace(SentinelHubRequest=request_class,
        DataCollection=SimpleNamespace(SENTINEL2_L2A=collection),
        MimeType=SimpleNamespace(TIFF="TIFF"), BBox=bbox_class,
        CRS=SimpleNamespace(POP_WEB="POP_WEB"), bbox_to_dimensions=lambda *a, **k:(3,3))
    monkeypatch.setitem(sys.modules, "sentinelhub", fake)
    config = SimpleNamespace(sh_base_url="https://sh.dataspace.copernicus.eu")
    fetch_parcel_ndvi(box(0,0,30,30), "2026-09-18", config)
    collection.define_from.assert_called_once_with(name="s2l2a_cdse", service_url=config.sh_base_url)
    assert request_class.input_data.call_args.kwargs["data_collection"] == "CDSE_L2A"
    assert request_class.call_args.kwargs["config"] is config


def test_process_api_reuses_existing_cdse_collection(monkeypatch):
    existing = object()
    collection = MagicMock()
    request_class = MagicMock()
    request_class.return_value.get_data.return_value = [np.zeros((3, 3, 2))]
    bbox_class = MagicMock()
    bbox_class.return_value = SimpleNamespace(min_x=0, max_x=30, min_y=0, max_y=30)
    fake = SimpleNamespace(SentinelHubRequest=request_class,
        DataCollection=SimpleNamespace(SENTINEL2_L2A=collection, s2l2a_cdse=existing),
        MimeType=SimpleNamespace(TIFF="TIFF"), BBox=bbox_class,
        CRS=SimpleNamespace(POP_WEB="POP_WEB"), bbox_to_dimensions=lambda *a, **k:(3,3))
    monkeypatch.setitem(sys.modules, "sentinelhub", fake)
    config = SimpleNamespace(sh_base_url="https://sh.dataspace.copernicus.eu")
    fetch_parcel_ndvi(box(0,0,30,30), "2026-09-18", config)
    collection.define_from.assert_not_called()
    assert request_class.input_data.call_args.kwargs["data_collection"] is existing
