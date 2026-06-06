"""Phase 4 validation — expected vs actual player stats on Masters Toronto 2025.

Applies `models.expected_stats.predict_expected_stats` (match-level recent-form +
opponent-Elo) to every map-resolved player in Masters Toronto 2025 (event 2282,
a time-held-out event) and reports mean absolute error and bias per stat
(ACS/K/D/A), plus an expected-vs-actual ACS scatter. Predictions are point-in-time
(only history before each match feeds them).

Run headless: `python notebooks/03_player_skill_validation.py`
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def __():
    import os
    import sqlite3
    import sys

    sys.path.insert(0, os.getcwd())  # importable when run headless from repo root

    import marimo as mo
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    from models.expected_stats import predict_expected_stats

    conn = sqlite3.connect("data/prx.db")
    HOLDOUT_EVENT = 2282  # Masters Toronto 2025
    STATS = ["acs", "kills", "deaths", "assists"]
    return (HOLDOUT_EVENT, STATS, conn, mo, np, pd, plt, predict_expected_stats)


@app.cell
def __(HOLDOUT_EVENT, conn, pd, predict_expected_stats):
    match_ids = [r[0] for r in conn.execute(
        "SELECT match_id FROM matches WHERE event_id = ? "
        "AND (series_name IS NULL OR series_name NOT LIKE 'Showmatch%') "
        "ORDER BY date_utc", (HOLDOUT_EVENT,)).fetchall()]
    preds = pd.concat([predict_expected_stats(mid, db_path="data/prx.db")
                       for mid in match_ids], ignore_index=True)
    preds = preds[preds["actual_acs"].notna()]
    print(f"[pval] Masters Toronto 2025: {len(match_ids)} matches, "
          f"{len(preds)} player rows | mean n_history={preds['n_history'].mean():.0f}")
    return match_ids, preds


@app.cell
def __(STATS, np, preds):
    print("[pval] -- expected vs actual (per-map averages), all players --")
    metrics = {}
    for _s in STATS:
        err = preds[f"expected_{_s}"] - preds[f"actual_{_s}"]
        mae = float(err.abs().mean())
        bias = float(err.mean())
        metrics[_s] = mae
        print(f"[pval]   {_s:8} MAE={mae:6.2f}  bias={bias:+5.2f}  "
              f"actual_mean={preds[f'actual_{_s}'].mean():6.2f}")
    # ACS focus: the done-when stat.
    estab = preds[preds["n_history"] >= 5]
    print(f"[pval] ACS MAE (n_history>=5, n={len(estab)}): "
          f"{(estab['expected_acs'] - estab['actual_acs']).abs().mean():.2f}")
    return estab, metrics


@app.cell
def __(plt, preds):
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(preds["expected_acs"], preds["actual_acs"], alpha=0.5)
    lo, hi = 80, 320
    ax.plot([lo, hi], [lo, hi], "k--", label="expected = actual")
    ax.set_xlabel("Expected ACS")
    ax.set_ylabel("Actual ACS (match avg)")
    ax.set_title("Expected vs actual ACS — Masters Toronto 2025")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.legend()
    fig
    return (fig,)


@app.cell
def __(metrics, mo, preds):
    mo.md(
        f"**Result.** On Masters Toronto 2025 ({len(preds)} player rows), match-level "
        f"expected stats track actuals with MAE **ACS {metrics['acs']:.1f}**, "
        f"kills {metrics['kills']:.1f}, deaths {metrics['deaths']:.1f}, "
        f"assists {metrics['assists']:.1f}. ACS is at the ±30 done-when floor "
        f"(player ACS is high-variance per the P4.T3 feasibility check). The residuals "
        f"are the over/under-performance signal the expected-vs-actual panel surfaces."
    )
    return


if __name__ == "__main__":
    app.run()
