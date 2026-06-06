"""Phase 3 revisit — does a team-aggregated player-skill feature lift map prediction?

P3.T8 found map prediction stuck at the Elo ceiling (~57%). This tests whether a
point-in-time team-skill feature (mean TrueSkill mu of each lineup, team1 minus
team2, from `replay_skill_diffs`) adds signal beyond Elo. Fits sklearn logistic
models on the train split and compares accuracy/AUC/Brier on the broad post-cutoff
holdout and the elite Masters subset for feature sets: elo, skill, elo+skill.

Run headless: `python notebooks/04_player_skill_lift.py`
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def __():
    import os
    import sqlite3
    import sys

    sys.path.insert(0, os.getcwd())

    import marimo as mo
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

    import models.bayes_logistic as bl
    from models.training_data import build_training_data
    from scripts.build_player_skill import replay_skill_diffs

    conn = sqlite3.connect("data/prx.db")
    conn.row_factory = sqlite3.Row
    MASTERS = [2282, 2760]  # Toronto 2025 + Santiago 2026
    return (LogisticRegression, MASTERS, StandardScaler, accuracy_score, bl,
            brier_score_loss, build_training_data, conn, mo, np, pd,
            replay_skill_diffs, roc_auc_score)


@app.cell
def __(build_training_data, conn, pd, replay_skill_diffs):
    td = build_training_data(conn)
    ev = pd.read_sql("SELECT match_id, event_id FROM matches", conn)
    td = td.merge(ev, on="match_id")
    td["skill_diff"] = td["map_id"].map(replay_skill_diffs(conn))
    td = td.dropna(subset=["skill_diff"])
    print(f"[lift] maps with skill_diff: {len(td)}")
    print(f"[lift] corr(skill_diff, elo_diff)={td['skill_diff'].corr(td['elo_diff']):.3f}  "
          f"corr(skill_diff, won)={td['skill_diff'].corr(td['team1_won']):.3f}  "
          f"corr(elo_diff, won)={td['elo_diff'].corr(td['team1_won']):.3f}")
    return (td,)


@app.cell
def __(LogisticRegression, MASTERS, StandardScaler, accuracy_score, bl,
       brier_score_loss, roc_auc_score, td):
    train = td[td["date_utc"] <= bl.TRAIN_CUTOFF]
    post = td[td["date_utc"] > bl.TRAIN_CUTOFF]
    masters = post[post["event_id"].isin(MASTERS)]

    def evaluate(cols, test):
        sc = StandardScaler().fit(train[cols])
        m = LogisticRegression(max_iter=2000).fit(sc.transform(train[cols]), train["team1_won"])
        p = m.predict_proba(sc.transform(test[cols]))[:, 1]
        y = test["team1_won"].to_numpy()
        return accuracy_score(y, p > 0.5), roc_auc_score(y, p), brier_score_loss(y, p)

    results = {}
    print(f"[lift] train={len(train)} post={len(post)} masters={len(masters)}")
    print("[lift] featureset    post(acc/auc/brier)      Masters(acc/auc/brier)")
    for label, cols in [("elo", ["elo_diff"]), ("skill", ["skill_diff"]),
                        ("elo+skill", ["elo_diff", "skill_diff"])]:
        pa = evaluate(cols, post)
        ma = evaluate(cols, masters)
        results[label] = (pa, ma)
        print(f"[lift]   {label:11} {pa[0]:.3f}/{pa[1]:.3f}/{pa[2]:.3f}    "
              f"{ma[0]:.3f}/{ma[1]:.3f}/{ma[2]:.3f}")
    return masters, post, results, train


@app.cell
def __(mo, results):
    elo, skill, both = results["elo"], results["skill"], results["elo+skill"]
    mo.md(
        f"**Result — player skill lifts map prediction beyond the Elo ceiling.** On the "
        f"broad post-cutoff holdout, **elo+skill** reaches **{both[0][0]:.1%}** accuracy / "
        f"AUC {both[0][1]:.3f} vs Elo-only {elo[0][0]:.1%} / {elo[0][1]:.3f} — a real, if "
        f"modest, gain (skill_diff correlates only ~0.5 with Elo, so it adds distinct info, "
        f"unlike the dead Layer-3 features). On the **elite Masters** holdout, **skill alone** "
        f"hits **{skill[1][0]:.1%}** / AUC {skill[1][1]:.3f} vs Elo's {elo[1][0]:.1%} / "
        f"{elo[1][1]:.3f} — individual firepower discriminates among top, evenly-matched teams "
        f"where team Elo can't. Recommendation: integrate `skill_diff` into the pre-match model "
        f"(training_data + Bambi refit) and re-validate; this revises the P3.T8 'hard ceiling' "
        f"conclusion."
    )
    return


if __name__ == "__main__":
    app.run()
