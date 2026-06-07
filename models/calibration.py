"""Probability recalibration for the pre-match map model (decision-grade Wave A).

The Bambi model is mildly mis-calibrated — a stated "70%" isn't exactly 70%
empirically, which is fatal for any EV/edge decision. Fit a **monotonic isotonic**
map ``p -> p_calibrated`` on the post-train-cutoff window and persist it
(``models/saved/calibration.json``) as piecewise-linear breakpoints, applied with
``np.interp`` (no pickle). ``calibrate(p)`` is the identity until a map is fit.

To report honestly (not in-sample), the CLI fits on the earlier 60% of the holdout
and measures Brier/ECE on the later 40%; the saved production map is refit on the
full holdout (most data, applied to future matches). Reuses the batch-prediction
approach from ``notebooks/02_model_validation.py``.

Usage:
    python -m models.calibration --db data/prx.db
"""

import argparse
import json
import os
import sqlite3

import numpy as np

DB_DEFAULT = "data/prx.db"
SAVE_PATH = "models/saved/calibration.json"
_CACHE = {}  # path -> (x, y) breakpoints, or None if no map at that path


def holdout_frame(db_path):
    """Post-train-cutoff maps with the model's raw prob ``p`` + outcome ``team1_won``."""
    import arviz as az

    import models.bayes_logistic as bl
    from models.training_data import build_training_data

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    df = build_training_data(conn)
    conn.close()
    post = df[df["date_utc"] > bl.TRAIN_CUTOFF].copy().sort_values(["date_utc", "map_id"])
    model = bl.build_model(bl.split_train(df))
    idata = az.from_netcdf(bl.SAVE_PATH)
    pred = model.predict(idata, data=post, inplace=False, sample_new_groups=True)
    post["p"] = pred.posterior["p"].mean(("chain", "draw")).values
    return post


def _isotonic(p, y):
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(np.asarray(p, float), np.asarray(y, float))
    return iso


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def ece(p, y, bins=10):
    """Expected calibration error: bin-count-weighted |mean(p) - mean(y)| over bins."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(total / len(p))


def save_map(iso, meta, path=SAVE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"x": np.asarray(iso.X_thresholds_).tolist(),
               "y": np.asarray(iso.y_thresholds_).tolist(), "meta": meta}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    _CACHE.pop(path, None)


def _load(path=SAVE_PATH):
    if path not in _CACHE:
        if not os.path.exists(path):
            _CACHE[path] = None
        else:
            with open(path) as f:
                d = json.load(f)
            _CACHE[path] = (np.asarray(d["x"]), np.asarray(d["y"]))
    return _CACHE[path]


def calibrate(p, *, path=SAVE_PATH):
    """Map a raw model probability to its calibrated value (identity if no map fit)."""
    cal = _load(path)
    if cal is None:
        return float(p) if np.isscalar(p) else np.asarray(p, float)
    x, y = cal
    out = np.interp(p, x, y)
    return float(out) if np.isscalar(p) else out


def main():
    import models.bayes_logistic as bl

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--out", default=SAVE_PATH)
    args = ap.parse_args()

    post = holdout_frame(args.db)
    p, y = post["p"].to_numpy(), post["team1_won"].to_numpy()
    n = len(post)
    cut = int(n * 0.6)

    # Honest eval: fit the map on the earlier 60%, measure on the later 40%.
    iso_eval = _isotonic(p[:cut], y[:cut])
    pe, ye = p[cut:], y[cut:]
    pe_cal = iso_eval.predict(pe)
    print(f"[cal] holdout n={n} (fit {cut} / eval {n - cut}, chronological)")
    print(f"[cal] EVAL (out-of-sample for the calibration map):")
    print(f"[cal]   raw        Brier={brier(pe, ye):.4f}  ECE={ece(pe, ye):.4f}")
    print(f"[cal]   calibrated Brier={brier(pe_cal, ye):.4f}  ECE={ece(pe_cal, ye):.4f}")

    print("[cal] raw calibration by tier (all post-cutoff):")
    for tier, g in post.groupby("tier"):
        gp, gy = g["p"].to_numpy(), g["team1_won"].to_numpy()
        print(f"[cal]   {tier:16} n={len(g):4} Brier={brier(gp, gy):.4f} "
              f"ECE={ece(gp, gy):.4f} mean_p={gp.mean():.3f} base={gy.mean():.3f}")

    # Only persist a recalibration map if it *demonstrably* improves out-of-sample
    # Brier. The model is already near-calibrated globally, so forcing an isotonic map
    # tends to overfit and hurt — in which case calibrate() stays the identity (honest:
    # don't manufacture confidence). The regime table above is the real deliverable.
    if brier(pe_cal, ye) < brier(pe, ye) - 1e-3:
        iso_full = _isotonic(p, y)
        save_map(iso_full, {"n_fit": n, "train_cutoff": bl.TRAIN_CUTOFF,
                            "eval_brier_raw": brier(pe, ye),
                            "eval_brier_calibrated": brier(pe_cal, ye)}, args.out)
        print(f"[cal] recalibration improves OOS Brier -> saved map to {args.out}")
    else:
        if os.path.exists(args.out):
            os.remove(args.out)
        print(f"[cal] model already well-calibrated (overall ECE={ece(p, y):.4f}); "
              f"recalibration does NOT improve OOS Brier -> identity, no map saved")


if __name__ == "__main__":
    main()
