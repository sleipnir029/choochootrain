"""Shared FastAPI dependencies (P6.T2): DB path + per-request connection.

The heavy model resources (Bambi posterior, training data, score-state table) are
loaded lazily by ``models.predict._resources`` on the first prediction request and
cached per db path — so importing the API is light and the predict routes pull the
MCMC stack only when actually called.
"""

import os
import sqlite3


def db_path() -> str:
    """Resolve the SQLite warehouse path (``PRX_DB_PATH`` or ``$DATA_DIR/prx.db``)."""
    explicit = os.environ.get("PRX_DB_PATH")
    if explicit:
        return explicit
    return os.path.join(os.environ.get("DATA_DIR", "data"), "prx.db")


def get_conn():
    """Per-request read-only-ish SQLite connection with row access by name.

    ``check_same_thread=False`` because async routes run their body in the event
    loop thread while a sync generator dependency is resolved in a threadpool
    thread — the connection would otherwise be thread-bound. Each request still
    gets its own connection (no sharing), so this is safe.
    """
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
