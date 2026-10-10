# Exact method bodies extracted from cropwater_rs.py v1.0.1, without algorithm changes.
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve
class BaselineMethods:
    def _validate_quant_thresholds(self):
            vals = [
                float(self.quant_q1_var.get()),
                float(self.quant_q2_var.get()),
                float(self.quant_q3_var.get()),
                float(self.quant_q4_var.get()),
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

    @staticmethod
    def _quant_crossing_date(dates, values, threshold, direction):
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

    def _calculate_quant_one(self, parcel_id):
            result = self.temporal_results.get(str(parcel_id))
            if result is None:
                # tolerate legacy keys not converted to str
                result = self.temporal_results.get(parcel_id)
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

            q1, q2, q3, q4 = self._validate_quant_thresholds()

            thresholds = {
                "Q1": ndvi_min + (q1 / 100.0) * amplitude,
                "Q2": ndvi_min + (q2 / 100.0) * amplitude,
                "Q3": ndvi_min + (q3 / 100.0) * amplitude,
                "Q4": ndvi_min + (q4 / 100.0) * amplitude,
            }

            rising = df.iloc[min_pos : peak_pos + 1].copy()
            falling = df.iloc[peak_pos:].copy()

            q1_date = self._quant_crossing_date(
                rising["date"],
                rising["ndvi_reconstructed_daily"],
                thresholds["Q1"],
                "rising",
            )
            q2_date = self._quant_crossing_date(
                rising["date"],
                rising["ndvi_reconstructed_daily"],
                thresholds["Q2"],
                "rising",
            )
            q3_date = self._quant_crossing_date(
                falling["date"],
                falling["ndvi_reconstructed_daily"],
                thresholds["Q3"],
                "falling",
            )
            q4_date = self._quant_crossing_date(
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
            if self.gdf is not None:
                hit = self.gdf[
                    self.gdf["parcel_id"].astype(str) == str(parcel_id)
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

    def _process_one_temporal_series(self, df, method, lam, sg_window):
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

            start = pd.Timestamp(self.start_var.get()).normalize()
            end = pd.Timestamp(self.end_var.get()).normalize()
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
                    self._kalman_smooth_local_level(observed.to_numpy(dtype=float)),
                    index=daily_index,
                    dtype=float,
                )

            else:
                raise ValueError(f"Unknown temporal method: {method}")

            if method != "Raw observations" and self.constrain_ndvi_var.get():
                reconstructed = reconstructed.clip(lower=0.0, upper=1.0)

            # Requested output resolution. Internal reconstruction remains daily.
            out = pd.DataFrame({
                "date": daily_index,
                "ndvi_observed": observed.to_numpy(dtype=float),
                "ndvi_reconstructed_daily": reconstructed.to_numpy(dtype=float),
            })

            resolution = self.output_resolution_var.get()
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

            diagnostics = self._temporal_diagnostics(good, reconstructed, method)

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

    @staticmethod
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

    @staticmethod
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
