# QUANT-based phenological partitioning

CropWater-RS v2.0.0 implements a parcel-wise adaptation of the QUANT transition framework of French et al. (2023), applied to reconstructed daily NDVI.

## Spectral transitions

For each analyzed seasonal curve, the algorithm identifies a seasonal NDVI peak and the pre-peak minimum used as the spectral baseline. The amplitude is the difference between the peak and baseline NDVI. Four amplitude-relative transitions are then determined by threshold crossings, with default percentages:

| Transition | Threshold | Limb | Boundary |
|---|---:|---|---|
| Q1 | 10% | Ascending | Initial / development |
| Q2 | 90% | Ascending | Development / mid-season |
| Q3 | 90% | Descending | Mid-season / late-season |
| Q4 | 50% | Descending | End of late-season |

Threshold crossing dates are linearly interpolated between neighboring daily observations. Missing or invalid crossings are reported rather than imputed. These dates are **spectral proxies**, not direct observations of physiological crop stages.

## Sowing date for phase-based water accounting

**The pre-peak NDVI minimum is a spectral cycle baseline, not necessarily the sowing date.** CropWater-RS offers three separate sowing-date sources for water-phase summaries:

1. A sowing date already present in an input parcel-vector attribute.
2. A manually assigned date, informed by field knowledge or a documented assumption.
3. A retrospective estimate from Q1: `sowing_date = Q1_date - offset_days`, using a user-defined crop-specific interval.

In the audited v2.0.0 Water Analysis implementation, the resolution priority when multiple sources exist is **manual override > vector attribute > Q1 offset**. The selected source should be retained in the outputs. A Q1-derived date is an assumed date, not an independently observed sowing date.

French et al. (2023) applied additional crop-calendar constraints to estimate planting date. CropWater-RS does not reproduce that planting-date procedure. Its reconstruction methods and transition-selection conventions also differ; the implementation should therefore be cited as **adapted from QUANT**, not identical to the complete original algorithm.

## Interpretation

The four transitions are used to partition the crop cycle into initial, development, mid-season, and late-season intervals for reporting. When sowing information is unavailable or invalid, phase-based water accounting cannot be completed for that parcel; daily water estimates can remain available independently.

## Reference

French, A. N., Sanchez, C. A., Wirth, T., Scott, A., Shields, J. W., Bautista, E., Saber, M. N., Wisniewski, E., & Gohardoust, M. R. (2023). Remote sensing of evapotranspiration for irrigated crops at Yuma, Arizona, USA. *Agricultural Water Management*, 290, 108582. https://doi.org/10.1016/j.agwat.2023.108582

For implementation-level details and limitations, see [`SCIENTIFIC_METHODOLOGY.md`](../SCIENTIFIC_METHODOLOGY.md), Sections 4 and 5.7.
