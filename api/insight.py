"""Templated narrative composer for the PRX-centric dashboard (P6 revision).

Pure text — turns the model's structured outputs (factors, expected-vs-actual,
score-state, replay trace) into short, PRX-framed narrative. No LLM, no I/O. This
is the "why" layer the SPEC (§7.2) calls for; Phase 7 can later feed the same
inputs to DeepSeek for richer prose. Each function returns
``{"headline": str, "points": list[str], "tone": str}``.

Inputs are plain dicts/lists (predictions, expected-vs-actual rows, replay maps)
so this module stays free of pandas / DB.
"""

PRX_TEAM_ID = 624
PRX = "PRX"

# Factors we trust for narrative. Recent form was found to be near-zero/noisy
# signal (Phase 3), so it's excluded from the "why" sentence.
_NARRATIVE_FACTORS = {"Player skill", "Elo difference", "Map advantage",
                      "Head-to-head", "Starting side"}
_ACS_DELTA = 25  # over/under-performance threshold (ACS vs expectation)


def _pct(p):
    return round(p * 100)


def _prx_prob(team1_prob, prx_side):
    return team1_prob if prx_side == "team1" else 1.0 - team1_prob


def prematch_insight(pred, subject_side, *, subject=PRX, subject_team_id=PRX_TEAM_ID,
                     expected=None):
    """What might happen, framed around ``subject`` (PRX when PRX is playing; otherwise the
    actual team so a non-PRX matchup isn't mislabelled). ``pred`` = a /api/predict/pre-match
    dict; ``subject_side`` is which side of the row the subject is ('team1'/'team2');
    ``expected`` = list of {handle, team_id, expected_acs} for the watch-player call."""
    sub_p = _prx_prob(pred["team1_win_prob"], subject_side)
    opp = (pred["team2"] if subject_side == "team1" else pred["team1"]).get("name") or "the opponent"
    pc = _pct(sub_p)
    tone = "favourite" if sub_p >= 0.6 else "underdog" if sub_p <= 0.4 else "coinflip"
    headline = {
        "favourite": f"{subject} are favoured — {pc}% to win the map vs {opp}",
        "underdog": f"{subject} are underdogs — {pc}% to win the map vs {opp}",
        "coinflip": f"{subject} vs {opp}: too close to call ({pc}%)",
    }[tone]

    points = []
    hdi = pred.get("team1_win_prob_hdi")
    if hdi:
        lo, hi = (hdi if subject_side == "team1" else [1 - hdi[1], 1 - hdi[0]])
        points.append(f"Confidence: {pc}% to win the map (likely {_pct(lo)}–{_pct(hi)}%).")

    facts = [f for f in pred.get("top_factors", []) if f["factor"] in _NARRATIVE_FACTORS][:2]
    sub_favs = [f["factor"].lower() for f in facts
                if (f["favors"] == "team1") == (subject_side == "team1")]
    opp_favs = [f["factor"].lower() for f in facts
                if (f["favors"] == "team1") != (subject_side == "team1")]
    if sub_favs:
        points.append(f"In {subject}'s favour: {' and '.join(sub_favs)}.")
    if opp_favs:
        points.append(f"Going {opp}'s way: {' and '.join(opp_favs)}.")

    sp = pred.get("series_win_prob")
    if sp:
        sub_series = sp["team1"] if subject_side == "team1" else sp["team2"]
        points.append(f"Series ({pred.get('series_format', 'Bo3')}): {_pct(sub_series)}% to take it.")

    mps = pred.get("map_predictions") or []
    if mps:
        def mp_sub(m):
            return _prx_prob(m["team1_win_prob"], subject_side)
        closest = min(mps, key=lambda m: abs(mp_sub(m) - 0.5))
        points.append(f"Closest map: {closest['map_name']} ({_pct(mp_sub(closest))}% {subject}).")

    if expected:
        sub_exp = [e for e in expected
                   if e["team_id"] == subject_team_id and e.get("expected_acs")]
        if sub_exp:
            top = max(sub_exp, key=lambda e: e["expected_acs"])
            points.append(f"Watch {top['handle']} — expected ~{round(top['expected_acs'])} ACS.")

    return {"headline": headline, "points": points, "tone": tone}


def matchup_extras(t1_name, t2_name, scout):
    """Scouting-derived bullets for the head-to-head prep view, framed by team name (not
    subject): the biggest sample-adjusted map edge, the marquee cross-roster duel, and each
    team's veto lean. ``scout`` = a models.scouting.head_to_head() dict. Appended to the
    matchup's pre-match insight points."""
    pts = []
    best = None
    for e in scout.get("map_edge", []):
        a1, a2 = e.get("t1_win_rate_adj"), e.get("t2_win_rate_adj")
        if a1 is None or a2 is None:
            continue
        d = a1 - a2
        if best is None or abs(d) > abs(best[1]):
            best = (e["map_name"], d)
    if best and abs(best[1]) >= 0.12:
        mapn, d = best
        team = t1_name if d > 0 else t2_name
        pts.append(f"Map edge: {team} are the stronger side on {mapn} (+{round(abs(d) * 100)} adj win%).")

    duels = scout.get("key_duels") or []
    if duels:
        top = max(duels, key=lambda x: abs(x["net"]))
        if abs(top["net"]) >= 6:
            win_p, lose_p, k, dd = (
                (top["t1_player"], top["t2_player"], top["kills"], top["deaths"]) if top["net"] > 0
                else (top["t2_player"], top["t1_player"], top["deaths"], top["kills"]))
            pts.append(f"Duel to watch: {win_p} has the history over {lose_p} ({k}-{dd}).")

    b1 = (scout.get("veto1") or {}).get("bans") or []
    b2 = (scout.get("veto2") or {}).get("bans") or []
    if b1 and b2:
        pts.append(f"Veto lean: {t1_name} most-ban {b1[0]['map_name']}, {t2_name} most-ban {b2[0]['map_name']}.")
    return pts


def biggest_swing(maps, prx_side):
    """Largest round-to-round win-prob move (PRX perspective) across a replay."""
    best = None
    for m in maps:
        prev = None
        for r in m["rounds"]:
            p = r.get("pre_round_prob_team1")
            if p is None:
                continue
            prx_p = _prx_prob(p, prx_side)
            if prev is not None:
                d = prx_p - prev
                if best is None or abs(d) > abs(best["delta"]):
                    best = {"map_name": m["map_name"], "round": r["round"], "delta": d}
            prev = prx_p
    return best


def postmatch_insight(subject_prob, subject_won, *, subject=PRX, subject_team_id=PRX_TEAM_ID,
                      expected=None, swing=None):
    """What actually happened, framed around ``subject``. ``subject_prob`` = pre-match
    P(subject); ``expected`` = list of {handle, team_id, expected_acs, actual_acs};
    ``swing`` = biggest_swing() output."""
    pc = _pct(subject_prob)
    correct = (subject_prob > 0.5) == subject_won
    result = "won" if subject_won else "lost"
    if abs(subject_prob - 0.5) < 0.05:
        headline, tone = f"A coin-flip on paper ({pc}%) — {subject} {result}.", "coinflip"
    else:
        headline = f"Model gave {subject} {pc}% — they {result} {'✓' if correct else '✗'}."
        tone = "expected" if correct else "upset"

    points = []
    if expected:
        sub = [e for e in expected if e["team_id"] == subject_team_id
               and e.get("actual_acs") is not None and e.get("expected_acs") is not None]
        deltas = [(e, e["actual_acs"] - e["expected_acs"]) for e in sub]
        if deltas:
            over_e, over_d = max(deltas, key=lambda d: d[1])
            under_e, under_d = min(deltas, key=lambda d: d[1])
            if over_d >= _ACS_DELTA:
                points.append(f"{over_e['handle']} stepped up: {round(over_e['actual_acs'])} ACS "
                              f"vs ~{round(over_e['expected_acs'])} expected (+{round(over_d)}).")
            if under_d <= -_ACS_DELTA:
                points.append(f"{under_e['handle']} off the pace: {round(under_e['actual_acs'])} "
                              f"vs ~{round(under_e['expected_acs'])} expected ({round(under_d)}).")
    if swing:
        side = subject if swing["delta"] >= 0 else "the opponent"
        points.append(f"Biggest swing: {swing['map_name']} round {swing['round']} "
                      f"({'+' if swing['delta'] >= 0 else ''}{_pct(swing['delta'])}pt for {side}).")
    return {"headline": headline, "points": points, "tone": tone}


def live_insight(live, subject_side, *, subject=PRX, prematch=None):
    """What's happening now. ``live`` = a /api/predict/live (mode=live) dict.

    Framed around ``subject`` (PRX when PRX is playing; otherwise the actual team so a
    non-PRX tier-1 live match isn't mislabelled). ``subject_side`` is which side of the
    live row the subject is ('team1'/'team2')."""
    cur = live.get("team1_win_prob_current_map")
    mapn = live.get("current_map") or "this map"
    if cur is None:
        return {"headline": f"{subject} are live on {mapn}.",
                "points": ["Waiting for the first in-map prediction."], "tone": "live"}
    sub_p = _prx_prob(cur, subject_side)
    t1r = (live.get("team1_round_ct") or 0) + (live.get("team1_round_t") or 0)
    t2r = (live.get("team2_round_ct") or 0) + (live.get("team2_round_t") or 0)
    sub_r, opp_r = (t1r, t2r) if subject_side == "team1" else (t2r, t1r)
    verb = "lead" if sub_r > opp_r else "trail" if sub_r < opp_r else "are level"
    headline = f"{subject} {verb} {sub_r}-{opp_r} on {mapn} — {_pct(sub_p)}% to win it."

    points = []
    if prematch is not None:
        d = sub_p - prematch
        if abs(d) >= 0.1:
            points.append(f"Momentum {'with' if d > 0 else 'against'} {subject} "
                          f"({'+' if d > 0 else ''}{_pct(d)}pt vs pre-match).")
    return {"headline": headline, "points": points, "tone": "live"}
