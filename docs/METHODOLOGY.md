# Methodology

## NDVI
`NDVI = (B08 - B04) / (B08 + B04)`

Sentinel-2 L2A parcel statistics are obtained through the CDSE Statistical API. The principal parcel statistic is NDVI P50.

The default SCL mask excludes classes 0, 1, 3, 8, 9, 10 and 11.

## Temporal reconstruction
Raw observations, Linear interpolation, Whittaker smoothing, Savitzky-Golay smoothing and Kalman reconstruction are supported.

## Crop coefficient
Direct relationships use `Kc = a × NDVI + b`. Kcb-only relationships are excluded from the direct Kc catalogue.

## Water requirements
`ETc = Kc × ETo`

`CWR = ETc`

`IWRnet,d = max(ETc,d - Pe,d, 0)`

The net IWR implementation is intentionally simplified and is not a full soil-water balance.

## Spatial outputs
Spatial maps represent parcel-level summaries.
