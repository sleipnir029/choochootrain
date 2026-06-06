"""Phase 3 validation — pre-match map win-prob model on the time-held-out window.

Primary holdout (per TASKS P3.T8) = Masters Toronto 2025 (event 2282) + Masters
Santiago 2026 (event 2760), both strictly after the train cutoff (2025-03-02, end
of Masters Bangkok 2025). Reports map-level accuracy + Brier (overall + per event)
against majority-class and Elo-sign baselines, plus a calibration plot. For
context it also reports accuracy across ALL post-cutoff maps, broken down by tier.

Compares to SPEC §6.3 targets (map-level 65-75%, Brier 0.20-0.23) and the Peng
reference (60.6% round-level — different granularity).

Pre-match predictions only (the score-state/live layer is round-level). Uses the
posterior saved by `python -m models.bayes_logistic`.

Run headless: `python notebooks/02_model_validation.py`
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def __():
    import os
    import sqlite3
    import sys

    # Make the repo's packages importable when run headless via
    # `python notebooks/02_model_validation.py` (run from the repo root).
    sys.path.insert(0, os.getcwd())

    import arviz as az
    import marimo as mo
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    # Importing bayes_logistic sets PYTENSOR_FLAGS (numba backend) before bambi.
    import models.bayes_logistic as bl
    from models.training_data import build_training_data

    np.random.seed(42)
    conn = sqlite3.connect("data/prx.db")
    conn.row_factory = sqlite3.Row
    HOLDOUT_EVENTS = {2282: "Toronto 2025", 2760: "Santiago 2026"}
    return (HOLDOUT_EVENTS, az, bl, build_training_data, conn, mo, np, pd, plt)


@app.cell
def __(bl, build_training_data, conn, pd):
    # Point-in-time features for every map; tag each with its event; keep the
    # post-cutoff slice as the evaluation universe.
    df = build_training_data(conn)
    ev = pd.read_sql("SELECT match_id, event_id FROM matches", conn)
    df = df.merge(ev, on="match_id", how="left")
    post = df[df["date_utc"] > bl.TRAIN_CUTOFF].copy()
    print(f"[val] post-cutoff maps={len(post)} (train cutoff {bl.TRAIN_CUTOFF})")
    return df, post


@app.cell
def __(az, bl, df, post):
    # Rebuild the model on the train split (for scale()/category state) and predict
    # all post-cutoff maps at once with the saved posterior. sample_new_groups
    # handles patches that only appear after the cutoff.
    model = bl.build_model(bl.split_train(df))
    idata = az.from_netcdf(bl.SAVE_PATH)
    pred = model.predict(idata, data=post, inplace=False, sample_new_groups=True)
    post_p = post.copy()
    post_p["p"] = pred.posterior["p"].mean(("chain", "draw")).values
    print(f"[val] predicted {len(post_p)} post-cutoff maps")
    return idata, model, post_p


@app.cell
def __(HOLDOUT_EVENTS, np, post_p):
    def metrics(g):
        y = g["team1_won"].to_numpy()
        p = g["p"].to_numpy()
        acc = float(((p > 0.5).astype(int) == y).mean())
        brier = float(np.mean((p - y) ** 2))
        elo = float(((g["elo_diff"] > 0).astype(int) == y).mean())
        major = float(max(y.mean(), 1 - y.mean()))
        return acc, brier, elo, major

    holdout = post_p[post_p["event_id"].isin(HOLDOUT_EVENTS)].copy()
    holdout["event"] = holdout["event_id"].map(HOLDOUT_EVENTS)
    h_acc, h_brier, h_elo, h_major = metrics(holdout)
    print(f"[val] === PRIMARY HOLDOUT (Masters Toronto 2025 + Santiago 2026), n={len(holdout)} ===")
    print(f"[val] model   acc={h_acc:.4f}  brier={h_brier:.4f}")
    print(f"[val] baseline majority={h_major:.4f}  Elo-sign={h_elo:.4f}")
    for _name, _g in holdout.groupby("event"):
        _a, _b, _e, _ = metrics(_g)
        print(f"[val]   {_name:14} acc={_a:.4f}  brier={_b:.4f}  elo={_e:.4f}  (n={len(_g)})")
    return h_acc, h_brier, h_elo, h_major, holdout, metrics


@app.cell
def __(metrics, post_p):
    # Context: accuracy by tier across ALL post-cutoff maps. The model tracks the
    # Elo-sign baseline; elite events (Masters/Champions — top, evenly-matched
    # teams) are near-coinflips, regional play is more predictable.
    a_acc, a_brier, a_elo, _ = metrics(post_p)
    print(f"[val] --- context: ALL post-cutoff n={len(post_p)} | "
          f"model={a_acc:.4f} Elo-sign={a_elo:.4f} brier={a_brier:.4f} ---")
    for _tier, _g in post_p.groupby("tier"):
        _a, _b, _e, _m = metrics(_g)
        print(f"[val]   {_tier:16} n={len(_g):4} model={_a:.4f} elo={_e:.4f} "
              f"major={_m:.4f} brier={_b:.4f}")
    return a_acc, a_brier, a_elo


@app.cell
def __(holdout, np, plt):
    # Reliability / calibration on the primary holdout.
    p = holdout["p"].to_numpy()
    yv = holdout["team1_won"].to_numpy()
    edges = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, edges) - 1, 0, 9)
    xs, ys, ns = [], [], []
    for _bin in range(10):
        _m = idx == _bin
        if _m.sum():
            xs.append(p[_m].mean())
            ys.append(yv[_m].mean())
            ns.append(int(_m.sum()))
    ece = float(np.sum([n * abs(x - y) for x, y, n in zip(xs, ys, ns)]) / len(p))
    print(f"[val] calibration bins={len(xs)} | ECE={ece:.4f}")

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", label="perfect")
    ax.scatter(xs, ys, s=[max(20, n * 6) for n in ns], alpha=0.7, label="holdout bins")
    ax.set_xlabel("Mean predicted P(team1 wins map)")
    ax.set_ylabel("Observed win rate")
    ax.set_title("Calibration — Masters Toronto 2025 + Santiago 2026")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    fig
    return ece, fig


@app.cell
def __(a_acc, a_elo, ece, h_acc, h_brier, h_elo, h_major, mo):
    mo.md(
        f"**Result (below SPEC target — surfaced to Rahat).** On the primary holdout "
        f"(Masters Toronto 2025 + Santiago 2026) the pre-match model reaches only "
        f"**{h_acc:.1%}** accuracy / Brier **{h_brier:.3f}** (ECE {ece:.3f}) — *below* the "
        f"{h_major:.1%} majority-class and {h_elo:.1%} Elo-sign baselines, and well short of "
        f"SPEC §6.3's 65-75% / 0.20-0.23. Across **all** post-cutoff maps it's {a_acc:.1%} "
        f"(Elo-sign {a_elo:.1%}): the model essentially **reproduces the Elo-sign baseline** — "
        f"the map offsets, form, H2H and patch/tier terms add ~no marginal signal (matching the "
        f"T5 posterior, where elo_diff dominated and the rest were ≈0). The Masters/Champions "
        f"holdout is the hardest slice (top, evenly-matched teams ≈ coinflips at map level); "
        f"regional play is more predictable (~60%). In-sample accuracy is also only ~57%, so this "
        f"is a **signal ceiling**, not overfitting. Decision needed before declaring Phase 3 done."
    )
    return


if __name__ == "__main__":
    app.run()
