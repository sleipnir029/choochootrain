"""Model-trust endpoints (decision-grade Wave A): is the model calibrated, and where
is it actually sharp? Reads the persisted ``prediction_log`` (built by
``python -m models.backtest``)."""

import math

from fastapi import APIRouter, Depends

from api.deps import get_conn

router = APIRouter()

_ELO_BUCKETS = [(0, 50, "0–50"), (50, 100, "50–100"), (100, 150, "100–150"),
                (150, 250, "150–250"), (250, 1e9, "250+")]


def _agg(rows):
    n = len(rows)
    if n == 0:
        return {"n": 0}
    y = [r["team1_won"] for r in rows]
    p = [r["team1_win_prob"] for r in rows]
    acc = sum(1 for r in rows if r["correct"]) / n
    elo = sum(1 for r in rows if (r["elo_diff"] > 0) == bool(r["team1_won"])) / n
    brier = sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / n
    ll = -sum(yi * math.log(min(max(pi, 1e-6), 1 - 1e-6))
              + (1 - yi) * math.log(min(max(1 - pi, 1e-6), 1 - 1e-6))
              for pi, yi in zip(p, y)) / n
    return {"n": n, "acc": round(acc, 4), "elo_sign_acc": round(elo, 4),
            "brier": round(brier, 4), "logloss": round(ll, 4)}


def _group(rows, key):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


@router.get("/api/model/track-record")
def track_record(conn=Depends(get_conn)):
    """Out-of-sample track record + reliability + the sharp-vs-coinflip regime map."""
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_log'"
    ).fetchone()
    if not exists:
        return {"available": False, "reason": "run `python -m models.backtest` to build prediction_log"}
    rows = [dict(r) for r in conn.execute("SELECT * FROM prediction_log").fetchall()]
    if not rows:
        return {"available": False, "reason": "prediction_log is empty"}

    by_tier = [{"tier": k, **_agg(v)} for k, v in sorted(_group(rows, "tier").items())]
    order = {"sharp": 0, "lean": 1, "coinflip": 2}
    by_conf = sorted(({"confidence": k, **_agg(v)} for k, v in _group(rows, "confidence").items()),
                     key=lambda d: order.get(d["confidence"], 9))

    by_elo = []
    for lo, hi, lab in _ELO_BUCKETS:
        g = [r for r in rows if lo <= abs(r["elo_diff"]) < hi]
        if g:
            by_elo.append({"bucket": lab, **_agg(g)})

    # Reliability curve: decile bins of predicted prob vs actual frequency.
    reliability = []
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        g = [r for r in rows if (lo <= r["team1_win_prob"] < hi) or (b == 9 and r["team1_win_prob"] == 1.0)]
        if g:
            reliability.append({
                "bin": round((lo + hi) / 2, 2),
                "predicted": round(sum(r["team1_win_prob"] for r in g) / len(g), 4),
                "actual": round(sum(r["team1_won"] for r in g) / len(g), 4),
                "n": len(g),
            })

    recent = [
        {k: r[k] for k in ("match_id", "date_utc", "tier", "team1_win_prob",
                           "team1_won", "correct", "confidence")}
        for r in sorted(rows, key=lambda r: r["date_utc"], reverse=True)[:25]
    ]

    return {
        "available": True,
        "overall": _agg(rows),
        "by_tier": by_tier,
        "by_confidence": by_conf,
        "by_elo_bucket": by_elo,
        "reliability": reliability,
        "recent": recent,
    }
