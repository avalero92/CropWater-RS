# Built-in NDVI–crop-coefficient relationships

CropWater-RS v2.0.0 provides six linear NDVI relationships. The numeric coefficients below are the values encoded in the v2.0.0 library. The output of each fitted equation must be interpreted according to the **coefficient type and reference evapotranspiration convention of its source**; the symbol `Kc` is not interchangeable with basal `Kcb` or a coefficient based on alfalfa-reference ET (`Kcr`).

| Model | Implemented expression | Interpretation / provenance |
|---|---|---|
| Kamble et al. (2013), general | `1.457 × NDVI − 0.1725` | Crop coefficient, context-dependent calibration |
| Gontia & Tiwari (2010), wheat | `2.7109 × NDVI + 0.424` | Wheat crop coefficient; **positive** intercept in the currently adopted model |
| Rocha et al. (2012), maize | `1.37 × NDVI − 0.017` | **Basal crop coefficient Kcb**, not total Kc |
| Singh & Irmak (2009), soybean | `1.217 × NDVI − 0.034` | Check reference-ET convention: coefficient reported in a reference-ET context that may differ from grass-reference ETo |
| Reyes-González et al. (2015), alfalfa | `2.112 × NDVI − 0.4989` | Alfalfa relationship; evaluate crop and sensor transferability |
| Rossi et al. (2010), rice | `0.206 × NDVI + 1.076` | Flooded-rice relationship attributed to the **2003** formulation discussed by Rossi et al. (2010) |

## Calculation and interpretation

The application evaluates each selected linear equation as `coefficient = a × NDVI + b`, with nonnegative clamping as described in the main methodology. The water calculation then uses the computed coefficient with the supplied reference evapotranspiration to obtain ETc. **This generic calculation does not, by itself, convert Kcb into total Kc or reconcile grass-reference ETo with alfalfa-reference ETr.** Users must choose an appropriate formulation and reference-ET basis; otherwise estimates can be systematically biased.

In particular, the Rocha maize equation is **Kcb** in the source, whereas the current Water Analysis computational path passes the linear output directly to the ETc multiplication step. This is a scientific limitation of that selection, not merely a naming issue. Correcting it would require an explicit calculation-policy decision and testing, rather than silently changing the catalog.

## Source metadata

The companion [`kc_ndvi_library.json`](../kc_ndvi_library.json) records numeric coefficients and descriptive metadata. Its `verification_status` field should not be interpreted as proof that an equation is universally transferable or independently validated for a user's fields. User-defined models require their own provenance and calibration documentation.

For full references, equation provenance and limitations, see [`SCIENTIFIC_METHODOLOGY.md`](../SCIENTIFIC_METHODOLOGY.md), Sections 5.2.1 and 7.
