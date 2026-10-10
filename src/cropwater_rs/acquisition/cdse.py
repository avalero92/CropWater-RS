"""CDSE Statistical API request construction and response decoding (Alpha 5)."""
import numpy as np
import pandas as pd

def stats_response_to_df(response):
    records = []

    for item in response.get("data", []):
        interval = item.get("interval", {})
        outputs = item.get("outputs", {})
        ndvi_obj = outputs.get("ndvi", {})
        bands = ndvi_obj.get("bands", {})
        b0 = bands.get("B0", {})
        stats = b0.get("stats", {})
        percentiles = stats.get("percentiles", {})

        sample_count = stats.get("sampleCount", np.nan)
        no_data_count = stats.get("noDataCount", np.nan)

        if pd.notna(sample_count) and sample_count:
            valid_fraction = (
                100.0 * max(sample_count - no_data_count, 0) / sample_count
            )
        else:
            valid_fraction = np.nan

        records.append(
            {
                "date_start": pd.to_datetime(interval.get("from")),
                "date_end": pd.to_datetime(interval.get("to")),
                "ndvi_mean": stats.get("mean", np.nan),
                "ndvi_stdev": stats.get("stDev", np.nan),
                "ndvi_min": stats.get("min", np.nan),
                "ndvi_max": stats.get("max", np.nan),
                "ndvi_p25": percentiles.get("25.0", percentiles.get("25", np.nan)),
                "ndvi_p50": percentiles.get("50.0", percentiles.get("50", np.nan)),
                "ndvi_p75": percentiles.get("75.0", percentiles.get("75", np.nan)),
                "sample_count": sample_count,
                "no_data_count": no_data_count,
                "valid_fraction_pct": valid_fraction,
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        return df

    df = df.sort_values("date_start").reset_index(drop=True)
    return df


def get_cdse_l2a_collection(data_collection, base_url):
    """Reuse the registered CDSE collection across Statistical and Process APIs.

    sentinelhub-py rejects registering an identical collection definition twice.
    """
    base_url = str(base_url).rstrip("/")
    existing = getattr(data_collection, "s2l2a_cdse", None)
    if existing is not None:
        return existing
    return data_collection.SENTINEL2_L2A.define_from(
        name="s2l2a_cdse", service_url=base_url
    )


def build_statistical_request(geometry, start_date, end_date, interval, config, *, statistical_class, data_collection, base_url, evalscript):
    """Build the original CDSE request, injecting SentinelHub types for offline tests."""
    aggregation = statistical_class.aggregation(
        evalscript=evalscript, time_interval=(start_date,end_date),
        aggregation_interval=interval, resolution=(10,10),
    )
    calculations = {"ndvi":{"statistics":{"default":{"percentiles":{"k":[25,50,75]}}}}}
    return statistical_class(
        aggregation=aggregation,
        input_data=[statistical_class.input_data(
            get_cdse_l2a_collection(data_collection, base_url),
            other_args={"dataFilter":{"mosaickingOrder":"leastCC"}},
        )],
        geometry=geometry,calculations=calculations,config=config,
    )
