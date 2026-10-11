"""Public read-only share links for frozen reports."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PROOFPATH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "0")
    monkeypatch.setenv("PROOFPATH_DISABLE_WORKER", "1")
    import sv.proofpath.app as mod
    return importlib.reload(mod).app


def _report(client):
    ev = client.post("/api/v1/evaluations", json={"preset_id": "eu_technical"}).json()["data"]
    eid, bid = ev["evaluation_id"], ev["brief"]["id"]
    snap = client.post(f"/api/v1/evaluations/{eid}/confirm", json={"brief_version_id": bid}).json()["data"]["comparison"]["id"]
    rep = client.post(f"/api/v1/evaluations/{eid}/reports",
                      json={"brief_version_id": bid, "comparison_snapshot_id": snap}).json()["data"]["id"]
    return eid, rep


def test_owner_shares_and_stranger_reads_only_the_report(app):
    with TestClient(app) as owner:
        eid, rep = _report(owner)
        path = owner.post(f"/api/v1/reports/{rep}/share").json()["data"]["path"]
        assert owner.post(f"/api/v1/reports/{rep}/share").json()["data"]["path"] == path   # idempotent
        stranger = TestClient(app)
        page = stranger.get(path)
        assert page.status_code == 200 and "Shared read-only copy" in page.text
        assert "share-btn" not in page.text and "Back to workspace" not in page.text
        assert stranger.get(f"/evaluations/{eid}").status_code == 404
        assert stranger.post(f"/api/v1/reports/{rep}/share").status_code == 404


def test_unknown_or_malformed_tokens_are_404(app):
    with TestClient(app) as c:
        assert c.get("/share/nope").status_code == 404
        assert c.get("/share/" + "A" * 24).status_code == 404
