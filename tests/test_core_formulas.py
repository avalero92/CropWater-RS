import importlib.util
from pathlib import Path
import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "cropwater_rs.py"
spec = importlib.util.spec_from_file_location("cropwater_rs", MODULE_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

def test_linear_kc():
    result = app.calculate_linear_kc(np.array([0.2, 0.5, 0.8]), 1.25, 0.1, True)
    np.testing.assert_allclose(result, [0.35, 0.725, 1.10])

def test_etc():
    np.testing.assert_allclose(
        app.calculate_etc(np.array([0.5, 1.0]), np.array([4.0, 5.0])),
        [2.0, 5.0],
    )

def test_net_iwr():
    np.testing.assert_allclose(
        app.calculate_net_iwr(np.array([2.0, 5.0]), np.array([0.5, 6.0])),
        [1.5, 0.0],
    )
