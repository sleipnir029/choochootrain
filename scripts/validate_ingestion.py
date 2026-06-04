"""Validate the ingested warehouse and write a summary report.

Checks structural integrity (every match has >=1 map, every map has player
stats), rounds-completeness per year, and resolution coverage. Prints the report
and saves it to logs/ingestion_validation.txt. Read-only; no network.

Usage:
    python -m scripts.validate_ingestion --db data/prx.db
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _scalar(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def build_report(db_path: str) -> tuple[str, dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    L = []  # report lines
    anomalies = {}

    L.append("=== PRX Predictor — Ingestion Validation ===")
    L.append(f"db: {db_path}")
    L.append(f"generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append("")

    # Row counts
    L.append("-- Row counts --")
    tables = ["events", "teams", "players", "matches", "maps", "rounds",
              "map_player_stats", "map_team_economy", "roster_history", "patches"]
    for t in tables:
        try:
            L.append(f"  {t:20} {_scalar(conn, f'SELECT COUNT(*) FROM {t}')}")
        except sqlite3.Error as e:
            L.append(f"  {t:20} ERROR {e}")
    L.append("")

    # Per-year breakdown (year from matches.date_utc)
    L.append("-- Per year (from matches.date_utc) --")
    L.append(f"  {'year':6}{'matches':>9}{'maps':>7}{'rounds':>9}{'maps_complete':>15}{'complete%':>11}")
    rows = conn.execute("""
        SELECT substr(m.date_utc,1,4) AS yr,
               COUNT(DISTINCT mt.match_id) AS matches,
               COUNT(mp.map_id) AS maps,
               COALESCE(SUM(mp.is_rounds_complete),0) AS complete
        FROM matches mt
        JOIN matches m ON m.match_id = mt.match_id
        LEFT JOIN maps mp ON mp.match_id = mt.match_id
        GROUP BY yr ORDER BY yr
    """).fetchall()
    year_stats = {}
    for r in rows:
        yr = r["yr"]
        nrounds = _scalar(conn,
            "SELECT COUNT(*) FROM rounds rd JOIN maps mp ON mp.map_id=rd.map_id "
            "JOIN matches m ON m.match_id=mp.match_id WHERE substr(m.date_utc,1,4)=?", (yr,))
        pct = (100.0 * r["complete"] / r["maps"]) if r["maps"] else 0.0
        L.append(f"  {yr:6}{r['matches']:>9}{r['maps']:>7}{nrounds:>9}{r['complete']:>15}{pct:>10.1f}%")
        year_stats[yr] = {"matches": r["matches"], "maps": r["maps"], "rounds": nrounds,
                          "maps_complete": r["complete"], "complete_pct": round(pct, 1)}
    L.append("")

    # Anomalies
    L.append("-- Anomalies --")
    no_maps = [r[0] for r in conn.execute(
        "SELECT match_id FROM matches WHERE match_id NOT IN (SELECT DISTINCT match_id FROM maps)")]
    no_stats = [r[0] for r in conn.execute(
        "SELECT map_id FROM maps WHERE map_id NOT IN (SELECT DISTINCT map_id FROM map_player_stats)")]
    incomplete_maps = _scalar(conn, "SELECT COUNT(*) FROM maps WHERE is_rounds_complete = 0")
    null_pid = _scalar(conn, "SELECT COUNT(*) FROM map_player_stats WHERE player_id IS NULL")
    null_pid_handles = _scalar(conn,
        "SELECT COUNT(DISTINCT player_handle) FROM map_player_stats WHERE player_id IS NULL")
    null_winner = _scalar(conn, "SELECT COUNT(*) FROM matches WHERE winner_id IS NULL")
    null_patch = _scalar(conn, "SELECT COUNT(*) FROM matches WHERE patch_id IS NULL")

    L.append(f"  matches with 0 maps:           {len(no_maps)}" + (f"  {no_maps}" if no_maps else ""))
    L.append(f"  maps with 0 player_stats:      {len(no_stats)}" + (f"  {no_stats[:20]}" if no_stats else ""))
    L.append(f"  maps with is_rounds_complete=0: {incomplete_maps}")
    L.append(f"  map_player_stats NULL player_id: {null_pid} rows ({null_pid_handles} distinct handles)")
    L.append(f"  matches with NULL winner_id:   {null_winner}")
    L.append(f"  matches with NULL patch_id:    {null_patch}  (populated by P2.T13)")
    L.append("")

    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    L.append(f"  PRAGMA foreign_key_check: {'OK (empty)' if not fk else f'{len(fk)} violations'}")
    conn.close()

    anomalies = {
        "matches_no_maps": no_maps,
        "maps_no_stats": no_stats,
        "incomplete_maps": incomplete_maps,
        "null_player_id_rows": null_pid,
        "null_winner": null_winner,
        "null_patch": null_patch,
        "fk_violations": len(fk),
        "year_stats": year_stats,
    }
    return "\n".join(L), anomalies


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the ingested warehouse.")
    parser.add_argument("--db", default="data/prx.db")
    parser.add_argument("--out", default="logs/ingestion_validation.txt")
    args = parser.parse_args(argv)

    report, _ = build_report(args.db)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n(report saved to {out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
