"""Differential tests: original v1.0.1 GUI method vs independent temporal core."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cropwater_rs.core.temporal import process_one_temporal_series
from test_regression_v2 import engine


def observations():
    return pd.DataFrame({
        'date_start': ['2024-01-02T00:00:00Z', '2024-01-07T00:00:00Z',
                       '2024-01-07T12:00:00Z', '2024-01-15T00:00:00Z',
                       '2024-01-20T00:00:00Z'],
        'ndvi_p50': [0.2, 0.6, 0.8, 0.4, 0.3],
        'accepted': [True]*5,
    })


@pytest.mark.parametrize('method', ['Raw observations', 'Linear interpolation', 'Whittaker', 'Savitzky-Golay', 'Kalman'])
@pytest.mark.parametrize('resolution', ['Daily', '5 days', '10 days'])
def test_differential_temporal(method, resolution):
    baseline = engine(resolution=resolution)
    old = baseline._process_one_temporal_series(observations(), method, 10.0, 7)
    new = process_one_temporal_series(observations(), method, 10.0, 7,
                                      '2024-01-01', '2024-01-21', True, resolution)
    assert old['method'] == new['method']
    for key in ['daily', 'output']:
        pd.testing.assert_frame_equal(old[key], new[key], check_exact=False, rtol=1e-12, atol=1e-12)
    assert old['quality'] == new['quality']
    for metric in ['n', 'rmse', 'mae', 'r2']:
        np.testing.assert_allclose(old['diagnostics'][metric], new['diagnostics'][metric], equal_nan=True)


@pytest.mark.parametrize('method', ['Linear interpolation', 'Whittaker', 'Savitzky-Golay', 'Kalman'])
def test_differential_unconstrained(method):
    baseline = engine(constrain=False)
    old = baseline._process_one_temporal_series(observations(), method, 2.0, 8)
    new = process_one_temporal_series(observations(), method, 2.0, 8,
                                      '2024-01-01', '2024-01-21', False, 'Daily')
    pd.testing.assert_frame_equal(old['daily'], new['daily'])


def test_temporal_core_no_gui_import():
    import subprocess
    proc = subprocess.run([sys.executable, '-c', 'import cropwater_rs.core.temporal; import sys; assert "tkinter" not in sys.modules and "sentinelhub" not in sys.modules'], cwd=Path(__file__).resolve().parents[1]/'src', capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
