"""Original temporal numerical helpers, extracted unchanged."""
import numpy as np
import pandas as pd

def _kalman_smooth_local_level(y):
    """Simple local-level Kalman filter + RTS smoother with missing data."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    finite = np.isfinite(y)
    if finite.sum() < 2:
        return np.full(n, np.nan)

    obs = y[finite]
    diffs = np.diff(obs)
    scale = np.nanvar(obs)
    if not np.isfinite(scale) or scale <= 1e-8:
        scale = 0.01

    r = max(scale * 0.05, 1e-5)
    q = max(np.nanvar(diffs) * 0.05 if len(diffs) else scale * 0.01, 1e-6)

    x_f = np.zeros(n, dtype=float)
    p_f = np.zeros(n, dtype=float)
    x_pred = np.zeros(n, dtype=float)
    p_pred = np.zeros(n, dtype=float)

    first = int(np.flatnonzero(finite)[0])
    x_prev = float(y[first])
    p_prev = 1.0

    for t in range(n):
        xp = x_prev
        pp = p_prev + q
        x_pred[t] = xp
        p_pred[t] = pp

        if finite[t]:
            k = pp / (pp + r)
            xf = xp + k * (y[t] - xp)
            pf = (1.0 - k) * pp
        else:
            xf = xp
            pf = pp

        x_f[t] = xf
        p_f[t] = pf
        x_prev, p_prev = xf, pf

    x_s = x_f.copy()
    p_s = p_f.copy()

    for t in range(n - 2, -1, -1):
        denom = p_pred[t + 1]
        c = p_f[t] / denom if denom > 0 else 0.0
        x_s[t] = x_f[t] + c * (x_s[t + 1] - x_pred[t + 1])
        p_s[t] = p_f[t] + c * c * (p_s[t + 1] - p_pred[t + 1])

    return x_s


def _temporal_diagnostics(good, reconstructed, method):
    if method == "Raw observations" or reconstructed.isna().all():
        return {
            "n": len(good),
            "rmse": np.nan,
            "mae": np.nan,
            "r2": np.nan,
        }

    obs_dates = (
        pd.to_datetime(good["date_start"], utc=True)
        .dt.tz_convert(None)
        .dt.normalize()
    )
    obs = good["ndvi_p50"].to_numpy(dtype=float)
    pred = reconstructed.reindex(obs_dates).to_numpy(dtype=float)

    mask = np.isfinite(obs) & np.isfinite(pred)
    obs = obs[mask]
    pred = pred[mask]

    if len(obs) == 0:
        return {"n": 0, "rmse": np.nan, "mae": np.nan, "r2": np.nan}

    err = obs - pred
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mae = float(np.mean(np.abs(err)))

    if len(obs) >= 2 and np.var(obs) > 0:
        ss_res = float(np.sum((obs - pred) ** 2))
        ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
        r2 = 1.0 - ss_res / ss_tot
    else:
        r2 = np.nan

    return {"n": len(obs), "rmse": rmse, "mae": mae, "r2": r2}


# Full daily reconstruction extracted from the v1.0.1 GUI without algorithmic changes.
from scipy.signal import savgol_filter
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve

def process_one_temporal_series(df, method, lam, sg_window, start_date, end_date, constrain_ndvi, output_resolution):
    good = df.loc[
        df["accepted"] & df["ndvi_p50"].notna(),
        ["date_start", "ndvi_p50"],
    ].copy()

    good["ndvi_p50"] = pd.to_numeric(
        good["ndvi_p50"],
        errors="coerce",
    )
    good = good.loc[
        np.isfinite(good["ndvi_p50"].to_numpy(dtype=float))
    ].copy()

    # CDSE timestamps are timezone-aware (UTC), while the daily index
    # created from the date-entry widgets is timezone-naive.  If both are
    # compared directly, no acquisition date matches the daily grid and the
    # reconstructed series collapses to empty/zero values.  Convert both to
    # plain calendar dates before matching.
    good["date_start"] = (
        pd.to_datetime(good["date_start"], utc=True)
        .dt.tz_convert(None)
        .dt.normalize()
    )
    good = (
        good.groupby("date_start", as_index=False)["ndvi_p50"]
        .median()
        .sort_values("date_start")
    )

    if len(good) >= 2:
        _gaps = good["date_start"].diff().dt.days.dropna()
        longest_gap_days = int(_gaps.max()) if not _gaps.empty else 0
    else:
        longest_gap_days = None

    if len(good) < 2:
        raise ValueError("At least two accepted NDVI observations are required.")

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    daily_index = pd.date_range(start, end, freq="D")

    observed = pd.Series(index=daily_index, dtype=float)
    valid_dates = good["date_start"].isin(daily_index)
    good = good.loc[valid_dates].copy()

    if good.empty:
        raise ValueError(
            "No accepted Sentinel-2 observations matched the selected date range."
        )
    if len(good) < 2:
        raise ValueError(
            "At least two accepted NDVI observations within the selected "
            "date range are required for temporal reconstruction."
        )

    observed.loc[good["date_start"]] = good["ndvi_p50"].to_numpy()

    # Linear interpolation supplies a complete baseline and endpoint values.
    linear = observed.interpolate(method="time", limit_direction="both")

    if method == "Raw observations":
        reconstructed = pd.Series(np.nan, index=daily_index, dtype=float)

    elif method == "Linear interpolation":
        reconstructed = linear.copy()

    elif method == "Whittaker":
        n = len(daily_index)
        y = observed.to_numpy(dtype=float)
        w = np.isfinite(y).astype(float)
        y0 = np.nan_to_num(y, nan=0.0)

        # Second-order difference penalty:
        # min Σ w_i(y_i-z_i)^2 + λ||D²z||²
        W = diags(w, 0, shape=(n, n), format="csc")
        D = diags(
            [np.ones(n), -2.0 * np.ones(n), np.ones(n)],
            [0, 1, 2],
            shape=(n - 2, n),
            format="csc",
        )
        A = W + lam * (D.T @ D)
        reconstructed = pd.Series(
            spsolve(A, w * y0),
            index=daily_index,
            dtype=float,
        )

    elif method == "Savitzky-Golay":
        # SG is applied to the complete daily linear-interpolation baseline.
        # ``mode="interp"`` in scipy performs polynomial least-squares fits
        # at both edges and, depending on the local LAPACK/NumPy/SciPy stack,
        # can raise "SVD did not converge in Linear Least Squares".
        # ``nearest`` avoids that auxiliary edge regression while preserving
        # the SG polynomial smoothing in the interior.
        vals = linear.to_numpy(dtype=float)

        if len(vals) < 5:
            raise ValueError(
                "Selected period is too short for Savitzky-Golay."
            )

        # Guard against non-finite input before entering scipy.
        finite = np.isfinite(vals)
        if not finite.all():
            # Rebuild any residual missing/invalid positions robustly.
            safe = pd.Series(
                np.where(finite, vals, np.nan),
                index=daily_index,
                dtype=float,
            ).interpolate(
                method="time",
                limit_direction="both",
            )
            vals = safe.to_numpy(dtype=float)

        if not np.isfinite(vals).all():
            raise ValueError(
                "Savitzky-Golay could not be applied because the daily "
                "baseline still contains non-finite NDVI values."
            )

        window = int(sg_window)
        if window % 2 == 0:
            window += 1

        max_window = (
            len(vals)
            if len(vals) % 2 == 1
            else len(vals) - 1
        )
        window = min(window, max_window)

        # Keep an odd window and guarantee polyorder < window_length.
        if window < 5:
            raise ValueError(
                "Selected period is too short for Savitzky-Golay."
            )

        polyorder = min(2, window - 1)

        try:
            sg_values = savgol_filter(
                vals,
                window_length=window,
                polyorder=polyorder,
                mode="nearest",
            )
        except Exception as exc:
            raise ValueError(
                "Savitzky-Golay smoothing failed. "
                f"Window={window} days, polyorder={polyorder}. "
                f"Original error: {exc}"
            ) from exc

        # Defensive post-condition: SG must yield one finite value per day.
        sg_values = np.asarray(sg_values, dtype=float)
        if sg_values.shape[0] != len(daily_index):
            raise ValueError(
                "Savitzky-Golay returned an unexpected number of values "
                f"({sg_values.shape[0]} instead of {len(daily_index)})."
            )
        if not np.isfinite(sg_values).any():
            raise ValueError(
                "Savitzky-Golay returned no finite NDVI values."
            )

        reconstructed = pd.Series(
            sg_values,
            index=daily_index,
            dtype=float,
        )

    elif method == "Kalman":
        reconstructed = pd.Series(
            _kalman_smooth_local_level(observed.to_numpy(dtype=float)),
            index=daily_index,
            dtype=float,
        )

    else:
        raise ValueError(f"Unknown temporal method: {method}")

    if method != "Raw observations" and constrain_ndvi:
        reconstructed = reconstructed.clip(lower=0.0, upper=1.0)

    # Requested output resolution. Internal reconstruction remains daily.
    out = pd.DataFrame({
        "date": daily_index,
        "ndvi_observed": observed.to_numpy(dtype=float),
        "ndvi_reconstructed_daily": reconstructed.to_numpy(dtype=float),
    })

    resolution = output_resolution
    if method == "Raw observations":
        output_dates = good["date_start"]
        output_values = good["ndvi_p50"].to_numpy(dtype=float)
    else:
        if resolution == "Daily":
            output_dates = daily_index
            output_values = reconstructed.to_numpy(dtype=float)
        else:
            step = 5 if resolution == "5 days" else 10
            sampled = reconstructed.iloc[::step]
            output_dates = sampled.index
            output_values = sampled.to_numpy(dtype=float)

    output = pd.DataFrame({
        "date": pd.to_datetime(output_dates),
        "ndvi_processed": output_values,
    })

    # A processed method must always expose an actual temporal series.
    # Failing here is preferable to silently storing an empty result that
    # later appears as if the method had done nothing in the GUI.
    if method != "Raw observations":
        processed_numeric = pd.to_numeric(
            output["ndvi_processed"], errors="coerce"
        )
        if output.empty or not np.isfinite(processed_numeric.to_numpy(dtype=float)).any():
            raise ValueError(
                f"{method} produced no finite temporal NDVI series."
            )

    diagnostics = _temporal_diagnostics(good, reconstructed, method)

    return {
        "method": method,
        "daily": out,
        "output": output,
        "diagnostics": diagnostics,
        "quality": {
            "n_accepted": int(len(good)),
            "longest_gap_days": longest_gap_days,
        },
    }
