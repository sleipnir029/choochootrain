"""Date->patch lookup.

Scrapes Riot's patch-notes index ONCE (the embedded ``__NEXT_DATA__`` JSON lists
``VALORANT Patch Notes X.YZ`` + ISO release dates), writes a committed
``data/patches.json`` (the reproducible source of truth — no repeated scraping),
populates the ``patches`` table, and backfills ``matches.patch_id`` to the latest
patch released on or before each match's date.

Usage:
    python -m ingestion.patches --db data/prx.db          # use data/patches.json if present, else scrape
    python -m ingestion.patches --db data/prx.db --refresh # re-scrape Riot
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

PATCH_NOTES_URL = "https://playvalorant.com/en-us/news/tags/patch-notes/"
DEFAULT_JSON = "data/patches.json"
_TITLE_RE = re.compile(r"Patch Notes (\d+\.\d+)")
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def parse_patches_html(html: str) -> list[dict]:
    """Extract [{patch_id, release_date, notes_url}] from the patch-notes page HTML."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise RuntimeError("no __NEXT_DATA__ on patch-notes page (layout changed?)")
    data = json.loads(m.group(1))

    out: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            title = node.get("title")
            # Riot stores the article date under publishedAt/publishDate (not 'date').
            date = node.get("publishedAt") or node.get("publishDate") or node.get("date")
            if isinstance(title, str) and isinstance(date, str) and date:
                mt = _TITLE_RE.search(title)
                if mt:
                    slug = ((node.get("action") or {}).get("payload") or {}).get("url")
                    notes = f"https://playvalorant.com{slug}" if isinstance(slug, str) and slug.startswith("/") else slug
                    out.setdefault(mt.group(1), {
                        "patch_id": mt.group(1), "release_date": date[:10], "notes_url": notes})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return sorted(out.values(), key=lambda p: [int(x) for x in p["patch_id"].split(".")])


def fetch_patches_from_riot(url: str = PATCH_NOTES_URL) -> list[dict]:
    """Fetch the patch-notes index and parse it (one external request)."""
    resp = httpx.get(url, timeout=30, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    resp.raise_for_status()
    patches = parse_patches_html(resp.text)
    logger.info("patches_fetched", count=len(patches),
                first=patches[0]["patch_id"] if patches else None,
                last=patches[-1]["patch_id"] if patches else None)
    return patches


def save_patches_json(patches: list[dict], path: str = DEFAULT_JSON) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(patches, indent=2), encoding="utf-8")


def load_patches_json(path: str = DEFAULT_JSON) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def populate_patches_table(conn: sqlite3.Connection, patches: list[dict]) -> None:
    for p in patches:
        conn.execute(
            "INSERT INTO patches (patch_id, release_date, notes_url) VALUES (?, ?, ?) "
            "ON CONFLICT(patch_id) DO UPDATE SET "
            "release_date = excluded.release_date, notes_url = excluded.notes_url",
            (p["patch_id"], p["release_date"], p.get("notes_url")),
        )


def backfill_match_patches(conn: sqlite3.Connection) -> int:
    """Set matches.patch_id = latest patch released on or before the match date."""
    cur = conn.execute(
        """
        UPDATE matches SET patch_id = (
            SELECT p.patch_id FROM patches p
            WHERE p.release_date <= matches.date_utc
            ORDER BY p.release_date DESC LIMIT 1
        )
        """
    )
    return cur.rowcount


def run(db_path: str, *, refresh: bool = False, json_path: str = DEFAULT_JSON) -> dict:
    if refresh or not Path(json_path).exists():
        patches = fetch_patches_from_riot()
        save_patches_json(patches, json_path)
    else:
        patches = load_patches_json(json_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        populate_patches_table(conn, patches)
        backfilled = backfill_match_patches(conn)
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM matches WHERE patch_id IS NULL").fetchone()[0]
    finally:
        conn.close()
    summary = {"patches": len(patches), "matches_updated": backfilled, "matches_null_patch": remaining}
    logger.info("patches_done", **summary)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build patches table + backfill matches.patch_id.")
    parser.add_argument("--db", default="data/prx.db")
    parser.add_argument("--json", default=DEFAULT_JSON)
    parser.add_argument("--refresh", action="store_true", help="Re-scrape Riot even if the JSON exists.")
    args = parser.parse_args(argv)
    s = run(args.db, refresh=args.refresh, json_path=args.json)
    print(f"patches: {s['patches']}, matches updated: {s['matches_updated']}, "
          f"still NULL patch: {s['matches_null_patch']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
