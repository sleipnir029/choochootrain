"""prx-app hello-world stub (P1.T7).

Exists only to prove the prx-app container runs and can reach the vlrggapi service
over the docker-compose network. The real FastAPI app arrives in Phase 6 (api/main.py);
this file is throwaway scaffolding and is intentionally NOT in api/.
"""
import json
import os
import urllib.request

from fastapi import FastAPI

app = FastAPI(title="prx-app (Phase 1 stub)")
VLRGGAPI_URL = os.environ.get("VLRGGAPI_URL", "http://vlrggapi:3001").rstrip("/")


@app.get("/")
def root():
    return {"service": "prx-app", "status": "hello", "vlrggapi_url": VLRGGAPI_URL}


@app.get("/vlrggapi-health")
def vlrggapi_health():
    """Proxy vlrggapi's health — proves prx-app -> vlrggapi connectivity end to end."""
    with urllib.request.urlopen(f"{VLRGGAPI_URL}/v2/health", timeout=10) as r:
        return {"reached": True, "upstream": json.load(r)}
