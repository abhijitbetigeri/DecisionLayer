import importlib

from fastapi.testclient import TestClient


def test_insights_and_historical_sources_require_ownership(tmp_path, monkeypatch):
    monkeypatch.setenv("PROOFPATH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "0")
    monkeypatch.setenv("PROOFPATH_DEMO_MODE", "local")
    from sv.proofpath import app as module
    module = importlib.reload(module)
    with TestClient(module.app) as owner:
        created = owner.post("/api/v1/evaluations", json={"preset_id": "eu_technical"}).json()["data"]
        eid = created["evaluation_id"]
        owner.post(f"/api/v1/evaluations/{eid}/confirm", json={"brief_version_id": created["brief"]["id"]})
        result = owner.get(f"/api/v1/evaluations/{eid}/insights")
        assert result.status_code == 200
        data = result.json()["data"]
        assert any(s["requirement_key"] == "sso" for s in data["next_steps"])
        sid = data["timeline"][0]["source_version_ids"][0]
        path = f"/api/v1/evaluations/{eid}/sources/{sid}"
        assert owner.get(path).status_code == 200
        assert owner.get(f"/api/v1/evaluations/{eid}/sources/unrelated").status_code == 404
        with TestClient(module.app) as outsider:
            assert outsider.get(path).status_code == 404
            assert outsider.get(f"/api/v1/evaluations/{eid}/insights").status_code == 404
        assert owner.get("/visitor-lab").status_code == 200
        assert owner.get("/api/v1/visitor-lab/results").status_code == 200
