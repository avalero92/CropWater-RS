# Changelog

## [1.0.1] - 2026-09-14

### Fixed
- Fixed Matplotlib colormap compatibility with recent Matplotlib versions.
- Improved Savitzky-Golay temporal reconstruction robustness and output validation.
- Improved meteorological CSV parsing for ISO (`YYYY-MM-DD`) and European (`DD/MM/YYYY`) date formats.
- Improved compatibility with comma- and semicolon-separated meteorological files.

## [1.0.0] — 2026-09-11

First stable public release.

### Included
- Manual and attribute-based crop labelling.
- Batch parcel workflows.
- CDSE Sentinel-2 L2A parcel NDVI retrieval.
- Linear, Whittaker, Savitzky-Golay and Kalman temporal processing.
- Direct Kc–NDVI library and custom model manager.
- ETc/CWR and simplified net IWR.
- Parcel-wise QUANT phenology.
- QUANT phase water summaries.
- Spatial parcel results.
- Previous/Next parcel navigation.
- CSV, metadata and GeoPackage exports.
- Persistent logging.
- Official CropWater-RS visual identity.
