"""Phase 0 EDA — round-level outcomes + economy/loadout signal (PRX Predictor).

Reframed Phase 0 (see docs/DEVIATIONS.md 2026-06-06): per-round loadout is not
available from vlrggapi, so this inspects what the warehouse DOES have at round
level (side, half, target balance) and validates the loadout signal descriptively
via map-level buy-category win rates.

Run headless: `python notebooks/00_round_eda.py`  (prints findings)
Interactive:  `marimo edit notebooks/00_round_eda.py`
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def __():
    import matplotlib
    matplotlib.use("Agg")  # headless-safe
    import sqlite3

    import marimo as mo
    import matplotlib.pyplot as plt
    import pandas as pd

    conn = sqlite3.connect("data/prx.db")
    return conn, mo, pd, plt


@app.cell
def __(mo):
    mo.md("# Phase 0 EDA — round outcomes & loadout signal")
    return


@app.cell
def __(conn, pd):
    n_rounds = pd.read_sql("SELECT COUNT(*) n FROM rounds", conn)["n"][0]
    # target balance: how often the (arbitrary) team1 wins a round
    t1 = pd.read_sql(
        """SELECT AVG(CASE WHEN r.winner_id = m.team1_id THEN 1.0 ELSE 0.0 END) wr
           FROM rounds r JOIN maps mp ON mp.map_id = r.map_id
           JOIN matches m ON m.match_id = mp.match_id""", conn)["wr"][0]
    print(f"[EDA] rounds = {n_rounds:,} | team1 round win-rate = {t1:.4f} (target balance)")
    return n_rounds, t1


@app.cell
def __(conn, pd):
    side = pd.read_sql(
        """SELECT r.team1_side AS side, COUNT(*) AS n,
                  AVG(CASE WHEN r.winner_id = m.team1_id THEN 1.0 ELSE 0.0 END) AS team1_winrate
           FROM rounds r JOIN maps mp ON mp.map_id = r.map_id
           JOIN matches m ON m.match_id = mp.match_id
           GROUP BY r.team1_side""", conn)
    print("[EDA] team1 round win-rate by side (CT/T balance):")
    print(side.to_string(index=False))
    return side,


@app.cell
def __(conn, pd):
    econ = pd.read_sql(
        """SELECT ROUND(AVG(pistol_win_pct),1) AS pistol,
                  ROUND(AVG(eco_win_pct),1)    AS eco,
                  ROUND(AVG(semi_buy_win_pct),1) AS semi_buy,
                  ROUND(AVG(full_buy_win_pct),1) AS full_buy
           FROM map_team_economy""", conn)
    print("[EDA] mean win% by buy category (loadout signal):")
    print(econ.to_string(index=False))
    return econ,


@app.cell
def __(econ, plt, side):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    cats = ["pistol", "eco", "semi_buy", "full_buy"]
    ax1.bar(cats, [econ[c][0] for c in cats], color="#4c78a8")
    ax1.axhline(50, ls="--", c="k", lw=0.8)
    ax1.set_title("Win % by buy category (loadout signal)")
    ax1.set_ylabel("win %")
    ax2.bar(side["side"], side["team1_winrate"] * 100, color="#f58518")
    ax2.axhline(50, ls="--", c="k", lw=0.8)
    ax2.set_title("team1 round win % by side")
    ax2.set_ylim(45, 60)
    fig.tight_layout()
    fig
    return


@app.cell
def __(mo):
    mo.md(
        "**Findings.** (1) Round target is balanced (~50.5% team1). "
        "(2) Side is barely predictive — pro maps are well-balanced (CT≈T≈50%). "
        "(3) Loadout shows the real signal: eco rounds win ~43% vs ~54% for buys "
        "(~11pt), matching Peng's thesis that loadout dominates — but only visible "
        "in aggregate here (no per-round loadout). The fitted baseline (notebook 01) "
        "will therefore be near-chance from side/score alone."
    )
    return


if __name__ == "__main__":
    app.run()
