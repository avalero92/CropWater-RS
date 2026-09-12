# QUANT phenological partitioning

CropWater-RS implements an adapted, parcel-wise QUANT procedure on reconstructed daily NDVI.

For each parcel:
1. the seasonal maximum is identified;
2. the minimum preceding the maximum defines the remote-sensing cycle baseline;
3. amplitude is `NDVImax - NDVImin`;
4. user-defined amplitude percentages are converted to absolute NDVI thresholds;
5. threshold-crossing dates are estimated by linear interpolation.

Default thresholds:
- 10% rising: INI→DEV
- 90% rising: DEV→MID
- 90% falling: MID→END
- 50% falling: EOS

If crossings cannot be identified, the parcel is flagged as incomplete.

## Reference

French, A.N., Sanchez, C.A., Wirth, T., Scott, A., Shields, J.W., Bautista, E., Saber, M.N., Wisniewski, E., & Gohardoust, M.R. (2023). Remote sensing of evapotranspiration for irrigated crops at Yuma, Arizona, USA. *Agricultural Water Management*, 290, 108582. https://doi.org/10.1016/j.agwat.2023.108582

## CropWater-RS adaptation

French et al. used additional crop-calendar constraints. CropWater-RS does not impose an external planting-date constraint; it uses the parcel-specific pre-peak NDVI minimum as the remote cycle start. Results should therefore be interpreted as remotely sensed FAO-56-style temporal partitions.
