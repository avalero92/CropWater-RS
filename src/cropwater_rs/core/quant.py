"""QUANT scientific core, extracted from v1.0.1 without formula changes."""
import numpy as np
import pandas as pd

def validate_quant_thresholds(q1, q2, q3, q4):
    vals = [
        float(q1),
        float(q2),
        float(q3),
        float(q4),
    ]
    if any(v <= 0 or v >= 100 for v in vals):
        raise ValueError(
            "All QUANT thresholds must be between 0 and 100%."
        )
    q1, q2, q3, q4 = vals
    if q1 >= q2:
        raise ValueError(
            "The ascending INI→DEV threshold must be lower than DEV→MID."
        )
    if q4 >= q3:
        raise ValueError(
            "For the descending limb, the EOS threshold must be lower "
            "than the MID→END threshold."
        )
    return vals


def quant_crossing_date(dates, values, threshold, direction):
    dates = pd.to_datetime(pd.Series(dates), errors="coerce").reset_index(drop=True)
    values = pd.Series(values, dtype=float).reset_index(drop=True)

    hits = []
    for i in range(len(values) - 1):
        y0 = values.iloc[i]
        y1 = values.iloc[i + 1]
        if not np.isfinite(y0) or not np.isfinite(y1):
            continue

        if direction == "rising":
            crossed = (y0 <= threshold <= y1) and (y1 > y0)
        else:
            crossed = (y0 >= threshold >= y1) and (y1 < y0)

        if not crossed:
            continue

        t0 = dates.iloc[i]
        t1 = dates.iloc[i + 1]
        if pd.isna(t0) or pd.isna(t1):
            continue

        frac = (threshold - y0) / (y1 - y0)
        dt = t0 + (t1 - t0) * float(frac)
        hits.append(pd.Timestamp(dt))

    if not hits:
        return pd.NaT

    # Right-most crossing is more robust to small residual oscillations
    # and is consistent with the late-season selection described by French et al.
    return hits[-1] if direction == "falling" else hits[0]


def calculate_quant_one(parcel_id, temporal_results, thresholds=(10.0, 90.0, 90.0, 50.0), gdf=None):
    result = temporal_results.get(str(parcel_id))
    if result is None:
        # tolerate legacy keys not converted to str
        result = temporal_results.get(parcel_id)
    if not result:
        raise ValueError("No reconstructed temporal series.")

    daily = result.get("daily")
    if daily is None or daily.empty:
        raise ValueError("Daily reconstructed NDVI is unavailable.")

    df = daily[["date", "ndvi_reconstructed_daily"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["ndvi_reconstructed_daily"] = pd.to_numeric(
        df["ndvi_reconstructed_daily"],
        errors="coerce",
    )
    df = (
        df.dropna()
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )

    if len(df) < 5:
        raise ValueError("Too few daily values for QUANT.")

    vals = df["ndvi_reconstructed_daily"].to_numpy(dtype=float)
    peak_pos = int(np.nanargmax(vals))
    if peak_pos < 2 or peak_pos >= len(df) - 2:
        raise ValueError(
            "Seasonal maximum is too close to the temporal boundary."
        )

    pre = df.iloc[: peak_pos + 1]
    min_rel = int(np.nanargmin(
        pre["ndvi_reconstructed_daily"].to_numpy(dtype=float)
    ))
    min_pos = min_rel

    ndvi_min = float(df.loc[min_pos, "ndvi_reconstructed_daily"])
    ndvi_max = float(df.loc[peak_pos, "ndvi_reconstructed_daily"])
    amplitude = ndvi_max - ndvi_min

    if not np.isfinite(amplitude) or amplitude <= 0.05:
        raise ValueError(
            f"Insufficient seasonal NDVI amplitude ({amplitude:.3f})."
        )

    q1, q2, q3, q4 = validate_quant_thresholds(*thresholds)

    thresholds = {
        "Q1": ndvi_min + (q1 / 100.0) * amplitude,
        "Q2": ndvi_min + (q2 / 100.0) * amplitude,
        "Q3": ndvi_min + (q3 / 100.0) * amplitude,
        "Q4": ndvi_min + (q4 / 100.0) * amplitude,
    }

    rising = df.iloc[min_pos : peak_pos + 1].copy()
    falling = df.iloc[peak_pos:].copy()

    q1_date = quant_crossing_date(
        rising["date"],
        rising["ndvi_reconstructed_daily"],
        thresholds["Q1"],
        "rising",
    )
    q2_date = quant_crossing_date(
        rising["date"],
        rising["ndvi_reconstructed_daily"],
        thresholds["Q2"],
        "rising",
    )
    q3_date = quant_crossing_date(
        falling["date"],
        falling["ndvi_reconstructed_daily"],
        thresholds["Q3"],
        "falling",
    )
    q4_date = quant_crossing_date(
        falling["date"],
        falling["ndvi_reconstructed_daily"],
        thresholds["Q4"],
        "falling",
    )

    cycle_start = pd.Timestamp(df.loc[min_pos, "date"])
    peak_date = pd.Timestamp(df.loc[peak_pos, "date"])

    required = [q1_date, q2_date, q3_date, q4_date]
    complete = all(not pd.isna(x) for x in required)

    durations = {
        "INI_days": np.nan,
        "DEV_days": np.nan,
        "MID_days": np.nan,
        "END_days": np.nan,
        "Total_days": np.nan,
    }

    if complete:
        durations["INI_days"] = (q1_date - cycle_start).total_seconds() / 86400.0
        durations["DEV_days"] = (q2_date - q1_date).total_seconds() / 86400.0
        durations["MID_days"] = (q3_date - q2_date).total_seconds() / 86400.0
        durations["END_days"] = (q4_date - q3_date).total_seconds() / 86400.0
        durations["Total_days"] = (q4_date - cycle_start).total_seconds() / 86400.0

        if any(v < 0 for v in durations.values()):
            complete = False

    crop = ""
    if gdf is not None:
        hit = gdf[
            gdf["parcel_id"].astype(str) == str(parcel_id)
        ]
        if not hit.empty:
            crop = str(hit.iloc[0]["crop"])

    out = {
        "parcel_id": str(parcel_id),
        "crop": crop,
        "status": "Complete" if complete else "Incomplete",
        "cycle_start_date": cycle_start,
        "cycle_start_DOY": int(cycle_start.dayofyear),
        "peak_date": peak_date,
        "peak_DOY": int(peak_date.dayofyear),
        "NDVI_min": ndvi_min,
        "NDVI_max": ndvi_max,
        "NDVI_amplitude": amplitude,
        "q1_percent": q1,
        "q2_percent": q2,
        "q3_percent": q3,
        "q4_percent": q4,
        "q1_threshold_ndvi": thresholds["Q1"],
        "q2_threshold_ndvi": thresholds["Q2"],
        "q3_threshold_ndvi": thresholds["Q3"],
        "q4_threshold_ndvi": thresholds["Q4"],
        "Q1_date": q1_date,
        "Q2_date": q2_date,
        "Q3_date": q3_date,
        "Q4_date": q4_date,
        "Q1_DOY": int(q1_date.dayofyear) if not pd.isna(q1_date) else np.nan,
        "Q2_DOY": int(q2_date.dayofyear) if not pd.isna(q2_date) else np.nan,
        "Q3_DOY": int(q3_date.dayofyear) if not pd.isna(q3_date) else np.nan,
        "Q4_DOY": int(q4_date.dayofyear) if not pd.isna(q4_date) else np.nan,
        **durations,
    }
    return out
