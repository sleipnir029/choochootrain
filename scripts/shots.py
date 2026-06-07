"""Dev-only screenshot harness (dashboard visual verification, Phase C/B/A).

Drives Chromium over the FastAPI-served dashboard and saves full-page PNGs so visual
changes can be eyeballed. Auto-discovers a recent match id + a roster player id from
/api/home. Not part of the app or test suite.

Run: ``python -m scripts.shots [out_subdir]``  (server must be on :8000)
"""

import sys
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = Path("/tmp/shots") / (sys.argv[1] if len(sys.argv) > 1 else "now")


def _home():
    with urllib.request.urlopen(f"{BASE}/api/home", timeout=30) as r:
        return json.load(r)


def main():
    h = _home()
    match_id = (h.get("recent") or [{}])[0].get("match_id")
    player_id = (h["prx"].get("roster") or [{}])[0].get("player_id")
    routes = [
        ("home", "/"),
        ("team_prx", "/team/624"),
        ("team_g2", "/team/11058"),
        ("matchup_prx_g2", "/matchup/624/11058"),
        ("matchup_fnc_nrg", "/matchup/2593/1034"),
        ("model", "/model"),
    ]
    if match_id:
        routes.append(("match", f"/match/{match_id}"))
    if player_id:
        routes.append(("player", f"/player/{player_id}"))

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1366, "height": 900}, device_scale_factor=2)
        for name, path in routes:
            pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=30000)
            pg.wait_for_timeout(900)  # let images/charts settle
            pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print(f"  shot {name:18} {path}")
        b.close()
    print(f"wrote {len(routes)} shots -> {OUT}")


if __name__ == "__main__":
    main()
