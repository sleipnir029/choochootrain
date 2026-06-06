"""Phase 0 baseline — round-winner logistic from side + score-state.

Reframed Phase 0 (docs/DEVIATIONS.md 2026-06-06): no per-round loadout, so this
fits the toolchain (sklearn LogisticRegression, time-aware split, accuracy) on
the round-level features the warehouse DOES have — team1 side, pre-round score
diff, half — predicting whether team1 wins the round. This both validates the
modeling stack end-to-end and seeds the Phase 3 score-state model.

Expectation: near-chance (~51-53%). Loadout (Peng's dominant signal) is
unavailable at round level, so a high round accuracy is NOT expected — the gap
vs Peng's ~60.6% is itself the finding.

Run headless: `python notebooks/01_round_baseline.py`
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def __():
    import sqlite3

    import marimo as mo
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score

    np.random.seed(42)
    conn = sqlite3.connect("data/prx.db")
    return LogisticRegression, accuracy_score, conn, mo, np, pd


@app.cell
def __(conn, pd):
    # One row per round, ordered within each map so we can compute pre-round score.
    df = pd.read_sql(
        """SELECT r.map_id, r.round_number, r.half, r.team1_side,
                  CASE WHEN r.winner_id = m.team1_id THEN 1 ELSE 0 END AS team1_won,
                  m.date_utc
           FROM rounds r
           JOIN maps mp ON mp.map_id = r.map_id
           JOIN matches m ON m.match_id = mp.match_id
           ORDER BY r.map_id, r.round_number""", conn)

    # Pre-round (causal) score state: wins BEFORE the current round.
    prior_rounds = df.groupby("map_id").cumcount()
    t1_prior = df.groupby("map_id")["team1_won"].cumsum() - df["team1_won"]
    t2_prior = prior_rounds - t1_prior
    df["score_diff"] = t1_prior - t2_prior
    df["side_ct"] = (df["team1_side"] == "ct").astype(int)
    df["half_second"] = (df["half"] == "second").astype(int)
    df["half_ot"] = (df["half"] == "ot").astype(int)
    print(f"[baseline] rounds={len(df):,} | base rate(team1_won)={df['team1_won'].mean():.4f}")
    return df,


@app.cell
def __(df):
    # Time-aware split at the MAP level (avoid leaking a map across train/test).
    map_dates = df[["map_id", "date_utc"]].drop_duplicates().sort_values("date_utc")
    cutoff = int(len(map_dates) * 0.70)
    train_maps = set(map_dates.iloc[:cutoff]["map_id"])
    train = df[df["map_id"].isin(train_maps)]
    test = df[~df["map_id"].isin(train_maps)]
    print(f"[baseline] split (time-aware by map): train rounds={len(train):,}, test rounds={len(test):,}")
    return test, train


@app.cell
def __(LogisticRegression, accuracy_score, test, train):
    def fit_report(name, feats):
        model = LogisticRegression(max_iter=1000)
        model.fit(train[feats], train["team1_won"])
        acc = accuracy_score(test["team1_won"], model.predict(test[feats]))
        coefs = dict(zip(feats, model.coef_[0].round(4)))
        print(f"[baseline] {name}: test_acc={acc:.4f} | coefs={coefs}")
        return acc

    acc_side = fit_report("side-only", ["side_ct"])
    acc_full = fit_report("side+score-state", ["side_ct", "score_diff", "half_second", "half_ot"])
    # majority-class reference
    base = max(test["team1_won"].mean(), 1 - test["team1_won"].mean())
    print(f"[baseline] majority-class baseline acc={base:.4f}")
    return acc_full, acc_side, base


@app.cell
def __(acc_full, mo):
    mo.md(
        f"**Result.** Side+score-state reaches **{acc_full:.1%}** test accuracy, beating the "
        "~50% base rate (side alone is chance; the lift comes from **score_diff** — leading "
        "teams win more rounds). This validates the sklearn toolchain end-to-end on real round "
        "data (feature build → time-aware split → logistic → accuracy). It's still well short of "
        "Peng's ~60.6%: **loadout** — which vlrggapi doesn't expose per round — is the missing "
        "dominant signal, exactly as Peng found. The score_diff effect is carried into the "
        "Phase 3 score-state model."
    )
    return


if __name__ == "__main__":
    app.run()
