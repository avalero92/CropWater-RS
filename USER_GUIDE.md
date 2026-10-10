# CropWater-RS User Guide — v2.0.0

This guide describes the **v2.0.0 PySide6 application**. Consult [SCIENTIFIC_METHODOLOGY.md](SCIENTIFIC_METHODOLOGY.md) for scientific definitions, assumptions and limitations.

## 1. Install and launch

Install the validated Windows distribution from the matching v2.0.0 GitHub Release when published. See [docs/INSTALLATION.md](docs/INSTALLATION.md). Do not assume that the source-installation instructions for the legacy v1.x Tkinter application apply to v2.0.0.

## 2. Load parcel geometries

Import the parcel polygon dataset. Check its coordinate system and identify the parcel ID, crop attribute and, when available, the sowing-date attribute. Review any missing or ambiguous values before processing.

## 3. Configure CDSE access

Enter user-owned Copernicus Data Space Ecosystem credentials in the application and choose the acquisition period. Do not share Client Secrets or embed credentials in project archives or screenshots.

## 4. Retrieve and inspect NDVI

Run Sentinel-2 L2A parcel-level extraction. Inspect SCL masking and quality-control results; rejected observations and sparse acquisition periods can affect the reconstructed time series.

## 5. Reconstruct daily NDVI

Select a supported method: linear interpolation, Whittaker, Savitzky–Golay or Kalman. Inspect the resulting curve and record the selected settings. Reconstruction does not create independent field observations.

## 6. Analyze QUANT transitions

Run the adapted QUANT method to identify Q1–Q4 on the daily NDVI trajectory. Default amplitude thresholds are 10%, 90%, 90% and 50%. A pre-peak spectral minimum is a cycle baseline, **not an observed sowing date**.

## 7. Assign sowing date

The application supports three sources: (1) a date stored in the input vector attributes, (2) manual assignment based on agronomic knowledge or a defined assumption, or (3) `sowing date = Q1 date − user-defined offset in days`. The third approach requires a valid Q1 and is a CropWater-RS convention, not the planting-date procedure from French et al. (2023). If more than one source is available, the current implementation resolves them in this order: manual override, vector attribute, then Q1 offset.

## 8. Select a crop-coefficient relationship

Choose a compatible built-in or user-defined NDVI-based model. Inspect the coefficient type and original calibration domain; Kcb should not be assumed identical to Kc. See the [scientific methodology](SCIENTIFIC_METHODOLOGY.md).

## 9. Load meteorological inputs

Provide daily reference evapotranspiration (`ETo`, mm/day). Include effective precipitation (`Pe`, mm/day) for net IWR estimates. Validate date parsing, units, gaps and the intended parcel association.

## 10. Calculate water requirements

- `ETc = Kc × ETo`
- `IWRnet,d = max(ETc,d − Pe,d, 0)`

The net IWR estimate is simplified and excludes soil-water storage and irrigation efficiency. Review phase-based totals separately from whole-series cumulative columns.

## 11. Save projects and export

Save the session as a `.cwrs` project and export the relevant NDVI, QUANT, water-analysis and parcel-level results. Preserve the external input datasets and settings for reproducibility.

## 12. Troubleshooting

For unexpected results, check data availability, the SCL mask, QC thresholds, reconstructed NDVI, QUANT transition completeness, sowing-date provenance, meteorological coverage and model selection before interpreting ETc/IWR outputs.
