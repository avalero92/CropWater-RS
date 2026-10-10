"""Meteorological CSV parsing and validation (v1.0.1 behavior)."""
import pandas as pd

def parse_meteorology_csv(path):
    df = pd.read_csv(path, sep=None, engine="python")
    mapping = {str(c).replace("\ufeff", "").strip().lower(): c for c in df.columns}
    if "date" not in mapping or "eto" not in mapping:
        raise ValueError("The CSV must contain at least Date and ETo columns.")
    rename = {mapping["date"]: "Date", mapping["eto"]: "ETo"}
    if "pe" in mapping:
        rename[mapping["pe"]] = "Pe"
    if "parcel_id" in mapping:
        rename[mapping["parcel_id"]] = "parcel_id"
    df = df.rename(columns=rename)
    raw_dates = df["Date"].astype(str).str.strip()
    parsed_dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    iso_mask = raw_dates.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)
    if iso_mask.any():
        parsed_dates.loc[iso_mask] = pd.to_datetime(raw_dates.loc[iso_mask], format="%Y-%m-%d", errors="coerce")
    dmy_mask = raw_dates.str.match(r"^\d{1,2}/\d{1,2}/\d{4}$", na=False)
    if dmy_mask.any():
        parsed_dates.loc[dmy_mask] = pd.to_datetime(raw_dates.loc[dmy_mask], format="%d/%m/%Y", errors="coerce")
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        examples = ", ".join(raw_dates.loc[invalid_dates].head(5).astype(str).tolist())
        raise ValueError("Some Date values could not be parsed. Accepted formats are YYYY-MM-DD and DD/MM/YYYY." + (f" Examples: {examples}" if examples else ""))
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
    high_pe_n = int((df["Pe"] > 200).sum()) if "Pe" in df.columns else 0
    subset = ["Date"] + (["parcel_id"] if "parcel_id" in df.columns else [])
    if df.duplicated(subset=subset).any():
        raise ValueError("Duplicate meteorological records detected for Date" + (" + parcel_id." if "parcel_id" in df.columns else "."))
    if "parcel_id" in df.columns:
        df["parcel_id"] = df["parcel_id"].astype(str)
    return df.sort_values(subset).reset_index(drop=True), high_eto_n, high_pe_n
