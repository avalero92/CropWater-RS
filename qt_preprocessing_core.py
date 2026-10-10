"""Pure preprocessing logic for parcel NDVI statistical observations."""
import numpy as np
import pandas as pd

REQUIRED = {"parcel_id", "date_start", "ndvi_p50"}

def quality_control(frame, min_valid_pct=50.0, min_samples=1):
    """Return annotated observations and a per-parcel QC summary.

    Duplicated dates are flagged, not silently discarded. Raw values remain unchanged.
    """
    if not 0 <= min_valid_pct <= 100:
        raise ValueError("Minimum valid fraction must be between 0 and 100%")
    if min_samples < 1: raise ValueError("Minimum sample count must be at least 1")
    missing=REQUIRED-set(frame.columns)
    if missing: raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    if frame.empty: raise ValueError("The input table is empty")
    out=frame.copy()
    out["date_start"]=pd.to_datetime(out["date_start"],utc=True,errors="coerce")
    out["ndvi_p50"]=pd.to_numeric(out["ndvi_p50"],errors="coerce")
    out["parcel_id"]=out["parcel_id"].astype("string").str.strip()
    has_date=out["date_start"].notna()
    has_parcel=out["parcel_id"].notna() & out["parcel_id"].ne("")
    has_ndvi=np.isfinite(out["ndvi_p50"].to_numpy(dtype=float))
    valid_range=has_ndvi & out["ndvi_p50"].between(-1,1).to_numpy()
    if "valid_fraction_pct" in out:
        valid_fraction=pd.to_numeric(out["valid_fraction_pct"],errors="coerce")
        valid_fraction_ok=valid_fraction.between(min_valid_pct,100).fillna(False)
    else:
        valid_fraction_ok=pd.Series(True,index=out.index)
    if "sample_count" in out:
        sample_count=pd.to_numeric(out["sample_count"],errors="coerce")
        sample_ok=sample_count.ge(min_samples).fillna(False)
    else:
        sample_ok=pd.Series(True,index=out.index)
    # Detect exact same parcel and calendar date; invalid dates are handled separately.
    day=out["date_start"].dt.normalize()
    duplicates=pd.DataFrame({"parcel":out["parcel_id"],"day":day}).duplicated(keep="first") & has_date & has_parcel
    reasons=[]
    for i in range(len(out)):
        r=[]
        if not has_parcel.iloc[i]:r.append("missing_parcel")
        if not has_date.iloc[i]:r.append("invalid_date")
        if not valid_range[i]:r.append("invalid_ndvi")
        if not bool(valid_fraction_ok.iloc[i]):r.append("low_valid_fraction")
        if not bool(sample_ok.iloc[i]):r.append("insufficient_samples")
        if bool(duplicates.iloc[i]):r.append("duplicate_date")
        reasons.append(";".join(r))
    out["qc_reason"]=reasons
    out["accepted"]=out["qc_reason"].eq("")
    out=out.sort_values(["parcel_id","date_start"],kind="stable",na_position="last").reset_index(drop=True)
    summary=(out.groupby("parcel_id",dropna=False).agg(observations=("accepted","size"),accepted=("accepted","sum"))
             .reset_index())
    summary["rejected"]=summary["observations"]-summary["accepted"]
    return out,summary
