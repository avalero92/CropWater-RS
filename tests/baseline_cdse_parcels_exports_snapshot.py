# Literal, AST-extracted methods from cropwater_rs.py v1.0.1. DO NOT EDIT.
import logging, json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
APP_VERSION = "1.0.1"
CROP_ALIASES = {
    "BARLEY": "BARLEY",
    "CEBADA": "BARLEY",
    "WHEAT": "WHEAT",
    "TRIGO": "WHEAT",
    "TRIGO BLANDO": "WHEAT",
    "TRIGO DURO": "WHEAT",
    "MAIZE": "MAIZE",
    "CORN": "MAIZE",
    "MAIZ": "MAIZE",
    "MAÍZ": "MAIZE",
    "PEA": "PEA",
    "PEAS": "PEA",
    "GUISANTE": "PEA",
    "GUISANTES": "PEA",
    "SUNFLOWER": "SUNFLOWER",
    "GIRASOL": "SUNFLOWER",
    "SOYBEAN": "SOYBEAN",
    "SOY": "SOYBEAN",
    "SOJA": "SOYBEAN",
    "ALFALFA": "ALFALFA",
    "COTTON": "COTTON",
    "ALGODON": "COTTON",
    "ALGODÓN": "COTTON",
    "RICE": "RICE",
    "ARROZ": "RICE",
    "POTATO": "POTATO",
    "POTATOES": "POTATO",
    "PATATA": "POTATO",
    "PATATAS": "POTATO",
    "OTHER": "OTHER",
    "OTRO": "OTHER",
    "OTROS": "OTHER",
}
KC_CATALOG = {
    "kamble_2013_general": {
        "label": "Kamble et al. (2013) — General",
        "crops": ["ALL"],
        "equation": "Kc = 1.457 × NDVI - 0.1725",
        "a": 1.457,
        "b": -0.1725,
        "reference": "Kamble, Kilic & Hubbard (2013), Remote Sensing 5:1588–1602",
        "doi": "10.3390/rs5041588",
        "scope": "General agricultural relationship; MODIS/AmeriFlux, Nebraska, USA",
    },
    "gontia_tiwari_2010_wheat": {
        "label": "Gontia & Tiwari (2010) — Wheat",
        "crops": ["WHEAT"],
        "equation": "Kc = 2.7109 × NDVI + 0.424",
        "a": 2.7109,
        "b": 0.424,
        "reference": "Gontia & Tiwari (2010), Water Resources Management 24:1399–1414",
        "doi": "10.1007/s11269-009-9505-3",
        "scope": "Wheat; IRS-P6; India; KcFAO relationship",
    },
    "rocha_2012_maize": {
        "label": "Rocha et al. (2012) — Maize",
        "crops": ["MAIZE"],
        "equation": "Kc = 1.37 × NDVI - 0.017",
        "a": 1.37,
        "b": -0.017,
        "reference": "Rocha et al. (2012) — maize relationship reported in later scientific syntheses",
        "doi": "",
        "scope": "Maize; Portugal",
    },
    "singh_irmak_2009_soybean": {
        "label": "Singh & Irmak (2009) — Soybean",
        "crops": ["SOYBEAN"],
        "equation": "Kc = 1.217 × NDVI - 0.034",
        "a": 1.217,
        "b": -0.034,
        "reference": "Singh & Irmak (2009) — soybean relationship",
        "doi": "",
        "scope": "Soybean; USA",
    },
    "reyes_2015_alfalfa": {
        "label": "Reyes-González et al. (2015) — Alfalfa",
        "crops": ["ALFALFA"],
        "equation": "Kc = 2.112 × NDVI - 0.4989",
        "a": 2.112,
        "b": -0.4989,
        "reference": "Reyes-González et al. (2015) — alfalfa relationship",
        "doi": "",
        "scope": "Alfalfa; Mexico",
    },
    "rossi_2010_rice": {
        "label": "Rossi et al. (2010) — Rice",
        "crops": ["RICE"],
        "equation": "Kc = 0.206 × NDVI + 1.076",
        "a": 0.206,
        "b": 1.076,
        "reference": "Rossi et al. (2010) — rice relationship reported in later scientific syntheses",
        "doi": "",
        "scope": "Rice; MODIS",
    },
}

class BaselineV4Methods:
    def _build_spatial_export_gdf(self):
        if self.gdf is None or self.gdf.empty:
            raise ValueError("No parcels are loaded.")

        out = self.gdf.copy()
        ndvi_mean, ndvi_last = [], []
        kc_mean, kc_last, kc_model = [], [], []
        cwr_total, iwr_total = [], []

        for _, row in out.iterrows():
            pid = str(row["parcel_id"])

            raw = self.ndvi_results.get(pid)
            if raw is not None and not raw.empty:
                accepted = raw.loc[
                    raw["accepted"] & raw["ndvi_p50"].notna(),
                    "ndvi_p50",
                ]
                ndvi_mean.append(float(accepted.mean()) if len(accepted) else np.nan)
                ndvi_last.append(float(accepted.iloc[-1]) if len(accepted) else np.nan)
            else:
                ndvi_mean.append(np.nan)
                ndvi_last.append(np.nan)

            kdf = self.kc_results.get(pid)
            if kdf is not None and not kdf.empty:
                kc_mean.append(float(kdf["Kc"].mean()))
                kc_last.append(float(kdf["Kc"].iloc[-1]))
            else:
                kc_mean.append(np.nan)
                kc_last.append(np.nan)

            mid = self.kc_assignments.get(pid)
            kc_model.append(KC_CATALOG[mid]["label"] if mid in KC_CATALOG else "")

            wdf = self.water_results.get(pid)
            if wdf is not None and not wdf.empty:
                cwr_total.append(float(wdf["ETc"].sum()))
                iwr_total.append(
                    float(wdf["IWR_net"].sum()) if "IWR_net" in wdf.columns else np.nan
                )
            else:
                cwr_total.append(np.nan)
                iwr_total.append(np.nan)

        out["ndvi_p50_mean"] = ndvi_mean
        out["ndvi_p50_last"] = ndvi_last
        out["kc_mean"] = kc_mean
        out["kc_last"] = kc_last
        out["kc_model"] = kc_model
        out["cwr_total_mm"] = cwr_total
        out["iwr_net_total_mm"] = iwr_total
        out["app_version"] = APP_VERSION
        return out
    @staticmethod
    def _find_column_case_insensitive(columns, candidates):
        """Return the first matching source column, ignoring case/whitespace."""
        lookup = {
            str(col).strip().casefold(): col
            for col in columns
        }
        for candidate in candidates:
            hit = lookup.get(str(candidate).strip().casefold())
            if hit is not None:
                return hit
        return None
    @staticmethod
    def _normalize_crop_name(value):
        """Normalize input crop labels to CropWater-RS controlled vocabulary."""
        if pd.isna(value):
            return "OTHER"

        raw = str(value).strip()
        if not raw:
            return "OTHER"

        # Normalize repeated spaces and uppercase before alias lookup.
        normalized = " ".join(raw.upper().split())
        return CROP_ALIASES.get(normalized, "OTHER")
    def _prepare_vector_attributes(
        self,
        gdf,
        id_field="<Auto>",
        crop_field="<Manual / OTHER>",
    ):
        """
        Prepare stable internal parcel ID and crop fields.

        ``id_field`` may be <Auto>, <Generate>, or a source attribute.
        ``crop_field`` may be <Auto>, <Manual / OTHER>, or a source attribute.

        Source crop text is retained in ``crop_source``. Internal crop labels
        are normalized to the CropWater-RS controlled vocabulary.
        """
        columns = list(gdf.columns)

        # -------------------------
        # ID field
        # -------------------------
        if id_field == "<Generate>":
            id_col = None
        elif id_field == "<Auto>":
            id_col = self._find_column_case_insensitive(
                columns,
                ["parcel_id", "ID"],
            )
        else:
            id_col = id_field if id_field in columns else None
            if id_col is None:
                raise ValueError(
                    f"Selected ID field '{id_field}' is not present in the vector layer."
                )

        if id_col is None:
            gdf["parcel_id"] = [
                f"P{i+1:05d}" for i in range(len(gdf))
            ]
            id_note = "Generated sequential parcel IDs"
        else:
            raw_ids = gdf[id_col].copy()
            ids = raw_ids.astype("string").str.strip()

            missing = (
                ids.isna()
                | (ids == "")
                | (ids.str.lower() == "nan")
                | (ids.str.lower() == "<na>")
            )

            if missing.any():
                used = set(
                    ids[~missing]
                    .astype(str)
                    .tolist()
                )
                counter = 1
                for idx in gdf.index[missing]:
                    while True:
                        candidate = f"P{counter:05d}"
                        counter += 1
                        if candidate not in used:
                            break
                    ids.loc[idx] = candidate
                    used.add(candidate)

            gdf["parcel_id"] = ids.astype(str)
            id_note = f"Parcel IDs imported from '{id_col}'"

        # -------------------------
        # Crop field
        # -------------------------
        if crop_field == "<Manual / OTHER>":
            crop_col = None
        elif crop_field == "<Auto>":
            crop_col = self._find_column_case_insensitive(
                columns,
                ["crop", "CROPS"],
            )
        else:
            crop_col = crop_field if crop_field in columns else None
            if crop_col is None:
                raise ValueError(
                    f"Selected crop field '{crop_field}' is not present in the vector layer."
                )

        if crop_col is None:
            gdf["crop_source"] = ""
            gdf["crop"] = "OTHER"
            crop_note = "Manual crop labelling selected"
        else:
            source_crop = (
                gdf[crop_col]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            gdf["crop_source"] = source_crop
            gdf["crop"] = gdf[crop_col].apply(
                self._normalize_crop_name
            )
            crop_note = f"Crop labels imported from '{crop_col}'"

        return gdf, id_note, crop_note
    @staticmethod
    def _stats_response_to_df(response):
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
    def _build_run_metadata(self):
        meta = {
            "app_version": APP_VERSION,
            "satellite_product": "Sentinel-2 L2A",
            "spatial_resolution_m": 10,
            "parcel_statistic": "P50",
            "scl_excluded_classes": "0,1,3,8,9,10,11",
            "date_start": self.start_var.get() if hasattr(self, "start_var") else "",
            "date_end": self.end_var.get() if hasattr(self, "end_var") else "",
            "aggregation_interval": self.interval_var.get() if hasattr(self, "interval_var") else "",
            "minimum_valid_fraction_percent": self.valid_pct_var.get() if hasattr(self, "valid_pct_var") else "",
            "temporal_method": self.temporal_method_var.get() if hasattr(self, "temporal_method_var") else "",
            "whittaker_lambda": self.whittaker_lambda_var.get() if hasattr(self, "whittaker_lambda_var") else "",
            "sg_window_days": self.sg_window_var.get() if hasattr(self, "sg_window_var") else "",
            "temporal_output_resolution": self.output_resolution_var.get() if hasattr(self, "output_resolution_var") else "",
            "constrain_ndvi_0_1": self.constrain_ndvi_var.get() if hasattr(self, "constrain_ndvi_var") else "",
            "kc_ndvi_source": self.kc_ndvi_source_var.get() if hasattr(self, "kc_ndvi_source_var") else "",
            "kc_nonnegative_constraint": self.kc_clip_var.get() if hasattr(self, "kc_clip_var") else "",
            "water_mode": self.water_mode_var.get() if hasattr(self, "water_mode_var") else "",
            "meteorological_file": self.meteo_file or "",
            "generated_at": pd.Timestamp.now().isoformat(),
            "software_author": self.software_metadata.get("author", ""),
            "software_orcid": self.software_metadata.get("orcid", ""),
            "software_repository": self.software_metadata.get("repository_url", ""),
            "software_doi": self.software_metadata.get("zenodo_doi", ""),
            "software_license": self.software_metadata.get("license", "GPL-3.0"),
            "iwr_definition": "daily max(ETc - Pe, 0); simplified net requirement",
            "quant_reference": "French et al. (2023), Agricultural Water Management 290, 108582",
            "quant_doi": "10.1016/j.agwat.2023.108582",
            "quant_q1_percent": self.quant_q1_var.get() if hasattr(self, "quant_q1_var") else "",
            "quant_q2_percent": self.quant_q2_var.get() if hasattr(self, "quant_q2_var") else "",
            "quant_q3_percent": self.quant_q3_var.get() if hasattr(self, "quant_q3_var") else "",
            "quant_q4_percent": self.quant_q4_var.get() if hasattr(self, "quant_q4_var") else "",
        }
        self.run_metadata = meta
        return meta
    def _write_analysis_summary(self, outdir):
        outdir = Path(outdir)
        meta = self._build_run_metadata()
        lines = [
            f"CropWater-RS v{APP_VERSION}",
            "=" * 48,
            "",
            f"Generated: {meta.get('generated_at', '')}",
            f"Author: {self.software_metadata.get('author', '')}",
            f"License: {self.software_metadata.get('license', '')}",
            "",
            "Scientific workflow",
            "-------------------",
            "Sentinel-2 L2A -> parcel NDVI -> temporal reconstruction -> "
            "direct literature Kc-NDVI -> ETc/CWR -> optional simplified net IWR",
            "",
        ]

        if self.gdf is not None:
            lines.extend([f"Parcels: {len(self.gdf)}", ""])

        lines.extend(["Processing parameters", "---------------------"])
        for k, v in meta.items():
            lines.append(f"{k}: {v}")

        if self.gdf is not None and not self.gdf.empty:
            lines.extend(["", "Parcel results", "--------------"])
            for _, row in self.gdf.iterrows():
                pid = str(row["parcel_id"])
                line = f"{pid} | crop={row['crop']} | area={row['area_ha']:.2f} ha"
                kdf = self.kc_results.get(pid)
                if kdf is not None and not kdf.empty:
                    line += f" | mean Kc={float(kdf['Kc'].mean()):.3f}"
                wdf = self.water_results.get(pid)
                if wdf is not None and not wdf.empty:
                    line += f" | CWR={float(wdf['ETc'].sum()):.1f} mm"
                    if "IWR_net" in wdf.columns:
                        line += f" | net IWR={float(wdf['IWR_net'].sum()):.1f} mm"
                lines.append(line)

        (outdir / "analysis_summary.txt").write_text("\n".join(lines), encoding="utf-8")
    def _write_spatial_export_to_folder(self, outdir):
        if self.gdf is None or self.gdf.empty:
            return
        try:
            spatial = self._build_spatial_export_gdf()
            spatial.to_file(
                Path(outdir) / "CropWater_RS_results.gpkg",
                layer="cropwater_results",
                driver="GPKG",
            )
        except Exception:
            logging.exception("Automatic GeoPackage export failed")
    def _write_quant_export_to_folder(self, outdir):
        if not self.quant_results:
            return
        try:
            qdf = self._quant_export_dataframe()
            qdf.to_csv(
                Path(outdir) / "QUANT_phenology_all_parcels.csv",
                index=False,
            )
        except Exception:
            logging.exception("Automatic QUANT export failed")
    def export_water_results(self):
        if not self.kc_results:
            messagebox.showwarning(
                "Export",
                "There are no Kc results to export.",
            )
            return

        folder = filedialog.askdirectory(
            title="Select output folder for Kc / CWR / IWR results"
        )
        if not folder:
            return

        outdir = Path(folder)
        try:
            # Kc
            kc_frames = []
            kc_dir = outdir / "Kc_by_parcel"
            kc_dir.mkdir(exist_ok=True)

            for pid, df in self.kc_results.items():
                if df is None or df.empty:
                    continue
                safe = str(pid).replace("/", "_").replace("\\", "_")
                df.to_csv(kc_dir / f"{safe}_Kc.csv", index=False)
                kc_frames.append(df)

            if kc_frames:
                pd.concat(kc_frames, ignore_index=True).to_csv(
                    outdir / "Kc_all_parcels.csv",
                    index=False,
                )

            # Water results only if calculated
            water_frames = []
            if self.water_results:
                water_dir = outdir / "Water_by_parcel"
                water_dir.mkdir(exist_ok=True)

                for pid, df in self.water_results.items():
                    if df is None or df.empty:
                        continue
                    safe = str(pid).replace("/", "_").replace("\\", "_")
                    df.to_csv(
                        water_dir / f"{safe}_CWR_IWR.csv",
                        index=False,
                    )
                    water_frames.append(df)

                if water_frames:
                    water_all = pd.concat(water_frames, ignore_index=True)
                    combined_name = (
                        "CWR_IWR_all_parcels.csv"
                        if "IWR_net" in water_all.columns
                        else "CWR_all_parcels.csv"
                    )
                    water_all.to_csv(
                        outdir / combined_name,
                        index=False,
                    )

            # Model assignments for reproducibility
            assignments = []
            if self.gdf is not None:
                for _, row in self.gdf.iterrows():
                    pid = str(row["parcel_id"])
                    mid = self.kc_assignments.get(pid)
                    if mid in KC_CATALOG:
                        m = KC_CATALOG[mid]
                        assignments.append({
                            "parcel_id": pid,
                            "crop": row["crop"],
                            "Kc_model_id": mid,
                            "Kc_model": m["label"],
                            "equation": m["equation"],
                            "reference": m["reference"],
                            "doi": m.get("doi", ""),
                            "scope": m.get("scope", ""),
                            "kc_type": m.get("kc_type", "Kc"),
                            "sensor": m.get("sensor", ""),
                            "study_region": m.get("study_region", ""),
                            "r2": m.get("r2", ""),
                            "ndvi_min": m.get("ndvi_min", ""),
                            "ndvi_max": m.get("ndvi_max", ""),
                            "kc_min": m.get("kc_min", ""),
                            "kc_max": m.get("kc_max", ""),
                            "calibration_note": m.get("calibration_note", ""),
                            "source_type": m.get("source_type", ""),
                            "verification_status": m.get("verification_status", ""),
                        })
            if assignments:
                pd.DataFrame(assignments).to_csv(
                    outdir / "Kc_model_assignments.csv",
                    index=False,
                )

            meta = self._build_run_metadata()
            pd.DataFrame(
                [{"parameter": k, "value": v} for k, v in meta.items()]
            ).to_csv(outdir / "run_metadata.csv", index=False)

            if self.temporal_quality:
                pd.DataFrame([
                    {
                        "parcel_id": pid,
                        "n_accepted": q.get("n_accepted"),
                        "longest_gap_days": q.get("longest_gap_days"),
                    }
                    for pid, q in self.temporal_quality.items()
                ]).to_csv(
                    outdir / "temporal_quality_summary.csv",
                    index=False,
                )

            self._write_spatial_export_to_folder(outdir)
            self._write_quant_export_to_folder(outdir)
            self._write_analysis_summary(outdir)

            msg = f"Export completed.\n\nFolder:\n{outdir}\n\nKc series: {len(kc_frames)}"
            if water_frames:
                msg += f"\nCWR/IWR series: {len(water_frames)}"
            else:
                msg += "\nCWR/IWR series: not calculated"

            messagebox.showinfo("Export Kc / CWR / IWR", msg)

        except Exception as exc:
            messagebox.showerror("Export Kc / CWR / IWR", str(exc))
    def export_all_results(self):
        """Export raw/QA and processed NDVI results for all parcels."""
        if not self.ndvi_results:
            messagebox.showwarning(
                "Export all",
                "There are no NDVI results to export yet.",
            )
            return

        folder = filedialog.askdirectory(
            title="Select output folder for all NDVI results"
        )
        if not folder:
            return

        outdir = Path(folder)

        try:
            # 1) Combined RAW/QA dataset for all parcels
            raw_frames = []
            for parcel_id, df in self.ndvi_results.items():
                if df is None or df.empty:
                    continue
                tmp = df.copy()
                if "parcel_id" not in tmp.columns:
                    tmp["parcel_id"] = parcel_id
                raw_frames.append(tmp)

            if raw_frames:
                raw_all = pd.concat(raw_frames, ignore_index=True)
                raw_all.to_csv(
                    outdir / "NDVI_all_parcels_raw.csv",
                    index=False,
                )

            # 2) Individual RAW/QA file for each parcel
            raw_dir = outdir / "raw_by_parcel"
            raw_dir.mkdir(exist_ok=True)

            for parcel_id, df in self.ndvi_results.items():
                if df is None or df.empty:
                    continue
                safe_id = str(parcel_id).replace("/", "_").replace("\\", "_")
                df.to_csv(
                    raw_dir / f"{safe_id}_NDVI_raw.csv",
                    index=False,
                )

            # 3) Processed datasets, only if temporal processing exists
            processed_count = 0
            if self.temporal_results:
                proc_dir = outdir / "processed_by_parcel"
                proc_dir.mkdir(exist_ok=True)

                processed_frames = []
                daily_frames = []

                for parcel_id, result in self.temporal_results.items():
                    if not result:
                        continue

                    safe_id = str(parcel_id).replace("/", "_").replace("\\", "_")
                    method = result.get("method", "Unknown")

                    # User-selected output resolution
                    output_df = result.get("output")
                    if output_df is not None and not output_df.empty:
                        tmp = output_df.copy()
                        tmp["parcel_id"] = parcel_id
                        tmp["method"] = method
                        processed_frames.append(tmp)

                        tmp.to_csv(
                            proc_dir / f"{safe_id}_NDVI_processed.csv",
                            index=False,
                        )
                        processed_count += 1

                    # Always preserve the internal daily reconstruction separately
                    daily_df = result.get("daily")
                    if daily_df is not None and not daily_df.empty:
                        tmp_daily = daily_df.copy()
                        tmp_daily["parcel_id"] = parcel_id
                        tmp_daily["method"] = method
                        daily_frames.append(tmp_daily)

                        tmp_daily.to_csv(
                            proc_dir / f"{safe_id}_NDVI_daily_internal.csv",
                            index=False,
                        )

                if processed_frames:
                    pd.concat(processed_frames, ignore_index=True).to_csv(
                        outdir / "NDVI_all_parcels_processed.csv",
                        index=False,
                    )

                if daily_frames:
                    pd.concat(daily_frames, ignore_index=True).to_csv(
                        outdir / "NDVI_all_parcels_daily_internal.csv",
                        index=False,
                    )

            # 4) Export a compact summary of parcel metadata
            if self.gdf is not None and not self.gdf.empty:
                summary_cols = [
                    c for c in ["parcel_id", "crop", "area_ha"]
                    if c in self.gdf.columns
                ]
                if summary_cols:
                    self.gdf[summary_cols].to_csv(
                        outdir / "parcel_summary.csv",
                        index=False,
                    )

            meta = self._build_run_metadata()
            pd.DataFrame(
                [{"parameter": k, "value": v} for k, v in meta.items()]
            ).to_csv(outdir / "run_metadata.csv", index=False)

            if self.temporal_quality:
                pd.DataFrame([
                    {
                        "parcel_id": pid,
                        "n_accepted": q.get("n_accepted"),
                        "longest_gap_days": q.get("longest_gap_days"),
                    }
                    for pid, q in self.temporal_quality.items()
                ]).to_csv(
                    outdir / "temporal_quality_summary.csv",
                    index=False,
                )

            self._write_spatial_export_to_folder(outdir)
            self._write_quant_export_to_folder(outdir)
            self._write_analysis_summary(outdir)

            msg = (
                f"Export completed successfully.\n\n"
                f"Folder:\n{outdir}\n\n"
                f"Raw parcel series: {len(raw_frames)}"
            )

            if processed_count:
                msg += f"\nProcessed parcel series: {processed_count}"
            else:
                msg += "\nProcessed parcel series: none"

            messagebox.showinfo("Export all NDVI results", msg)

        except Exception as exc:
            messagebox.showerror(
                "Export all NDVI results",
                str(exc),
            )
