"""Walk-forward backtest + persisted track record (decision-grade Wave A).

For every post-train-cutoff map (genuine out-of-sample), record the prediction the
model *would* have made pre-match, the calibrated probability, the outcome, and a
**confidence tier** — then persist to ``prediction_log`` so the API/dashboard can
show an honest track record without recomputing, and so forward performance accrues.

The headline accuracy is capped (~57% broad / ~50% elite — intrinsic), so the real
output is the **regime map**: where the model is *sharp* (big Elo gaps, regional)
vs a *coinflip* (elite, evenly-matched). Decisions should only trust the sharp
regimes. Reuses ``models.calibration.holdout_frame`` (one model load).

Usage:
    python -m models.backtest --db data/prx.db
"""

import argparse
import math
import sqlite3

import numpy as np

from models import calibration

DB_DEFAULT = "data/prx.db"

PREDICTION_LOG_DDL = """
CREATE TABLE IF NOT EXISTS prediction_log (
    map_id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL,
    date_utc TEXT NOT NULL,
    tier TEXT,
    elo_diff REAL,
    team1_win_prob REAL NOT NULL,        -- calibrated P(team1 wins the map)
    team1_won INTEGER NOT NULL,
    correct INTEGER NOT NULL,            -- (prob>0.5) == team1_won
    confidence TEXT NOT NULL             -- 'sharp' | 'lean' | 'coinflip'
)
"""

# Confidence tiers, grounded in the backtest (see module CLI): the model essentially
# *is* Elo, so |elo_diff| is the real signal; elite events (top, evenly-matched teams)
# are coinflips even at moderate gaps.
_SHARP_ELO = 150.0
_LEAN_ELO = 75.0
_ELITE = {"Masters", "Champions"}


def confidence_tier(elo_diff, tier):
    a = abs(elo_diff or 0.0)
    if tier in _ELITE and a < _SHARP_ELO:
        return "coinflip" if a < _LEAN_ELO else "lean"
    if a >= _SHARP_ELO:
        return "sharp"
    if a >= _LEAN_ELO:
        return "lean"
    return "coinflip"


def _logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _metrics(p, y, elo):
    p, y, elo = np.asarray(p), np.asarray(y), np.asarray(elo)
    return {
        "n": int(len(p)),
        "acc": float(((p > 0.5).astype(int) == y).mean()),
        "elo_sign_acc": float(((elo > 0).astype(int) == y).mean()),
        "brier": calibration.brier(p, y),
        "logloss": _logloss(p, y),
    }


def run(db_path=DB_DEFAULT):
    """Build the post-cutoff prediction set, write prediction_log, return the frame."""
    post = calibration.holdout_frame(db_path)
    post["p_cal"] = [calibration.calibrate(x) for x in post["p"]]  # identity unless a map is fit
    post["correct"] = ((post["p_cal"] > 0.5).astype(int) == post["team1_won"]).astype(int)
    post["confidence"] = [confidence_tier(e, t) for e, t in zip(post["elo_diff"], post["tier"])]

    conn = sqlite3.connect(db_path)
    conn.execute(PREDICTION_LOG_DDL)
    conn.execute("DELETE FROM prediction_log")
    conn.executemany(
        "INSERT INTO prediction_log (map_id, match_id, date_utc, tier, elo_diff, "
        "team1_win_prob, team1_won, correct, confidence) VALUES (?,?,?,?,?,?,?,?,?)",
        [(int(r.map_id), int(r.match_id), r.date_utc, r.tier, float(r.elo_diff),
          float(r.p_cal), int(r.team1_won), int(r.correct), r.confidence)
         for r in post.itertuples()],
    )
    conn.commit()
    conn.close()
    return post


def _print_report(post):
    p, y, elo = post["p_cal"].to_numpy(), post["team1_won"].to_numpy(), post["elo_diff"].to_numpy()
    o = _metrics(p, y, elo)
    print(f"[bt] ALL post-cutoff n={o['n']} | acc={o['acc']:.4f} "
          f"elo-sign={o['elo_sign_acc']:.4f} brier={o['brier']:.4f} logloss={o['logloss']:.4f}")

    print("[bt] by tier:")
    for tier, g in post.groupby("tier"):
        m = _metrics(g["p_cal"], g["team1_won"], g["elo_diff"])
        print(f"[bt]   {tier:16} n={m['n']:4} acc={m['acc']:.4f} elo={m['elo_sign_acc']:.4f} "
              f"brier={m['brier']:.4f}")

    print("[bt] by |elo_diff| bucket (the real signal):")
    edges = [0, 50, 100, 150, 250, 1e9]
    labels = ["0-50", "50-100", "100-150", "150-250", "250+"]
    a = post["elo_diff"].abs()
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        g = post[(a >= lo) & (a < hi)]
        if len(g):
            m = _metrics(g["p_cal"], g["team1_won"], g["elo_diff"])
            print(f"[bt]   |elo| {lab:8} n={m['n']:4} acc={m['acc']:.4f} brier={m['brier']:.4f}")

    print("[bt] by confidence tier (what decisions key off):")
    for conf, g in post.groupby("confidence"):
        m = _metrics(g["p_cal"], g["team1_won"], g["elo_diff"])
        print(f"[bt]   {conf:9} n={m['n']:4} acc={m['acc']:.4f} brier={m['brier']:.4f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_DEFAULT)
    args = ap.parse_args()
    post = run(args.db)
    _print_report(post)
    print(f"[bt] wrote prediction_log ({len(post)} rows)")


if __name__ == "__main__":
    main()
