"""Pre-match map win-probability model — Bayesian logistic via Bambi (P3.T5).

A hierarchical logistic regression on the point-in-time features from
``models.training_data``. Trained on maps through the end of Masters Bangkok 2025
(``TRAIN_CUTOFF`` = 2025-03-02); everything after is held out for P3.T8.

Design (SPEC §6.1 — hierarchical Bayesian with partial pooling):
- continuous predictors standardized with the stateful ``scale()`` transform, so
  prediction (P3.T7) reapplies the train-time mean/sd automatically;
- ``tier`` as a fixed categorical (only 4 levels — too few for a random effect);
- a patch-level random intercept ``(1|patch_id)`` for partial pooling across
  patches.

Saves the posterior to ``models/saved/bayes_logistic.nc`` (regenerable; not
committed) and an arviz summary to ``logs/bayes_logistic_fit.txt``. Done when all
parameters have r_hat < 1.05.

Usage:
    python -m models.bayes_logistic --db data/prx.db
"""

import argparse
import os
import sqlite3
from pathlib import Path

# This machine's PyTensor C backend can't link (msys64 g++ -> "ld returned 116"),
# so compile the model via the numba/LLVM backend and disable the C compiler. This
# MUST be set before importing bambi (which imports pytensor). Override the env var
# to use a different backend (e.g. a working C toolchain in Docker). See DEVIATIONS
# 2026-06-06.
os.environ.setdefault("PYTENSOR_FLAGS", "mode=NUMBA,cxx=")

import arviz as az  # noqa: E402
import bambi as bmb  # noqa: E402

from models.training_data import build_training_data  # noqa: E402

TRAIN_CUTOFF = "2025-03-02"   # end of Masters Bangkok 2025
RHAT_THRESHOLD = 1.05
SAVE_PATH = "models/saved/bayes_logistic.nc"

FORMULA = (
    "team1_won ~ scale(elo_diff) + scale(map_elo_diff) + scale(skill_diff)"
    " + team1_starts_atk_or_def"
    " + scale(recent_form_team1) + scale(recent_form_team2)"
    " + scale(h2h_team1_win_rate) + C(tier) + (1|patch_id)"
)


def split_train(df, cutoff=TRAIN_CUTOFF):
    """Maps on/before the cutoff date (the rest is the P3.T8 holdout)."""
    return df[df["date_utc"] <= cutoff].copy()


def build_model(train_df):
    """The Bambi model spec — reused by P3.T7 to reconstruct for prediction."""
    return bmb.Model(FORMULA, train_df, family="bernoulli")


def fit(train_df, *, draws=1000, tune=1000, chains=4, seed=42, target_accept=0.9):
    model = build_model(train_df)
    idata = model.fit(
        draws=draws, tune=tune, chains=chains,
        random_seed=seed, target_accept=target_accept,
    )
    return model, idata


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--tune", type=int, default=1000)
    ap.add_argument("--chains", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=SAVE_PATH)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    df = build_training_data(conn)
    conn.close()

    train = split_train(df)
    print(f"train rows: {len(train)} (date_utc <= {TRAIN_CUTOFF})")

    model, idata = fit(train, draws=args.draws, tune=args.tune,
                       chains=args.chains, seed=args.seed)

    summary = az.summary(idata)
    max_rhat = float(summary["r_hat"].max())
    n_div = int(idata.sample_stats["diverging"].sum())

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    idata.to_netcdf(args.out)
    Path("logs").mkdir(exist_ok=True)
    with open("logs/bayes_logistic_fit.txt", "w", encoding="utf-8") as f:
        f.write(f"train rows: {len(train)} (date_utc <= {TRAIN_CUTOFF})\n")
        f.write(f"formula: {FORMULA}\n")
        f.write(f"max r_hat: {max_rhat:.4f}; divergences: {n_div}\n\n")
        f.write(summary.to_string())

    print(summary.to_string())
    status = "PASS" if max_rhat < RHAT_THRESHOLD else "FAIL"
    print(f"\nmax r_hat = {max_rhat:.4f}; divergences = {n_div} "
          f"-> convergence {status} (threshold {RHAT_THRESHOLD})")
    print(f"saved posterior -> {args.out}")


if __name__ == "__main__":
    main()
