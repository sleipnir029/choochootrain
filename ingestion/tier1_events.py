"""Curated registry of tier-1 VCT events (the source of truth for P2.T4).

vlrggapi's `/v2/events` list is paginated/recent-first, lacks a tier field, and
carries no year, so it can't reliably classify the tier-1 set; `/v2/search` is
fuzzy and event naming is inconsistent across years. Instead we pin the exact
vlr.gg event IDs here (verified against PRX_PREDICTOR_SPEC.md §4 dates) and pull
each event's mutable details from `/v2/event/{id}` at ingest time.

Each entry's `tier`/`region` is OUR classification (the API doesn't provide it).
- tier:   'Masters' | 'Champions' | 'Kickoff' | 'RegionalLeague'  (per ARCHITECTURE.md)
- region: 'global' for Masters/Champions, else 'na'|'emea'|'pac'|'cn'
          (Americas → 'na' per SPEC §4's NA/EMEA/PAC/CN/Global wording)

Scope: all tier-1 per SPEC §4 — Kickoff + Stage 1 + Stage 2 for all four
International Leagues, plus every Masters and Champions, 2024–2026.
Ascension (promotion) events are intentionally excluded — not tier-1 per §4.
"""

MASTERS = "Masters"
CHAMPIONS = "Champions"
KICKOFF = "Kickoff"
LEAGUE = "RegionalLeague"

GLOBAL = "global"
NA, EMEA, PAC, CN = "na", "emea", "pac", "cn"


def _e(event_id: int, tier: str, region: str, label: str) -> dict:
    return {"event_id": event_id, "tier": tier, "region": region, "label": label}


TIER1_EVENTS: list[dict] = [
    # ---- 2024 ----
    _e(1923, KICKOFF, NA, "VCT 2024: Americas Kickoff"),
    _e(1925, KICKOFF, EMEA, "VCT 2024: EMEA Kickoff"),
    _e(1924, KICKOFF, PAC, "VCT 2024: Pacific Kickoff"),
    _e(1926, KICKOFF, CN, "VCT 2024: China Kickoff"),
    _e(1921, MASTERS, GLOBAL, "Masters Madrid 2024"),
    _e(2004, LEAGUE, NA, "VCT 2024: Americas Stage 1"),
    _e(1998, LEAGUE, EMEA, "VCT 2024: EMEA Stage 1"),
    _e(2002, LEAGUE, PAC, "VCT 2024: Pacific Stage 1"),
    _e(2006, LEAGUE, CN, "VCT 2024: China Stage 1"),
    _e(1999, MASTERS, GLOBAL, "Masters Shanghai 2024"),
    _e(2095, LEAGUE, NA, "VCT 2024: Americas Stage 2"),
    _e(2094, LEAGUE, EMEA, "VCT 2024: EMEA Stage 2"),
    _e(2005, LEAGUE, PAC, "VCT 2024: Pacific Stage 2"),
    _e(2096, LEAGUE, CN, "VCT 2024: China Stage 2"),
    _e(2097, CHAMPIONS, GLOBAL, "Champions Seoul 2024"),
    # ---- 2025 ----
    _e(2274, KICKOFF, NA, "VCT 2025: Americas Kickoff"),
    _e(2276, KICKOFF, EMEA, "VCT 2025: EMEA Kickoff"),
    _e(2277, KICKOFF, PAC, "VCT 2025: Pacific Kickoff"),
    _e(2275, KICKOFF, CN, "VCT 2025: China Kickoff"),
    _e(2281, MASTERS, GLOBAL, "Masters Bangkok 2025"),
    _e(2347, LEAGUE, NA, "VCT 2025: Americas Stage 1"),
    _e(2380, LEAGUE, EMEA, "VCT 2025: EMEA Stage 1"),
    _e(2379, LEAGUE, PAC, "VCT 2025: Pacific Stage 1"),
    _e(2359, LEAGUE, CN, "VCT 2025: China Stage 1"),
    _e(2282, MASTERS, GLOBAL, "Masters Toronto 2025"),
    _e(2501, LEAGUE, NA, "VCT 2025: Americas Stage 2"),
    _e(2498, LEAGUE, EMEA, "VCT 2025: EMEA Stage 2"),
    _e(2500, LEAGUE, PAC, "VCT 2025: Pacific Stage 2"),
    _e(2499, LEAGUE, CN, "VCT 2025: China Stage 2"),
    _e(2283, CHAMPIONS, GLOBAL, "Champions Paris 2025"),
    # ---- 2026 ----
    _e(2682, KICKOFF, NA, "VCT 2026: Americas Kickoff"),
    _e(2684, KICKOFF, EMEA, "VCT 2026: EMEA Kickoff"),
    _e(2683, KICKOFF, PAC, "VCT 2026: Pacific Kickoff"),
    _e(2685, KICKOFF, CN, "VCT 2026: China Kickoff"),
    _e(2760, MASTERS, GLOBAL, "Masters Santiago 2026"),
    _e(2860, LEAGUE, NA, "VCT 2026: Americas Stage 1"),
    _e(2863, LEAGUE, EMEA, "VCT 2026: EMEA Stage 1"),
    _e(2775, LEAGUE, PAC, "VCT 2026: Pacific Stage 1"),
    _e(2864, LEAGUE, CN, "VCT 2026: China Stage 1"),
    _e(2765, MASTERS, GLOBAL, "Masters London 2026"),
    _e(2977, LEAGUE, NA, "VCT 2026: Americas Stage 2"),
    _e(2976, LEAGUE, EMEA, "VCT 2026: EMEA Stage 2"),
    _e(2776, LEAGUE, PAC, "VCT 2026: Pacific Stage 2"),
    _e(2978, LEAGUE, CN, "VCT 2026: China Stage 2"),
    _e(2766, CHAMPIONS, GLOBAL, "Champions Shanghai 2026"),
]
