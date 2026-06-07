"""Build the Valorant asset manifest for the dashboard (Phase B).

Pulls agent icons/roles and map splash/minimap art + minimap coordinate transforms from
valorant-api.com (the community mirror of Riot's client assets) into a single committed
JSON manifest, keyed by lowercased display name so the warehouse's agent/map *names* resolve
directly. Image URLs are **hotlinked** to media.valorant-api.com (stable per-UUID CDN) — we
commit the manifest, not the binaries (DEVIATIONS 2026-06-07). The map transforms
(xMultiplier/yMultiplier/xScalarToAdd/yScalarToAdd) are captured now so a later phase can
plot kill coordinates onto the minimap without re-fetching.

Run: ``python -m scripts.fetch_assets`` → writes dashboard/src/assets/valorant-assets.json
"""

import json
import urllib.request
from pathlib import Path

BASE = "https://valorant-api.com/v1"
OUT = Path("dashboard/src/assets/valorant-assets.json")


def _get(path):
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=30) as r:
        return json.load(r)["data"]


def build():
    agents = {}
    for a in _get("agents?isPlayableCharacter=true"):
        role = a.get("role") or {}
        agents[a["displayName"].lower()] = {
            "role": role.get("displayName"),
            "icon": a.get("displayIcon"),
            "roleIcon": role.get("displayIcon"),
        }

    maps = {}
    for m in _get("maps"):
        # Some non-standard entries (e.g. The Range) have no displayIcon minimap; keep anyway.
        maps[m["displayName"].lower()] = {
            "splash": m.get("splash"),
            "minimap": m.get("displayIcon"),
            "listView": m.get("listViewIcon"),
            "xMultiplier": m.get("xMultiplier"),
            "yMultiplier": m.get("yMultiplier"),
            "xScalarToAdd": m.get("xScalarToAdd"),
            "yScalarToAdd": m.get("yScalarToAdd"),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"agents": agents, "maps": maps}, indent=1), encoding="utf-8")
    print(f"wrote {OUT} | {len(agents)} agents, {len(maps)} maps")


if __name__ == "__main__":
    build()
