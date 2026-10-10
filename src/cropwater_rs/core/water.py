"""Original CropWater-RS v1.0.1 water equations, extracted without changes."""
import numpy as np


def calculate_linear_kc(ndvi, a, b, constrain_nonnegative=True):
    """Direct literature relationship Kc = a*NDVI + b."""
    values = np.asarray(ndvi, dtype=float) * float(a) + float(b)
    if constrain_nonnegative:
        values = np.maximum(values, 0.0)
    return values


def calculate_etc(kc, eto):
    """Crop evapotranspiration / CWR in mm d-1."""
    return np.asarray(kc, dtype=float) * np.asarray(eto, dtype=float)


def calculate_net_iwr(etc, pe):
    """Simplified daily net IWR = max(ETc - Pe, 0), in mm d-1."""
    return np.maximum(
        np.asarray(etc, dtype=float) - np.asarray(pe, dtype=float),
        0.0,
    )


