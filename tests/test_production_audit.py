"""Audit failures must remain visible; snapshot absence is never called a miss."""
import httpx
import pytest

from app.production_audit import IndependentEvent, collect_audit, evaluate_samples


def _event():
    return IndependentEvent(
        title="Official model release", source_url="https://lab.test/news/model/",
        published_on="2026-10-29", verified_on="2026-10-31", reason="Independent official listing",
    )


def test_snapshot_matches_official_url_without_inventing_timely_recall():
    event = _event()
    observed = evaluate_samples([event], [{"id": "a", "url": "https://lab.test/news/model?utm_source=rss"}])
    assert observed["observed"] == 1
    absent = evaluate_samples([event], [])
    assert absent["items"][0]["status"] == "not_observed"
    assert "recall_rate" not in absent


@pytest.mark.asyncio
async def test_audit_handles_partial_endpoint_failure_and_reads_nested_summary():
    def handler(request):
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True, "version": "test", "data_dir": "private"})
        if request.url.path.endswith("/sources"):
            return httpx.Response(503)
        if request.url.path.endswith("/report"):
            return httpx.Response(200, json={"benchmark_coverage": {"total": 0}})
        if request.url.path.endswith("/today"):
            return httpx.Response(200, json={"summary": {"generated_at": "2026-10-31T00:00:00Z", "body": "excluded"}})
        return httpx.Response(200, json={"total": 0, "items": []})
    async with httpx.AsyncClient(base_url="https://site.test", transport=httpx.MockTransport(handler)) as client:
        report = await collect_audit(client, [_event()])
    assert report["ok"] is False
    assert report["summary"]["generated_at"] == "2026-10-31T00:00:00Z"
    assert report["health"] == {"ok": True, "version": "test"}
    assert "body" not in report["summary"]
    assert report["independent_sample"]["observed"] == 0


@pytest.mark.asyncio
async def test_changing_inventory_does_not_produce_false_sample_misses():
    def handler(request):
        path = request.url.path
        if path.endswith("/sources"):
            return httpx.Response(200, json=[])
        if path.endswith("/articles"):
            offset = int(request.url.params["offset"])
            return httpx.Response(200, json={"total": 101 if offset == 0 else 102,
                "items": [{"id": str(i)} for i in range(offset, offset + 100)]})
        return httpx.Response(200, json={"ok": True})
    async with httpx.AsyncClient(base_url="https://site.test", transport=httpx.MockTransport(handler)) as client:
        report = await collect_audit(client, [_event()])
    assert report["ok"] is False
    assert report["independent_sample"] is None
