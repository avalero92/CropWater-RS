"""Built-in Kc–NDVI catalogue; original 1.0.1 values and defaults."""
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


# Common metadata schema for direct Kc-NDVI relationships.
# Calibration ranges remain blank until verified against each primary paper.
for _kc_meta in KC_CATALOG.values():
    _kc_meta.setdefault("kc_type", "Kc")
    _kc_meta.setdefault("sensor", "Not specified")
    _kc_meta.setdefault("study_region", _kc_meta.get("scope", "Not specified"))
    _kc_meta.setdefault("r2", None)
    _kc_meta.setdefault("ndvi_min", None)
    _kc_meta.setdefault("ndvi_max", None)
    _kc_meta.setdefault("kc_min", None)
    _kc_meta.setdefault("kc_max", None)
    _kc_meta.setdefault(
        "calibration_note",
        "Calibration domain not encoded yet; verify against the primary publication."
    )
    _kc_meta.setdefault("source_type", "built-in")
    _kc_meta.setdefault("verification_status", "not specified")


