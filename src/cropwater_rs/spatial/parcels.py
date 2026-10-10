"""Parcel attribute preparation preserving v1.0.1 rules."""
import pandas as pd
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

def find_column_case_insensitive(columns,candidates):
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

def normalize_crop_name(value):
    """Normalize input crop labels to CropWater-RS controlled vocabulary."""
    if pd.isna(value):
        return "OTHER"

    raw = str(value).strip()
    if not raw:
        return "OTHER"

    # Normalize repeated spaces and uppercase before alias lookup.
    normalized = " ".join(raw.upper().split())
    return CROP_ALIASES.get(normalized, "OTHER")

def prepare_vector_attributes(gdf,id_field="<Auto>",crop_field="<Manual / OTHER>"):
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
        id_col = find_column_case_insensitive(
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
        crop_col = find_column_case_insensitive(
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
            normalize_crop_name
        )
        crop_note = f"Crop labels imported from '{crop_col}'"

    return gdf, id_note, crop_note
