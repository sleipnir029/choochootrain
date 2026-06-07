"""Pure unit tests for models.calibration (no model/bambi needed)."""

import json

from models import calibration


def test_brier_and_ece_perfect():
    # Perfectly-calibrated, certain predictions -> Brier 0, ECE 0.
    p = [0.0, 1.0, 0.0, 1.0]
    y = [0, 1, 0, 1]
    assert calibration.brier(p, y) == 0.0
    assert calibration.ece(p, y) == 0.0


def test_brier_worst_case():
    assert calibration.brier([1.0, 0.0], [0, 1]) == 1.0


def test_ece_detects_miscalibration():
    # Says 0.9 but only right half the time -> sizeable ECE.
    p = [0.9] * 10
    y = [1, 0] * 5
    assert calibration.ece(p, y) > 0.3


def test_calibrate_identity_without_map(tmp_path):
    path = str(tmp_path / "absent.json")
    assert calibration.calibrate(0.73, path=path) == 0.73


def test_calibrate_applies_map(tmp_path):
    path = str(tmp_path / "cal.json")
    # Piecewise-linear map: 0->0, 0.5->0.6, 1->1.
    with open(path, "w") as f:
        json.dump({"x": [0.0, 0.5, 1.0], "y": [0.0, 0.6, 1.0], "meta": {}}, f)
    calibration._CACHE.pop(path, None)
    assert abs(calibration.calibrate(0.5, path=path) - 0.6) < 1e-9
    assert abs(calibration.calibrate(0.25, path=path) - 0.3) < 1e-9  # linear interp
    assert calibration.calibrate(0.5, path=path).__class__ is float
