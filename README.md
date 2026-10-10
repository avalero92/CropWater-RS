# CropWater-RS

![](https://raw.githubusercontent.com/avalero92/CropWater-RS/main/assets/cropwater_rs_logo.png)

[![DOI: 10.5281/zenodo.23279404](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.23279404-blue)](https://doi.org/10.5281/zenodo.23279404)
[![GitHub Release](https://img.shields.io/github/v/release/avalero92/CropWater-RS?label=release)](https://github.com/avalero92/CropWater-RS/releases/tag/v2.0.0)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0--only-green)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D4)](https://github.com/avalero92/CropWater-RS/releases/tag/v2.0.0)

CropWater-RS is an open-source desktop application for parcel-level crop monitoring and irrigation-water analysis. Version 2.0.0 combines Sentinel-2 Level-2A imagery, NDVI quality control and daily temporal reconstruction, QUANT-based phenological transitions, crop-coefficient relationships, evapotranspiration and simplified net irrigation requirements in a graphical workflow.

## Main capabilities

- Import parcel polygons from supported vector formats (including SHP, GeoPackage and GeoJSON), with crop and parcel-identifier attributes.
- Retrieve parcel-level Sentinel-2 L2A NDVI statistics through the Copernicus Data Space Ecosystem (CDSE).
- Apply Sentinel-2 Scene Classification Layer (SCL) masking and observation-quality screening.
- Reconstruct daily NDVI trajectories using linear, Whittaker, Savitzky–Golay or Kalman approaches.
- Identify parcel-level Q1–Q4 spectral transitions using an adapted QUANT approach.
- Assign sowing dates from vector attributes, manual agronomic information or a user-defined retrospective offset from Q1.
- Apply built-in or user-defined NDVI–crop-coefficient relationships, subject to their original calibration domains.
- Calculate daily crop evapotranspiration and simplified net irrigation requirements from supplied meteorological data.
- Inspect parcel-level curves, water-analysis summaries and spatial outputs; save and reopen `.cwrs` projects and export analysis results.

## Scientific workflow

`Sentinel-2 L2A → SCL masking → parcel NDVI → quality control → daily reconstruction → crop coefficient → ETc → simplified net IWR`

QUANT-based spectral transitions provide an additional phenological partitioning step. **Sowing-date assignment is separate from QUANT** and may be based on a vector attribute, a manual date, or a retrospective Q1 offset.

## Installation and getting started

For **v2.0.0 on Windows**, download and run [CropWater-RS_2.0.0_Setup.exe](https://github.com/avalero92/CropWater-RS/releases/download/v2.0.0/CropWater-RS_2.0.0_Setup.exe) from the [official v2.0.0 GitHub Release](https://github.com/avalero92/CropWater-RS/releases/tag/v2.0.0). The release also provides a SHA-256 checksum file for integrity verification. See [installation instructions](docs/INSTALLATION.md) and the [user guide](USER_GUIDE.md). To run from source, use the PySide6 entry point `cropwater_rs_qt.py` and `requirements-qt.txt` as documented in the installation guide.

For data acquisition, users must supply their own CDSE credentials. **Never commit Client Secrets or credentials to the repository.**

## Input data

- Parcel polygons with a stable parcel identifier and optional crop and sowing-date attributes.
- User-supplied daily meteorological data, including `Date,ETo` for ETc; add `Pe` for simplified net IWR. Optional parcel-specific meteorology depends on the imported dataset and workflow.

Example:

```csv
Date,ETo,Pe
2026-01-01,1.9,0.0
2026-01-02,2.1,0.0
```

## Core calculations and interpretation

For a selected relationship, `Kc = a × NDVI + b` (with nonnegative clipping as implemented), `ETc = Kc × ETo`, and `IWRnet,d = max(ETc,d − Pe,d, 0)`.

The IWR calculation is a **simplified daily net requirement**, not a full soil-water balance or a gross irrigation allocation. Individual literature models may refer to Kc, basal Kcb or other reference definitions; their transferability must be evaluated before application.

## Scientific documentation

- [Scientific methodology, algorithms and reproducibility](SCIENTIFIC_METHODOLOGY.md) — authoritative methodological description for v2.0.0.
- [User guide](USER_GUIDE.md) — practical application workflow.
- [Installation](docs/INSTALLATION.md) — distribution and setup notes.
- [QUANT method](docs/QUANT_METHOD.md) and [Kc–NDVI library](docs/KC_NDVI_LIBRARY.md) — supplementary descriptions.

## Reproducibility and outputs

Retain the input parcel geometries, dates, meteorological inputs, selected NDVI reconstruction settings, QUANT thresholds, sowing-date provenance, coefficient model and exported results. The `.cwrs` project format supports saving and reopening application work; project files do not replace the original external datasets or source provenance.

## Citation

**Author:** Alexey Valero-Jorge — Centro de Investigación y Tecnología Agroalimentaria de Aragón (CITA), Aragón, Spain.

Cite **CropWater-RS v2.0.0** using the [CITATION.cff](CITATION.cff) metadata and its version-specific Zenodo DOI: [10.5281/zenodo.23279404](https://doi.org/10.5281/zenodo.23279404). Earlier releases have their own version-specific DOIs (for example, [v1.0.1: 10.5281/zenodo.22746413](https://doi.org/10.5281/zenodo.22746413)).

## License

GNU General Public License v3.0 only (`GPL-3.0-only`). See [LICENSE](LICENSE).

## Contact

- ORCID: [0000-0002-5993-7346](https://orcid.org/0000-0002-5993-7346)
- Email: avalero@cita-aragon.es
- Source repository: https://github.com/avalero92/CropWater-RS
