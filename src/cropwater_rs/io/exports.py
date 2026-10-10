"""Pure export table preparation; no GUI or file-system side effects."""
import pandas as pd

def metadata_rows(metadata):
    """Preserve v1.0.1 metadata CSV column order and values."""
    return [{"parameter": k, "value": v} for k, v in metadata.items()]

def combined_parcel_frames(results, *, parcel_column="parcel_id", inject_id=False):
    """Combine nonempty frames in insertion order, preserving baseline behavior."""
    frames = []
    for parcel_id, df in results.items():
        if df is None or df.empty:
            continue
        frame = df.copy()
        if inject_id and parcel_column not in frame.columns:
            frame[parcel_column] = parcel_id
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else None

def temporal_quality_rows(quality):
    return [{"parcel_id": pid, "n_accepted": q.get("n_accepted"),
             "longest_gap_days": q.get("longest_gap_days")} for pid, q in quality.items()]

def model_assignment_rows(gdf, assignments, catalog):
    """Build original Kc model provenance columns without GUI dependencies."""
    rows=[]
    if gdf is None:
        return rows
    for _, row in gdf.iterrows():
        pid=str(row["parcel_id"]); mid=assignments.get(pid)
        if mid not in catalog:
            continue
        m=catalog[mid]
        rows.append({"parcel_id":pid,"crop":row["crop"],"Kc_model_id":mid,
          "Kc_model":m["label"],"equation":m["equation"],"reference":m["reference"],
          "doi":m.get("doi",""),"scope":m.get("scope",""),"kc_type":m.get("kc_type","Kc"),
          "sensor":m.get("sensor",""),"study_region":m.get("study_region",""),
          "r2":m.get("r2",""),"ndvi_min":m.get("ndvi_min",""),
          "ndvi_max":m.get("ndvi_max",""),"kc_min":m.get("kc_min",""),
          "kc_max":m.get("kc_max",""),"calibration_note":m.get("calibration_note",""),
          "source_type":m.get("source_type",""),
          "verification_status":m.get("verification_status","")})
    return rows
