# CropWater-RS User Guide — v1.0.0

## 1. Start
Install dependencies from `requirements.txt`, then run `python cropwater_rs.py`.

## 2. Load parcels
Open a polygon SHP, GeoPackage or GeoJSON.

Choose either:
- **Manual assignment**: select each parcel, choose a crop and press **Assign**.
- **Use vector attributes**: choose the ID and crop fields and apply them in batch.

## 3. Configure CDSE
Enter your Client ID and Client Secret, then define the date range, aggregation interval and valid-pixel threshold.

## 4. NDVI
Calculate one parcel or all parcels. Use Previous/Next to inspect trajectories.

## 5. Temporal processing
Available methods: Raw, Linear, Whittaker, Savitzky-Golay and Kalman.

Daily reconstructed output is recommended for accumulated water requirements.

## 6. QUANT phenology
Run QUANT after temporal reconstruction. It processes every parcel independently, identifies Q1–Q4, displays the transitions on the parcel curve and flags incomplete cases rather than forcing dates.

## 7. Kc–NDVI
Select a direct relationship compatible with the crop, or add a user relationship through the library manager.

## 8. Meteorology
Load `Date,ETo` for ETc/CWR, or `Date,ETo,Pe` for simplified net IWR. Optional `parcel_id` provides parcel-specific meteorology.

## 9. Water requirements
- `ETc = Kc × ETo`
- `CWR = ETc`
- `IWRnet,d = max(ETc,d - Pe,d, 0)`

## 10. Spatial view
Spatial outputs are parcel summaries, not pixel-level NDVI rasters.

## 11. Export
Export raw/processed NDVI, water results, QUANT results, run metadata and parcel-level GeoPackage outputs.

## 12. Logs
Logs are written to `.cropwater_rs/cropwater_rs.log` under the user's home directory.
