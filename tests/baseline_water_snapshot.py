# Literal method snapshots from cropwater_rs.py (baseline v1.0.1).
# No computational logic changed. GUI dependencies supplied by tests.
import json, logging
from pathlib import Path
import numpy as np
import pandas as pd
from baseline_core_snapshot import calculate_etc, calculate_net_iwr
class BaselineWaterMethods:
    def _load_kc_library(self):
        global KC_CATALOG
        if not self.kc_library_path.exists():
            logging.info("External Kc library not found; built-in catalogue used.")
            return
        try:
            loaded = json.loads(
                self.kc_library_path.read_text(encoding="utf-8")
            )
            if not isinstance(loaded, dict) or not loaded:
                raise ValueError("Kc library must be a non-empty JSON object.")

            cleaned = {}
            for model_id, m in loaded.items():
                required = ["label", "crops", "a", "b", "reference"]
                missing = [x for x in required if x not in m]
                if missing:
                    raise ValueError(
                        f"{model_id}: missing required field(s): "
                        + ", ".join(missing)
                    )
                m = dict(m)
                m["a"] = float(m["a"])
                m["b"] = float(m["b"])
                m["crops"] = [str(c).upper() for c in m["crops"]]
                m.setdefault(
                    "equation",
                    f"Kc = {m['a']} × NDVI "
                    + (f"+ {m['b']}" if m["b"] >= 0 else f"- {abs(m['b'])}")
                )
                m.setdefault("doi", "")
                m.setdefault("scope", "")
                m.setdefault("kc_type", "Kc")
                m.setdefault("sensor", "Not specified")
                m.setdefault("study_region", "Not specified")
                m.setdefault("r2", None)
                m.setdefault("ndvi_min", None)
                m.setdefault("ndvi_max", None)
                m.setdefault("kc_min", None)
                m.setdefault("kc_max", None)
                m.setdefault("source_type", "built-in")
                m.setdefault("verification_status", "not specified")
                m.setdefault("calibration_note", "")
                cleaned[str(model_id)] = m

            KC_CATALOG = cleaned
            logging.info("Loaded %d Kc-NDVI relationships", len(KC_CATALOG))
        except Exception as exc:
            logging.exception("Kc library load failed")
            messagebox.showwarning(
                "Kc–NDVI library",
                "The external Kc library could not be loaded. "
                "The internal catalogue will be used.\n\n"
                f"{exc}",
            )

    def load_meteo_csv(self):
        path = filedialog.askopenfilename(
            title="Select meteorological CSV",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            df = pd.read_csv(path, sep=None, engine="python")
            # Case-insensitive canonicalization
            mapping = {
                str(c).replace("\ufeff", "").strip().lower(): c
                for c in df.columns
            }
            if "date" not in mapping or "eto" not in mapping:
                raise ValueError("The CSV must contain at least Date and ETo columns.")

            rename = {
                mapping["date"]: "Date",
                mapping["eto"]: "ETo",
            }
            if "pe" in mapping:
                rename[mapping["pe"]] = "Pe"
            if "parcel_id" in mapping:
                rename[mapping["parcel_id"]] = "parcel_id"

            df = df.rename(columns=rename)

            # Parse dates deterministically. CropWater-RS accepts the two
            # documented formats used most often by the target workflows:
            # ISO YYYY-MM-DD and European DD/MM/YYYY. Avoid pandas' generic
            # inference because mixed/ambiguous day-month values can otherwise
            # be silently interpreted incorrectly.
            raw_dates = df["Date"].astype(str).str.strip()
            parsed_dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

            iso_mask = raw_dates.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)
            if iso_mask.any():
                parsed_dates.loc[iso_mask] = pd.to_datetime(
                    raw_dates.loc[iso_mask],
                    format="%Y-%m-%d",
                    errors="coerce",
                )

            dmy_mask = raw_dates.str.match(r"^\d{1,2}/\d{1,2}/\d{4}$", na=False)
            if dmy_mask.any():
                parsed_dates.loc[dmy_mask] = pd.to_datetime(
                    raw_dates.loc[dmy_mask],
                    format="%d/%m/%Y",
                    errors="coerce",
                )

            invalid_dates = parsed_dates.isna()
            if invalid_dates.any():
                examples = ", ".join(
                    raw_dates.loc[invalid_dates].head(5).astype(str).tolist()
                )
                raise ValueError(
                    "Some Date values could not be parsed. Accepted formats are "
                    "YYYY-MM-DD and DD/MM/YYYY."
                    + (f" Examples: {examples}" if examples else "")
                )

            df["Date"] = parsed_dates.dt.normalize()

            df["ETo"] = pd.to_numeric(df["ETo"], errors="coerce")
            if df["ETo"].isna().any():
                raise ValueError("Some ETo values are missing or non-numeric.")
            if (df["ETo"] < 0).any():
                raise ValueError("ETo cannot contain negative values.")
            high_eto_n = int((df["ETo"] > 15).sum())

            if "Pe" in df.columns:
                df["Pe"] = pd.to_numeric(df["Pe"], errors="coerce")
                if df["Pe"].isna().any():
                    raise ValueError("Some Pe values are missing or non-numeric.")
                if (df["Pe"] < 0).any():
                    raise ValueError("Pe cannot contain negative values.")
                high_pe_n = int((df["Pe"] > 200).sum())

            subset = ["Date"] + (["parcel_id"] if "parcel_id" in df.columns else [])
            if df.duplicated(subset=subset).any():
                raise ValueError(
                    "Duplicate meteorological records detected for Date"
                    + (" + parcel_id." if "parcel_id" in df.columns else ".")
                )

            if "parcel_id" in df.columns:
                df["parcel_id"] = df["parcel_id"].astype(str)

            self._invalidate_water()
            self.meteo_df = df.sort_values(subset).reset_index(drop=True)
            self.meteo_file = path
            self.meteo_file_var.set(path)

            # If Pe is supplied, default to Net IWR for the test workflow.
            # The user can still switch back to "CWR / ETc only".
            if "Pe" in df.columns:
                self.water_mode_var.set("Net IWR")

            extra = "Pe available — Net IWR can be calculated" if "Pe" in df.columns else "Pe not present — CWR / ETc only"
            scope = "parcel-specific" if "parcel_id" in df.columns else "shared by all parcels"
            warnings = []
            if high_eto_n:
                warnings.append(f"{high_eto_n} ETo value(s) > 15 mm d⁻¹")
            if "Pe" in df.columns and high_pe_n:
                warnings.append(f"{high_pe_n} Pe value(s) > 200 mm d⁻¹")
            warning_txt = ""
            if warnings:
                warning_txt = "\nWarning: " + "; ".join(warnings)

            messagebox.showinfo(
                "Meteorological CSV",
                f"Loaded {len(df)} records.\n{extra}\nMeteorology: {scope}.\n"
                f"Expected units: ETo and Pe in mm d⁻¹."
                f"{warning_txt}",
            )

        except Exception as exc:
            messagebox.showerror("Meteorological CSV", str(exc))

    def calculate_water_all(self):
        if not self.kc_results:
            messagebox.showwarning("CWR / IWR", "Calculate Kc first.")
            return
        if self.meteo_df is None or self.meteo_df.empty:
            messagebox.showwarning("CWR / IWR", "Load the meteorological CSV first.")
            return

        mode = self.water_mode_var.get().strip()
        calculate_iwr = (mode == "Net IWR")

        # Kc from raw Sentinel-2 observations may be inspected/exported,
        # but seasonal CWR/IWR accumulation requires continuous daily Kc.
        invalid_daily = []
        for pid, kcdf in self.kc_results.items():
            if kcdf is None or kcdf.empty:
                invalid_daily.append(str(pid))
                continue

            sources = set(kcdf["NDVI_source"].astype(str).unique())
            processed_source = any(s.startswith("Processed") for s in sources)

            dates = pd.to_datetime(
                kcdf["date"], errors="coerce"
            ).dropna().sort_values().drop_duplicates()

            continuous_daily = (
                len(dates) >= 2
                and dates.diff().dt.days.dropna().eq(1).all()
            )

            if not processed_source or not continuous_daily:
                invalid_daily.append(str(pid))

        if invalid_daily:
            messagebox.showwarning(
                "CWR / IWR",
                "Accumulated CWR/IWR requires continuous DAILY processed NDVI/Kc.\n\n"
                "Raw Sentinel-2 observations remain valid for Kc inspection/export, "
                "but not for seasonal water accumulation.\n\n"
                "Process the temporal series and recalculate Kc for: "
                + ", ".join(invalid_daily)
            )
            return

        if calculate_iwr and "Pe" not in self.meteo_df.columns:
            messagebox.showerror(
                "Net IWR",
                "Net IWR was selected, but the meteorological CSV does not contain Pe.",
            )
            return

        self.water_results.clear()
        errors = []

        for pid, kc_df in self.kc_results.items():
            try:
                met = self.meteo_df.copy()

                if "parcel_id" in met.columns:
                    met = met[met["parcel_id"].astype(str) == str(pid)].copy()
                    if met.empty:
                        raise ValueError(
                            "No meteorological records were found for this parcel."
                        )

                merged = kc_df.copy()
                merged["date"] = pd.to_datetime(
                    merged["date"], errors="coerce"
                ).dt.normalize()

                met["Date"] = pd.to_datetime(
                    met["Date"], errors="coerce"
                ).dt.normalize()

                required_dates = pd.DatetimeIndex(
                    merged["date"].dropna().drop_duplicates().sort_values()
                )
                met_dates = pd.DatetimeIndex(
                    met["Date"].dropna().drop_duplicates().sort_values()
                )

                missing_dates = required_dates.difference(met_dates)
                if len(missing_dates):
                    preview = ", ".join(
                        d.strftime("%Y-%m-%d") for d in missing_dates[:8]
                    )
                    if len(missing_dates) > 8:
                        preview += f" ... (+{len(missing_dates) - 8} more)"
                    raise ValueError(
                        f"Incomplete meteorological coverage: "
                        f"{len(missing_dates)} required day(s) missing. {preview}"
                    )

                expected_dates = pd.date_range(
                    required_dates.min(), required_dates.max(), freq="D"
                )
                if len(expected_dates) != len(required_dates):
                    raise ValueError(
                        "The Kc series is not continuous daily data. "
                        "CWR/IWR accumulation was stopped."
                    )

                merged = merged.merge(
                    met,
                    left_on="date",
                    right_on="Date",
                    how="left",
                    suffixes=("", "_meteo"),
                    validate="one_to_one",
                )

                if merged["ETo"].isna().any():
                    raise ValueError("ETo contains missing values after date matching.")

                # Crop water requirement: CWR = ETc = Kc * ETo
                merged["ETc"] = calculate_etc(
                    merged["Kc"].to_numpy(),
                    merged["ETo"].to_numpy(),
                )
                merged["CWR"] = merged["ETc"]
                merged["CWR_cumulative"] = merged["CWR"].cumsum()

                # Net irrigation water requirement is calculated only when
                # explicitly requested by the user.
                if calculate_iwr:
                    if merged["Pe"].isna().any():
                        raise ValueError(
                            "Pe contains missing values on dates matched to the Kc series."
                        )

                    merged["IWR_net"] = (
                        merged["CWR"] - merged["Pe"]
                    ).clip(lower=0.0)

                    merged["IWR_net_cumulative"] = (
                        merged["IWR_net"].cumsum()
                    )

                merged["ETo_warning"] = merged["ETo"] > 15
                if "Pe" in merged.columns:
                    merged["Pe_warning"] = merged["Pe"] > 200

                self.water_results[str(pid)] = merged.reset_index(drop=True)

            except Exception as exc:
                errors.append((str(pid), str(exc)))

        self._plot_selected_water()
        self._update_water_summary()

        n_iwr = sum(
            1 for df in self.water_results.values()
            if "IWR_net" in df.columns
        )

        if errors:
            details = "\n".join(f"{pid}: {msg}" for pid, msg in errors[:8])
            messagebox.showwarning(
                "CWR / IWR",
                f"Results calculated for {len(self.water_results)} parcel(s).\n"
                f"Net IWR calculated for {n_iwr} parcel(s).\n\n"
                f"Problems:\n{details}",
            )
        else:
            if calculate_iwr:
                messagebox.showinfo(
                    "CWR / IWR",
                    f"CWR and net IWR calculated successfully for "
                    f"{len(self.water_results)} parcel(s).",
                )
            else:
                messagebox.showinfo(
                    "CWR / ETc",
                    f"CWR / ETc calculated successfully for "
                    f"{len(self.water_results)} parcel(s).",
                )

