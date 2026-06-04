"""Async HTTP client for the self-hosted vlrggapi.

Thin wrapper over httpx used by all Phase 2 ingestion modules. Reads the base
URL from the ``VLRGGAPI_URL`` env var (default ``http://localhost:3001``),
retries transient failures with exponential backoff, sleeps on HTTP 429 rate
limits (honouring ``Retry-After`` when present), and logs via structlog.

vlrggapi wraps every v2 response in an envelope:
``{"status": "success", "data": {"status": ..., "segments": [...]}, ...}``.
``get_json`` returns the whole envelope; ``get_segments`` unwraps
``data.segments`` after asserting ``status == "success"``.

Caching: every successful GET is cached to disk (keyed by path+params), so the
whole downloading system fetches any given endpoint at most once — across
ingestion stages and across separate runs (safe to pause/resume). Cache dir is
``VLR_CACHE_DIR`` (default ``data/http_cache``). Volatile callers (e.g. the live
poller) should construct ``VlrClient(cache=False)``.

Usage:
    async with VlrClient() as client:
        prx = await client.get_segments("/v2/team", id="624")
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import httpx
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "http://localhost:3001"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3          # attempts beyond the first before giving up
BACKOFF_BASE = 0.5       # seconds; doubled each retry
DEFAULT_CACHE_DIR = "data/http_cache"


class VlrApiError(Exception):
    """Raised when vlrggapi returns a non-retryable error or exhausts retries."""


class VlrClient:
    """Async client for vlrggapi. Use as an async context manager."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        cache: bool = True,
        cache_dir: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("VLRGGAPI_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache_enabled = cache
        self._cache_dir = Path(cache_dir or os.environ.get("VLR_CACHE_DIR", DEFAULT_CACHE_DIR))
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "VlrClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self._timeout, transport=self._transport
        )
        return self

    def _cache_path(self, path: str, query: dict) -> Path:
        key = hashlib.sha256(f"{path}?{urlencode(sorted(query.items()))}".encode()).hexdigest()
        return self._cache_dir / f"{key}.json"

    def _cache_read(self, cache_path: Path) -> dict | None:
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _cache_write(self, cache_path: Path, payload: dict) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(cache_path)  # atomic; safe if a run is interrupted
        except OSError as e:  # caching is best-effort, never fatal
            logger.warning("cache_write_failed", path=str(cache_path), error=repr(e))

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _backoff_seconds(self, attempt: int) -> float:
        return BACKOFF_BASE * (2 ** (attempt - 1))

    async def get_json(self, path: str, **params: object) -> dict:
        """GET ``path`` with query ``params``; return the parsed JSON envelope.

        Retries on transport errors, HTTP 5xx, and HTTP 429 (rate limit). Other
        4xx responses raise immediately. Raises ``VlrApiError`` on exhaustion.
        """
        if self._client is None:
            raise RuntimeError("VlrClient must be used as an async context manager")

        query = {k: v for k, v in params.items() if v is not None}

        cache_path = self._cache_path(path, query) if self._cache_enabled else None
        if cache_path is not None and cache_path.exists():
            cached = self._cache_read(cache_path)
            if cached is not None:
                logger.debug("cache_hit", path=path, params=query)
                return cached

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.get(path, params=query or None)
            except httpx.RequestError as e:
                if attempt > self._max_retries:
                    logger.error("vlr_request_failed", path=path, params=query, error=repr(e))
                    raise VlrApiError(f"transport error for {path}: {e!r}") from e
                wait = self._backoff_seconds(attempt)
                logger.warning("vlr_request_retry", path=path, attempt=attempt, wait=wait, error=repr(e))
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 429:
                if attempt > self._max_retries:
                    logger.error("vlr_rate_limited_giveup", path=path, attempt=attempt)
                    raise VlrApiError(f"rate limited (429) for {path} after {attempt} attempts")
                retry_after = _parse_retry_after(resp) or self._backoff_seconds(attempt)
                logger.warning("vlr_rate_limited", path=path, attempt=attempt, wait=retry_after)
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code >= 500:
                if attempt > self._max_retries:
                    logger.error("vlr_server_error_giveup", path=path, status=resp.status_code)
                    raise VlrApiError(f"server error {resp.status_code} for {path}")
                wait = self._backoff_seconds(attempt)
                logger.warning("vlr_server_error_retry", path=path, status=resp.status_code, attempt=attempt, wait=wait)
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 400:
                logger.error("vlr_client_error", path=path, status=resp.status_code)
                raise VlrApiError(f"client error {resp.status_code} for {path}")

            logger.debug("vlr_request_ok", path=path, params=query, status=resp.status_code)
            payload = resp.json()
            # Cache only successful envelopes (don't cache error/empty responses).
            if cache_path is not None and isinstance(payload, dict) and payload.get("status") == "success":
                self._cache_write(cache_path, payload)
            return payload

    async def get_segments(self, path: str, **params: object) -> list:
        """GET ``path`` and return ``data.segments``, asserting envelope success."""
        payload = await self.get_json(path, **params)
        if payload.get("status") != "success":
            raise VlrApiError(f"non-success envelope for {path}: status={payload.get('status')}")
        data = payload.get("data") or {}
        return data.get("segments", []) if isinstance(data, dict) else []


def _parse_retry_after(resp: httpx.Response) -> float | None:
    """Parse a numeric Retry-After header (seconds). Ignore HTTP-date form."""
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
