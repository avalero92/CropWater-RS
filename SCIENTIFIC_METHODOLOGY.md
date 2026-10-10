# CropWater-RS v2.0.0 — Scientific Methodology, Algorithms and Reproducibility

**Author:** Alexey Valero-Jorge  
**Affiliation:** Centro de Investigación y Tecnología Agroalimentaria de Aragón (CITA), Aragón, Spain  
**Version:** 2.0.0  
**Scope:** Sentinel-2 L2A acquisition, SCL masking, parcel NDVI, observation QC, daily reconstruction, QUANT phenology, crop coefficients, ETc and simplified net irrigation requirements.

## 1. Scope and processing chain

CropWater-RS is a parcel-oriented workflow. Sentinel-2 L2A data are retrieved through CDSE; SCL and data-availability masks precede NDVI aggregation; accepted parcel NDVI P50 observations are reconstructed to a daily series; QUANT identifies spectral transitions; and a selected Kc–NDVI relationship together with user-supplied daily ETo and effective precipitation produces daily ETc and simplified net irrigation requirements. Single-date raster visualization is a distinct pathway and is not required to compute the parcel time series.

**Interpretation:** NDVI-derived dates are spectral proxies rather than observed crop stages; the QUANT pre-peak minimum is not a measured sowing date; reconstruction diagnostics are in-sample; and the daily net IWR equation is not a soil-water balance or gross irrigation demand.

## 2. Sentinel-2 acquisition, masking and parcel NDVI

### 2.1 Data source and parcel geometry
CropWater-RS retrieves Sentinel-2 Level-2A imagery through the Copernicus Data Space Ecosystem (CDSE) Sentinel Hub services. The time-series workflow uses the Statistical API, while single-date raster inspection and optional GeoTIFF export use the Process API. The software converts parcel geometries to WGS84 for statistical requests. Raster requests operate on projected parcel bounds in EPSG:3857 and subsequently mask the returned image to the parcel polygon.

### 2.2 Bands and spectral index
The evalscripts request B04 (red), B08 (near infrared), the Scene Classification Layer (SCL), and `dataMask`. The index is computed for valid pixels as:

\[ NDVI = \frac{B08 - B04}{B08 + B04}. \]

For the statistical workflow, a zero denominator produces `NaN`. For raster export, the denominator must be positive; invalid pixels are written as `-9999` (GeoTIFF nodata). The retrieved spectral values are supplied by the Sentinel Hub service; this implementation does not perform an additional explicit radiometric scaling step in Python.

### 2.3 SCL and data-availability masking
The following SCL classes are excluded by the code: **0** (no data), **1** (saturated/defective), **3** (cloud shadows), **8** (medium-probability clouds), **9** (high-probability clouds), **10** (thin cirrus), and **11** (snow/ice). Pixels must additionally satisfy `dataMask == 1`.

The code does **not** explicitly exclude SCL **2** (topographic cast shadows / dark-area pixels), **7** (unclassified), or **6** (water). Therefore, the mask should not be described as excluding all shadows, all unclassified pixels, or all nonvegetated pixels. No additional cloud-buffer dilation is visible in the inspected evalscripts.

### 2.4 Parcel-level statistical time series
The Statistical API uses an aggregation resolution of **10 m × 10 m**, with the `leastCC` mosaicking order. Supported aggregation intervals are `P1D`, `P5D`, `P10D`, and `P1M`. Returned fields include interval start/end, NDVI mean, standard deviation, minimum, maximum, 25th/50th/75th percentiles, `sampleCount`, and `noDataCount`. The software computes:

\[ Valid\ fraction\ (\%) = 100\,\frac{sampleCount-noDataCount}{sampleCount}, \]

when `sampleCount > 0`. The downstream preprocessing module uses **NDVI P50**, rather than mean NDVI, as its required observation variable.

**Interpretation note:** `leastCC` is a scene/mosaic selection policy; it does not guarantee cloud-free observations. Aggregated interval statistics are not equivalent to a raw observation for every calendar day.

### 2.5 Single-date visualization and GeoTIFF
The Process API is distinct from the parcel statistical time-series pipeline. On-demand visualization retrieves a one-day mosaicked NDVI image and masks invalid pixels and pixels outside the polygon. The GeoTIFF export worker allows output pixel sizes of **10, 20, or 30 m**, uses EPSG:3857, `float32`, nodata `-9999`, and DEFLATE compression. These exported rasters are not required for the Statistical API time-series calculations.

### 2.6 Source-code traceability
| Scientific operation | Implementation |
|---|---|
| Statistical evalscript and SCL mask | `qt_cdse_acquisition.py` → `NDVI_EVALSCRIPT` |
| CDSE Statistical API request and 10 m resolution | `src/cropwater_rs/acquisition/cdse.py` → `build_statistical_request` |
| Decode parcel statistics and valid fraction | `src/cropwater_rs/acquisition/cdse.py` → `stats_response_to_df` |
| Raster evalscript and GeoTIFF masking | `qt_cdse_raster.py` → `EVALSCRIPT`, `write_masked_geotiff` |
| On-demand raster visualization | `src/cropwater_rs/spatial/ndvi_raster.py` → `fetch_parcel_ndvi`, `mask_ndvi` |
| QC input variable and acceptance checks | `qt_preprocessing_core.py` |

## 3. Observation quality control and daily NDVI reconstruction

### 3.1 Quality control of parcel-level NDVI observations

The preprocessing module evaluates parcel-level observations derived from the Sentinel-2 Statistical API. The minimum required fields are `parcel_id`, `date_start`, and `ndvi_p50`. Dates are parsed as UTC, NDVI is converted to numeric values, and parcel identifiers are normalized as strings with surrounding whitespace removed. The original input data are preserved; the quality-control routine returns an annotated copy.

An observation is accepted only when all applicable checks pass:

1. A nonempty parcel identifier and a valid acquisition date are present.
2. The parcel median NDVI (`ndvi_p50`) is finite and within the physical index range [-1, 1].
3. If `valid_fraction_pct` is available, it must lie between the configured minimum and 100%. The default minimum is **50%**.
4. If `sample_count` is available, it must be at least the configured minimum, **one sample** by default.
5. The record is not a duplicate of an earlier record for the same parcel and UTC calendar date.

If either optional quality field (`valid_fraction_pct` or `sample_count`) is absent, its respective criterion is treated as passed rather than estimated. A missing value in a *present* field fails its check. The valid-fraction threshold is inclusive, as is the minimum sample count. Duplicates are marked using first-occurrence retention (`duplicated(keep="first")`); the code does not preferentially retain the highest-quality observation. No separate temporal outlier detection (e.g., Hampel filter or sigma clipping) is implemented in this QC function.

Each observation receives an `accepted` Boolean and a semicolon-delimited `qc_reason`, potentially combining `missing_parcel`, `invalid_date`, `invalid_ndvi`, `low_valid_fraction`, `insufficient_samples`, and `duplicate_date`. The parcel summary reports total, accepted, and rejected observation counts. Changing QC parameters invalidates previously calculated QC and reconstruction results in the user interface.

**Interpretation:** The 50% default is an operational acceptance threshold, not a scientifically optimized threshold established by this code. Its appropriateness depends on parcel size, image availability, seasonal cloudiness, and the application.

### 3.2 Temporal domain and reconstruction prerequisites

For each parcel, only QC-accepted observations with finite `ndvi_p50` values enter the reconstruction. At least two accepted observations with valid dates are required. Acquisition timestamps are converted to UTC calendar days and normalized to midnight, avoiding mismatches between timezone-aware acquisition timestamps and timezone-naive daily grids. If multiple accepted observations remain on one calendar day, the numerical core takes their median; under the standard QC workflow, later duplicate records have already been rejected.

The reconstruction interval is inclusive, from the **first accepted observation date** to the **last accepted observation date**. Thus, the standard PySide6 workflow does not independently extrapolate the series to sowing, harvest, or user-defined campaign boundaries. A complete daily index is constructed at one-day spacing. Missing acquisition days are represented as missing (`NaN`) observations until reconstructed. The maximum interval between successive accepted observations is recorded as `longest_gap_days` for diagnostic purposes; the code does not impose a maximum-gap rejection threshold.

### 3.3 Daily NDVI reconstruction methods

Let `y_t` denote the observed parcel NDVI P50 on day `t`, with missing values on dates without accepted observations, and let `z_t` denote the reconstructed daily NDVI. Four methods are exposed in the v2.0.0 PySide6 interface.

#### Linear interpolation

A daily baseline is generated using pandas time-based interpolation between observed dates. Endpoint propagation (`limit_direction="both"`) is enabled in the numerical core. In the standard application workflow the output period starts and ends at accepted observations, so extrapolation outside that interval is not ordinarily involved. Linear interpolation is also used as the complete input baseline for Savitzky–Golay filtering.

#### Whittaker smoothing

Whittaker reconstruction minimizes a weighted data-fidelity term and a second-difference roughness penalty:

\[
\hat{\mathbf z}=\arg\min_{\mathbf z}\left[\sum_t w_t(y_t-z_t)^2+\lambda\sum_t(\Delta^2 z_t)^2\right],
\]

where `w_t = 1` on observed days and `0` on missing days, and `λ` controls smoothness. The implementation solves the sparse linear system

\[
(\mathbf W+\lambda\mathbf D^\mathsf T\mathbf D)\hat{\mathbf z}=\mathbf W\mathbf y_0,
\]

with a second-order difference operator `D`, sparse matrices, and SciPy `spsolve`. The interface defaults to **λ = 100**, adjustable from **0.01 to 10,000,000**. Higher λ values impose stronger smoothness. The method is not described as asymmetric Whittaker or as incorporating robust iterative outlier weights, because neither mechanism is implemented here.

#### Savitzky–Golay filtering

A Savitzky–Golay polynomial filter is applied **after** linearly interpolating the accepted observations to daily resolution. The default window is **21 days**, with a fixed polynomial order of **2**. Even window inputs are increased to the next odd integer, and the effective window is capped at the largest odd integer not exceeding the daily series length. The series must contain at least five days. The SciPy call uses `mode="nearest"` at the boundaries; it does not use the default edge polynomial interpolation. The interface allows window lengths from 5 to 365 days, although the numerical core may reduce the effective window for short series.

This is a smoothing operation on a preinterpolated daily baseline, **not** a missing-data-aware Savitzky–Golay fit directly to irregular observation dates.

#### Kalman filtering and smoothing

The Kalman option implements a scalar local-level state-space model with a forward filter followed by a Rauch–Tung–Striebel (RTS) backward smoother. In conceptual form,

\[
x_t=x_{t-1}+\eta_t,\qquad y_t=x_t+\epsilon_t,
\]

with process noise variance `q` and observation noise variance `r`. Missing observations skip the measurement update, while state prediction continues. The implementation derives `r = max(0.05 Var(y_obs), 10^{-5})`, using a fallback variance of 0.01 if the observed variance is too small or nonfinite. It derives `q = max(0.05 Var(diff(y_obs)), 10^{-6})` when successive observed differences exist (otherwise a fallback based on the scale). These are code-defined heuristic variance estimates, not user-calibrated or maximum-likelihood-fitted noise parameters. The initial state is the first observed NDVI, with initial state variance 1.

### 3.4 Postprocessing and diagnostic indicators

The interface provides a **Constrain NDVI [0,1]** option, enabled by default. When selected, reconstructed values are clipped to [0,1] **after** reconstruction. This differs from the QC rule, which accepts original NDVI observations in [-1,1]. The clipping is an application-level restriction and may alter the fitted signal, especially over water, bare soil, or other low-NDVI surfaces. Disabling it retains the unbounded reconstructed output of the selected method.

The daily output includes `date`, `ndvi_observed`, and `ndvi_reconstructed_daily`, together with `parcel_id` in the PySide6 adapter. Diagnostics at observed dates are computed as:

\[
RMSE=\sqrt{n^{-1}\sum_i(y_i-\hat y_i)^2},\qquad MAE=n^{-1}\sum_i|y_i-\hat y_i|,
\]

\[
R^2=1-\frac{\sum_i(y_i-\hat y_i)^2}{\sum_i(y_i-\bar y)^2},
\]

where `R²` is undefined if fewer than two matched observations exist or observed variance is zero. The diagnostics also include `n_accepted` and `longest_gap_days`. **These are in-sample reconstruction diagnostics, not independent cross-validation or external accuracy assessments.** In particular, linear interpolation generally passes through the accepted observation values, so an in-sample RMSE near zero should not be interpreted as superior predictive skill.

The export action writes the reconstructed daily CSV and a companion `.parameters.json` file containing the selected method, applicable λ or Savitzky–Golay window, clipping setting, and QC thresholds. A failure affecting one parcel is reported; successfully reconstructed parcels can still be returned and transferred to the QUANT module. Changing reconstruction parameters invalidates the previous reconstruction until rerun.

### 3.5 Limitations and recommended reporting

For reproducibility, users should report the source imagery and date range, the NDVI statistic (P50), QC thresholds, the number of accepted observations, the longest observation gap, reconstruction method and parameters, whether NDVI clipping was applied, and the number of failed parcels. Scientific applications should independently evaluate sensitivity to observation gaps, smoothing strength, and clipping. The current preprocessing code does not implement a dedicated phenology-aware gap limit, explicit temporal spike removal, uncertainty envelopes, or external reconstruction validation.

### 3.6 Source-code traceability

| Operation | Source file and function |
|---|---|
| Observation QC and reason flags | `qt_preprocessing_core.py` → `quality_control` |
| QC and reconstruction parameter defaults | `qt_preprocessing_page.py` → UI initialization |
| Per-parcel reconstruction and daily date bounds | `qt_reconstruction_core.py` → `reconstruct_qc` |
| Linear, Whittaker, Savitzky–Golay and Kalman implementations | `src/cropwater_rs/core/temporal.py` → `process_one_temporal_series` |
| Kalman forward filter and RTS smoother | `src/cropwater_rs/core/temporal.py` → `_kalman_smooth_local_level` |
| In-sample RMSE, MAE and R² | `src/cropwater_rs/core/temporal.py` → `_temporal_diagnostics` |
| Export of CSV and parameter metadata | `qt_preprocessing_page.py` → `export_reconstructed` |

## 4. QUANT phenological analysis

### 4.1 Inputs and analysis scope

The QUANT module accepts reconstructed daily NDVI with columns `parcel_id`, `date`, and `ndvi_reconstructed_daily`, either transferred from the preprocessing workflow or imported as CSV. Records with missing parcel identifiers, dates, or NDVI values are removed before analysis. Users may analyze all parcels or a selected subset. For each parcel, the analysis window can comprise the full reconstructed series, a manually assigned start date (calendar date or day of year with reference year), or a start date read from a vector attribute. Start-date filtering retains dates on or after the selected date. The user interface records the applied start date, its source, and the number of analyzed daily records.

**Interpretation:** the analysis-window start is not necessarily a sowing date; it is distinct from the NDVI-derived cycle start defined below.

### 4.2 Data preparation and season identification

Within `calculate_quant_one`, dates and NDVI values are converted to appropriate types, missing records are removed, duplicate dates are dropped (the first occurrence is retained), and observations are sorted chronologically. Fewer than five remaining daily records triggers an error.

The seasonal peak is the global maximum of the analyzed series, at index `peak_pos`. The peak must have at least two records before it and two after it. The seasonal baseline is the **minimum NDVI occurring at or before the peak**, not necessarily the first observation or a measured planting date. Define

\[
NDVI_{min}=\min_{t\le t_{peak}}NDVI(t),\qquad NDVI_{max}=NDVI(t_{peak}),
\]
\[
A=NDVI_{max}-NDVI_{min}.
\]

A non-finite amplitude or an amplitude `A <= 0.05` raises an error. This is an NDVI-unit threshold, not a percentage. A single global maximum and its preceding minimum are used; no automatic multi-cycle segmentation is implemented in this core.

### 4.3 Amplitude-based thresholds

The default percentage thresholds are Q1 = 10, Q2 = 90, Q3 = 90 and Q4 = 50. For each transition `Qi`, the corresponding absolute NDVI threshold is

\[
T_{Qi}=NDVI_{min}+\frac{q_i}{100}A.
\]

All percentages must lie strictly between 0 and 100; additionally `Q1 < Q2` and `Q4 < Q3`. The UI permits increments of 0.1 percentage point between 0.1% and 99.9%, subject to these relational constraints. The rising limb extends from the pre-peak minimum through the peak; the falling limb extends from the peak to the last analyzed date.

| Transition | Default threshold | Limb | Interpretation in the software |
|---|---:|---|---|
| Q1 | 10% | Rising | INI → DEV |
| Q2 | 90% | Rising | DEV → MID |
| Q3 | 90% | Falling | MID → END |
| Q4 | 50% | Falling | End of remotely sensed cycle / END termination |

These are spectral amplitude crossings and should not be presented as direct field observations of FAO-56 stage boundaries.

### 4.4 Crossing detection and date interpolation

The algorithm searches successive valid daily values `(y0, y1)`. Rising crossings require `y0 <= T <= y1` and `y1 > y0`; falling crossings require `y0 >= T >= y1` and `y1 < y0`. For an eligible pair with timestamps `t0`, `t1`, the crossing date is linearly interpolated:

\[
f=\frac{T-y_0}{y_1-y_0},\qquad t_Q=t_0+f(t_1-t_0).
\]

If more than one crossing occurs, **the first rising crossing** is selected for Q1/Q2 and **the last falling crossing** for Q3/Q4. This choice matters if residual NDVI oscillations remain. If no eligible crossing exists, the transition is missing (`NaT`). Interpolated timestamps may contain fractions of a day; day-of-year outputs refer to the calendar day containing the timestamp.

### 4.5 Phase durations and completeness

The NDVI-derived cycle start is the date of the pre-peak minimum, `t_min`. For four detected transitions, the implementation calculates durations in decimal days:

\[
D_{INI}=t_{Q1}-t_{min},\quad D_{DEV}=t_{Q2}-t_{Q1},
\]
\[
D_{MID}=t_{Q3}-t_{Q2},\quad D_{END}=t_{Q4}-t_{Q3},
\]
\[
D_{total}=t_{Q4}-t_{min}.
\]

A parcel is `Complete` when all four crossings exist and no calculated duration is negative; otherwise it is `Incomplete`, with duration fields set to missing values for absent transitions (or retained values when a negative-duration check fails, depending on the executed path). Structural and amplitude failures raise exceptions that the graphical layer records as `Error` with an explanatory message. An incomplete parcel must not be treated as a complete four-stage cycle.

**Important distinction:** the QUANT `cycle_start_date` is the NDVI minimum, whereas phase-based Water Analysis may obtain a **separate sowing date** from manual entry, a vector attribute, or a crop-specific Q1 offset. Those water-accounting conventions require their own methodological section.

### 4.6 Output and provenance

Per-parcel outputs include `parcel_id`, `crop` (blank when the core receives no parcel geometry metadata), status, cycle start and peak dates/DOY, NDVI minimum, maximum and amplitude, the four percentages, four absolute NDVI thresholds, Q1–Q4 dates/DOY, and INI/DEV/MID/END/total durations. The graphical layer adds `analysis_start_date`, `analysis_start_DOY`, `start_source`, and `n_days_analyzed`. Results can be exported as CSV. Dates, thresholds, reconstruction settings, and parcel selection should be retained for reproducibility.

### 4.7 Scientific limitations and interpretation

1. The implementation detects one dominant peak in the selected interval; double cropping or multiple vegetation cycles require carefully chosen temporal windows and parcel-specific interpretation.
2. Results are conditional on the reconstruction method, data coverage, quality control and temporal window. The reconstructed series is not an independent ground-truth record.
3. NDVI amplitude thresholds are **spectral proxies**, not field-validated crop-stage observations; comparisons with agronomic calendars or field phenology are required for accuracy claims.
4. The pre-peak minimum may represent bare soil, residue, weeds, an earlier crop or other conditions, rather than sowing.
5. The first-rising/last-falling rule can be sensitive to residual oscillations; smoothness and boundary conditions warrant diagnostic inspection.
6. The `A > 0.05` criterion excludes low-amplitude series but is not itself a formal quality guarantee.
7. No planting-date constraint is imposed by the scientific QUANT core; optional user-supplied start dates limit the analyzed window but do not redefine the baseline as sowing.

### 4.8 Source-code traceability

| Operation | Source file | Function / location |
|---|---|---|
| Threshold validation | `src/cropwater_rs/core/quant.py` | `validate_quant_thresholds` |
| Crossing and interpolation | `src/cropwater_rs/core/quant.py` | `quant_crossing_date` |
| Peak, baseline, amplitude, phases, outputs | `src/cropwater_rs/core/quant.py` | `calculate_quant_one` |
| Parcel selection, user thresholds, start modes, export | `qt_quant_page.py` | `QuantPage` / `run_quant` |
| Start-date conversion and series truncation | `qt_quant_scope.py` | `resolve_start`, `filter_daily` |
| Separate water-phase boundaries | `qt_water_phase_core.py` | `summarize_water` |

### 4.9 Relationship to the original QUANT method

The QUANT-based transition framework follows French et al. (2023), *Agricultural Water Management*, 290, 108582, DOI: https://doi.org/10.1016/j.agwat.2023.108582. The original publication defines a single-season threshold scheme using 10% on the ascending limb, 90% on both ascending and descending limbs, and 50% on the descending limb (Section 2.5, Table 6 and Fig. 4). These thresholds correspond to the application defaults. However, French et al. also constrain the day-of-planting estimate using crop-specific reference initial-stage durations and a ±10-day tolerance; CropWater-RS does **not** reproduce that sowing-date rule. Its QUANT core uses the pre-peak NDVI minimum as a spectral cycle-start proxy, and sowing is independently assigned in Water Analysis (Section 5.7). Furthermore, the application uses its own temporal reconstruction options and crossing-selection conventions, so it is correctly described as an **adapted QUANT implementation**, not a complete replication of French et al. (2023). The separate multiple-cutting alfalfa procedure described in Table 7 and Fig. 5 of the source publication is not implemented as automatic multi-cycle segmentation by this QUANT core.

---

## 5. Crop coefficients, evapotranspiration and irrigation requirements

### 5.1 Inputs and temporal alignment

The Water Analysis module receives parcel-level, daily reconstructed NDVI (`ndvi_reconstructed_daily`) and a daily meteorological CSV containing `date`, `eto_mm` (reference evapotranspiration, mm d⁻¹) and `pe_mm` (effective precipitation, mm d⁻¹). An optional `parcel_id` supports parcel-specific weather; otherwise meteorology is joined by date across parcels. Dates are normalized to calendar days. Numeric meteorological inputs must be finite and nonnegative, and date or parcel-date keys must be unique. The merge must cover **every NDVI parcel-day**; missing weather causes a calculation error. The software does not calculate ETo or effective precipitation from raw meteorological observations: these are supplied by the user.

**Source:** `qt_water_page.py`, `set_weather`, `calculate`.

### 5.2 Crop-specific Kc–NDVI relationships

For each parcel and day, a selected linear relationship is applied:

\[K_{c,t}=\max\left(0,a\,NDVI_t+b\right).\]

Here, `a` and `b` are the selected formulation coefficients. Negative Kc values are clipped to zero by default; no upper Kc cap is imposed by this function. The application requires validation of both crop assignment and Kc–NDVI formulation before calculating results. Formulations are selected from a built-in crop library or user-defined entries. The built-in library is immutable through the user library interface; custom entries are stored separately under `%APPDATA%/CropWater-RS/kc_ndvi_library.json` on Windows. Custom entries require finite `a` and `b`, a label and a crop list.

Built-in relationships have distinct calibration domains and provenance. A built-in catalog entry is **not** a guarantee that a relationship is appropriate for a particular crop, region, sensor or management system. Bibliographic correspondence does not establish local calibration suitability, equivalent reference-ET definitions, or predictive accuracy.

### 5.2.1 Built-in Kc–NDVI catalog: coefficients and provenance

The following table documents the **released v2.0.0 catalog**; the equations should not be assumed valid for all sites. In particular, some relationships originally refer to basal crop coefficients (Kcb), whereas the software treats all selected coefficients as a single Kc in ETc = Kc × ETo.

| Catalog entry / crop | Equation encoded in v2.0.0 | Scientific interpretation and source |
|---|---|---|
| Kamble et al. (2013), general | `Kc = 1.457 NDVI - 0.1725` | General empirical relationship; transfer requires calibration-domain caution. DOI: 10.3390/rs5041588. |
| Gontia & Tiwari (2010), wheat | `Kc = 2.7109 NDVI + 0.424` | Primary-source Eq. (7); the intercept is **positive**. DOI: 10.1007/s11269-009-9505-3. |
| Rocha et al. (2012), maize | `Kc = 1.37 NDVI - 0.017` | Primary-source Eq. (6); the original dependent variable is **basal Kcb**, not total Kc. The released library labels it Kc and the water engine uses it as such; soil evaporation Ke is not added. DOI: 10.5772/48561. |
| Singh & Irmak (2009), soybean | `Kc = 1.217 NDVI - 0.034` | Primary-source Fig. 6(b), p. 606: irrigated soybean, mean values across Landsat overpasses, Kcr = 1.217 NDVI - 0.034 (R² = 0.93). Crucially Kcr is defined against **alfalfa-reference ETr**, whereas CropWater-RS multiplies this coefficient by grass-reference ETo; this is not directly equivalent without reference conversion or recalibration. DOI: 10.1061/(ASCE)IR.1943-4774.0000052. |
| Reyes-González et al. (2015), alfalfa | `Kc = 2.112 NDVI - 0.4989` | Primary-source Fig. 4, p. 7: fitted line is Kc = 2.112 NDVI - 0.4989 (R² = 0.9723). The text Eq. (4), PDF p. 6, rounds the slope to 2.11; the library preserves the more precise figure coefficient. FAO-56-tabulated Kc calibration, not direct independent ETc measurement; Region Lagunera, Mexico, 2011. |
| Rossi et al. (2010), flooded rice | `Kc = 0.206 NDVI + 1.076` | Primary-source Table 1 (p. 228): 2003 flooded-rice relationship. The 2004 alternative (`Kc = 0.221 NDVI + 1.009`) is not implemented. The relationships were parameterized using FAO-56 tabulated Kc and spectral observations, not independent direct ETc measurements. DOI: 10.1061/(ASCE)IR.1943-4774.0000161. |

**Source:** `src/cropwater_rs/core/water.py`, `calculate_linear_kc`; `qt_kc_library_store.py`; `kc_ndvi_library.json`; `qt_water_page.py`, `calculate`.

### 5.3 Crop evapotranspiration

Crop evapotranspiration is estimated using the single-coefficient approach:

\[ET_{c,t}=K_{c,t}\,ET_{0,t},\]

where both `ETc` and `ETo` are expressed in mm d⁻¹. The application does not estimate `ET0` internally or independently account for soil evaporation and crop transpiration.

**Source:** `src/cropwater_rs/core/water.py`, `calculate_etc`.

### 5.4 Simplified net irrigation requirement

Daily net irrigation water requirement is calculated as:

\[IWR_{net,t}=\max\left(ET_{c,t}-P_{e,t},0\right),\]

where `Pe` is user-supplied **effective**, not necessarily total, precipitation. A negative daily deficit is set to zero before accumulation; therefore precipitation surpluses are not carried over to subsequent days. The result is a simplified daily atmospheric-demand-minus-effective-rainfall deficit, **not** a full root-zone soil-water balance and **not** gross irrigation demand. Irrigation application efficiency, soil-water storage, capillary rise, runoff, deep percolation and other balance terms are not modeled by these functions.

**Source:** `src/cropwater_rs/core/water.py`, `calculate_net_iwr`.

### 5.5 Daily cumulative series and period totals

For each parcel, daily outputs include `kc`, `etc_mm`, `iwr_net_mm`, `etc_cumulative_mm` and `iwr_cumulative_mm`. In `qt_water_page.py`, cumulative columns are computed using `cumsum()` over each parcel's complete reconstructed daily series, sorted by date. **These cumulative columns do not automatically restart at sowing.** Separate phase and crop-cycle totals are computed by summing the selected dates in the reporting layer.

For any reporting period \(T\):

\[ET_{c,T}=\sum_{t\in T}ET_{c,t},\qquad IWR_{net,T}=\sum_{t\in T}IWR_{net,t}.\]

**Source:** `qt_water_page.py`, `calculate`; `qt_water_phase_core.py`, `summarize_water`.

### 5.6 Analysis modes and phenological phase boundaries

Two modes are available:

1. **Full time series:** summarize all available reconstructed parcel-days without requiring QUANT transitions.
2. **QUANT phenological phases:** require a complete QUANT result, a resolved sowing date, strictly increasing boundaries, and complete daily data coverage from sowing through Q4.

The reporting layer uses five ordered boundaries: sowing, Q1, Q2, Q3 and Q4. Four non-overlapping periods are defined:

| Reported phase | Date interval |
|---|---|
| Start | Sowing ≤ date < Q1 |
| Development | Q1 ≤ date < Q2 |
| Mid-season | Q2 ≤ date < Q3 |
| Late-season | Q3 ≤ date ≤ Q4 |

The inclusive Q4 endpoint is intentional. Dates outside these intervals are marked `Outside crop cycle` in the phase-annotated daily table. A separate `Total crop cycle` record summarizes all four phases. Each phase record contains its dates, day count and, when present, metric means, minima, maxima and water totals.

The phases are **operational intervals defined by QUANT boundaries**, not independently observed FAO-56 phenological stages; their equivalence should not be assumed without validation.

**Source:** `qt_water_phase_core.py`, `PHASES`, `summarize_water`.

### 5.7 Sowing date determination and provenance

CropWater-RS supports **three distinct sources of sowing-date information** for parcel-level phase accounting:

1. **Vector attribute:** use a sowing date already supplied in the input parcel dataset. Its reliability depends on the provenance and quality of that attribute.
2. **Manual assignment:** specify a date using field knowledge, agronomic records, or an explicit user-defined assumption. A manually assigned date must not automatically be described as an observed date.
3. **Retrospective Q1 offset:** after detecting Q1 from the ascending 10% NDVI-amplitude crossing, infer a sowing date by subtracting a user-defined, crop-specific number of days:

   `sowing_date = Q1_date − offset_days`.

This offset is an assumption, **not a sowing-date estimate provided by French et al. (2023)** and not a direct output of QUANT. The interface initially includes an editable **30-day default for BARLEY**; it is not a universal agronomic constant. The v2.0.0 implementation resolves competing inputs with **manual override > vector attribute > Q1 offset**; this software precedence is separate from the conceptual description of the three available mechanisms. The selected source and offset are retained in `sowing_source`, `sowing_date` and `q1_offset_days` reporting fields. Missing or invalid sowing information prevents phase-based reporting for that parcel; it does not change the already computed daily ETc or IWR.

**Source:** `qt_water_page.py`, `sowing_dates`, `configure_sowing_offsets`, `calculate`.

### 5.8 Validation, diagnostics and excluded parcels

The implementation rejects non-finite or negative meteorology, duplicate meteorological keys, missing meteorology for NDVI parcel-days and unvalidated crop/formulation assignments. In phase mode it additionally rejects absent/ambiguous QUANT results, incomplete QUANT status, missing sowing, nonmonotonic dates, duplicated daily dates and gaps in daily coverage. These conditions are reported as issues. Phase reporting is generated only for valid parcel cycles; it does not interpolate missing weather or infer missing transitions.

**Source:** `qt_water_page.py`, `set_weather`, `calculate`; `qt_water_phase_core.py`, `summarize_water`.

### 5.9 Interpretation, uncertainty and limitations

Uncertainty propagates from the remotely sensed NDVI (cloud screening, valid-pixel sampling and temporal reconstruction), the selected Kc–NDVI calibration, supplied ETo and Pe, QUANT dates and estimated sowing dates. No formal propagation of these uncertainty components into ETc or IWR confidence intervals is implemented in the implemented calculation functions. Cross-crop or cross-region comparisons should document formulation provenance and meteorological data preparation.

The water equations are consistent with the crop-coefficient conceptual framework described by Allen et al. (1998), *Crop evapotranspiration: Guidelines for computing crop water requirements*, FAO Irrigation and Drainage Paper 56. However, **the application is not a complete FAO-56 dual-Kc or root-zone water-balance implementation**. Individual catalog references must be cited according to the actual selected Kc formulation; see Section 5.2.1 and `kc_ndvi_library.json` for equation provenance and application limitations.

### 5.10 Code traceability

| Processing operation | Code entry point | Main output |
|---|---|---|
| Meteorology input and validation | `qt_water_page.py::set_weather` | validated daily weather |
| Crop/formulation validation and date join | `qt_water_page.py::calculate` | merged parcel-day data |
| Linear Kc | `src/cropwater_rs/core/water.py::calculate_linear_kc` | `kc` |
| Crop evapotranspiration | `src/cropwater_rs/core/water.py::calculate_etc` | `etc_mm` |
| Net IWR | `src/cropwater_rs/core/water.py::calculate_net_iwr` | `iwr_net_mm` |
| Cumulative daily series | `qt_water_page.py::calculate` | `etc_cumulative_mm`, `iwr_cumulative_mm` |
| Sowing date precedence | `qt_water_page.py::sowing_dates` | sowing provenance |
| QUANT phase segmentation and totals | `qt_water_phase_core.py::summarize_water` | phase summary, annotated daily series, issues |
| User formulation persistence | `qt_kc_library_store.py::KcLibrary` | user Kc library JSON |

## 6. Reproducibility and reporting

For every analysis, archive the application version, parcel geometries and coordinate reference system, study dates, acquisition aggregation interval, SCL exclusion list, NDVI statistic (P50), QC thresholds and accepted counts, temporal reconstruction algorithm and parameters, NDVI clipping choice, QUANT thresholds and analysis window, selected Kc–NDVI equation and provenance, meteorological CSV and its ETo/Pe derivation, sowing-date source, and the resulting daily and phase summaries. Preserve available CSV parameter sidecars and `.cwrs` projects where applicable. Do not assume a `.cwrs` archive contains raw satellite imagery, user credentials, or user-defined Kc library files.

## 7. Methodological references

- Kamble, B., Kilic, A., & Hubbard, K. (2013). Estimating crop coefficients using remote sensing-based vegetation index. *Remote Sensing*, 5(4), 1588–1602. https://doi.org/10.3390/rs5041588
- Gontia, N. K., & Tiwari, K. N. (2010). Estimation of crop coefficient and evapotranspiration of wheat (*Triticum aestivum*) in an irrigation command using remote sensing and GIS. *Water Resources Management*, 24, 1399–1414. https://doi.org/10.1007/s11269-009-9505-3
- Reyes-González, A., Hay, C., Kjaersgaard, J., & Neale, C. (2015). *Use of remote sensing to generate crop coefficient and estimate actual crop evapotranspiration*. 2015 ASABE Annual International Meeting, New Orleans, Louisiana, Paper No. 152190105. — alfalfa Fig. 4 (2.112 NDVI - 0.4989); text Eq. (4) rounds slope to 2.11.
- Singh, R. K., & Irmak, A. (2009). Estimation of crop coefficients using satellite remote sensing. *Journal of Irrigation and Drainage Engineering*, 135(5), 597–608. https://doi.org/10.1061/(ASCE)IR.1943-4774.0000052
- Rocha, J., Perdigão, A., Melo, R., & Henriques, C. (2012). Remote sensing based crop coefficients for water management in agriculture. In *Sustainable Development – Authoritative and Leading Edge Content for Environmental Management* (Chapter 8, pp. 167–191). InTech. https://doi.org/10.5772/48561 — maize **Kcb** equation.
- Rossi, S., Rampini, A., Bocchi, S., & Boschetti, M. (2010). Operational monitoring of daily crop water requirements at the regional scale with time series of satellite data. *Journal of Irrigation and Drainage Engineering*, 136(4), 225–231. https://doi.org/10.1061/(ASCE)IR.1943-4774.0000161 — flooded rice, 2003 and 2004 relationships.

- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements*. FAO Irrigation and Drainage Paper 56.
- Eilers, P. H. C. (2003). A perfect smoother. *Analytical Chemistry*, 75, 3631–3636. https://doi.org/10.1021/ac034173t
- Savitzky, A., & Golay, M. J. E. (1964). Smoothing and differentiation of data by simplified least squares procedures. *Analytical Chemistry*, 36, 1627–1639. https://doi.org/10.1021/ac60214a047
- Kalman, R. E. (1960). A new approach to linear filtering and prediction problems. *Journal of Basic Engineering*, 82, 35–45. https://doi.org/10.1115/1.3662552
- Rauch, H. E., Tung, F., & Striebel, C. T. (1965). Maximum likelihood estimates of linear dynamic systems. *AIAA Journal*, 3, 1445–1450. https://doi.org/10.2514/3.3166
- Whittaker, E. T. (1923). On a new method of graduation. *Proceedings of the Edinburgh Mathematical Society*, 41, 63–75.
- French, A. N., Sanchez, C. A., Wirth, T., Scott, A., Shields, J. W., Bautista, E., Saber, M. N., Wisniewski, E., & Gohardoust, M. R. (2023). Remote sensing of evapotranspiration for irrigated crops at Yuma, Arizona, USA. *Agricultural Water Management*, 290, 108582. https://doi.org/10.1016/j.agwat.2023.108582 — primary source for the QUANT threshold framework; the sowing-date assignment implemented in CropWater-RS differs from the original paper.
