"""Tests for ingestion.patches — HTML parse + date-range backfill. No network."""

import json
import sqlite3

from ingestion.patches import (
    backfill_match_patches,
    parse_patches_html,
    populate_patches_table,
)
from ingestion.schema import init_db

_NEXT = {
    "props": {"articles": [
        {"title": "VALORANT Patch Notes 8.04", "publishedAt": "2024-03-06T13:00:00.000Z",
         "action": {"payload": {"url": "/en-us/news/game-updates/valorant-patch-notes-8-04"}}},
        {"title": "VALORANT Patch Notes 8.05", "publishDate": "2024-03-19T13:00:00.000Z",
         "action": {"payload": {"url": "/x"}}},
        {"title": "Some unrelated article", "publishedAt": "2024-03-10T00:00:00.000Z"},
    ]}
}
_HTML = ('<html><body><script id="__NEXT_DATA__" type="application/json">'
         + json.dumps(_NEXT) + "</script></body></html>")


def test_parse_patches_html():
    patches = parse_patches_html(_HTML)
    assert [p["patch_id"] for p in patches] == ["8.04", "8.05"]  # sorted, non-patch dropped
    p804 = patches[0]
    assert p804["release_date"] == "2024-03-06"
    assert p804["notes_url"] == "https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-8-04"
    # publishDate fallback works
    assert patches[1]["release_date"] == "2024-03-19"


def _db_with_matches(tmp_path, dates):
    db = str(tmp_path / "prx.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO events (event_id,name,tier,region,start_date,end_date) "
                 "VALUES (1,'E','Masters','global','2024-01-01','2024-12-31')")
    for tid in (10, 20):
        conn.execute("INSERT INTO teams (team_id,name,last_updated) VALUES (?,?,?)", (tid, f"T{tid}", "x"))
    for mid, d in dates.items():
        conn.execute("INSERT INTO matches (match_id,event_id,team1_id,team2_id,team1_score,team2_score,"
                     "date_utc,format) VALUES (?,1,10,20,2,0,?,'Bo3')", (mid, d))
    conn.commit()
    return db, conn


def test_backfill_latest_patch_on_or_before(tmp_path):
    # match 1 in 8.04 window, match 2 on 8.05 release day, match 3 before any patch
    db, conn = _db_with_matches(tmp_path, {1: "2024-03-14", 2: "2024-03-19", 3: "2024-02-10"})
    patches = [
        {"patch_id": "8.03", "release_date": "2024-02-21", "notes_url": None},
        {"patch_id": "8.04", "release_date": "2024-03-06", "notes_url": None},
        {"patch_id": "8.05", "release_date": "2024-03-19", "notes_url": None},
    ]
    populate_patches_table(conn, patches)
    backfill_match_patches(conn)
    conn.commit()

    def patch_of(mid):
        return conn.execute("SELECT patch_id FROM matches WHERE match_id=?", (mid,)).fetchone()[0]

    assert patch_of(1) == "8.04"   # 8.04 (03-06) <= 03-14 < 8.05 (03-19)
    assert patch_of(2) == "8.05"   # 03-19 release day, inclusive
    assert patch_of(3) is None     # before the earliest patch
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_populate_is_idempotent(tmp_path):
    db, conn = _db_with_matches(tmp_path, {})
    patches = [{"patch_id": "9.0", "release_date": "2024-08-27", "notes_url": "u"}]
    populate_patches_table(conn, patches)
    populate_patches_table(conn, patches)  # upsert, no duplicate
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM patches").fetchone()[0] == 1
    conn.close()
