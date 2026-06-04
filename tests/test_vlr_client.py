"""Tests for ingestion.vlr_client's disk cache (uses httpx.MockTransport, no net)."""

import asyncio

import httpx

from ingestion.vlr_client import VlrClient

OK_BODY = {"status": "success", "data": {"status": 200, "segments": [{"id": "624"}]},
           "meta": None, "message": None}


def _counting_transport(counter, body=OK_BODY):
    def handler(request):
        counter["n"] += 1
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


def test_cache_hit_skips_network(tmp_path):
    counter = {"n": 0}

    async def run():
        async with VlrClient(base_url="http://test", cache=True, cache_dir=str(tmp_path),
                             transport=_counting_transport(counter)) as c:
            a = await c.get_json("/v2/team", id="624")
            b = await c.get_json("/v2/team", id="624")  # served from cache
        return a, b

    a, b = asyncio.run(run())
    assert a == b == OK_BODY
    assert counter["n"] == 1  # only one real request


def test_distinct_params_are_separate_cache_entries(tmp_path):
    counter = {"n": 0}

    async def run():
        async with VlrClient(base_url="http://test", cache=True, cache_dir=str(tmp_path),
                             transport=_counting_transport(counter)) as c:
            await c.get_json("/v2/team", id="624")
            await c.get_json("/v2/team", id="624", q="matches")  # different params -> miss
            await c.get_json("/v2/team", id="624")               # hit
            await c.get_json("/v2/team", id="624", q="matches")  # hit

    asyncio.run(run())
    assert counter["n"] == 2


def test_cache_disabled_always_fetches(tmp_path):
    counter = {"n": 0}

    async def run():
        async with VlrClient(base_url="http://test", cache=False, cache_dir=str(tmp_path),
                             transport=_counting_transport(counter)) as c:
            await c.get_json("/v2/team", id="624")
            await c.get_json("/v2/team", id="624")

    asyncio.run(run())
    assert counter["n"] == 2


def test_non_success_envelope_not_cached(tmp_path):
    counter = {"n": 0}
    err = {"status": "error", "data": None}

    async def run():
        async with VlrClient(base_url="http://test", cache=True, cache_dir=str(tmp_path),
                             transport=_counting_transport(counter, body=err)) as c:
            await c.get_json("/v2/team", id="624")
            await c.get_json("/v2/team", id="624")  # not cached -> refetched

    asyncio.run(run())
    assert counter["n"] == 2
