"""Session ownership, authorization, and exactly-once run submission."""
import pytest
from fastapi.testclient import TestClient
from tests.proofpath.test_api_journey import client, create_confirm, data, needs_core, needs_poc, run_poc


@needs_core
@needs_poc
def test_second_session_cannot_read_owned_objects(client):
    eid, bid, comparison = create_confirm(client)
    result = run_poc(client, eid, bid)
    report = data(client.post(f'/api/v1/evaluations/{eid}/reports', json={'brief_version_id': bid, 'comparison_snapshot_id': comparison['id']}), 201)
    assert result['artifacts'], 'POC must export inspectable artifacts'
    other = TestClient(client.app)
    paths = [f'/api/v1/evaluations/{eid}/workspace', '/api/v1/reports/' + report['id'], '/api/v1/runs/' + result['run']['id'], '/api/v1/artifacts/' + result['artifacts'][0]['id']]
    for path in paths:
        assert other.get(path).status_code == 404, path


def test_operator_routes_require_authorization(client):
    for path, payload in [('/api/v1/demo/source-update', {}), ('/api/v1/sources/unknown/review', {'decision': 'approved'}), ('/api/v1/demo/reset', {})]:
        assert client.post(path, json=payload).status_code == 403


@needs_core
def test_run_idempotency_and_active_conflict(client, monkeypatch):
    # Stop the worker so an active run cannot finish before the conflict assertion.
    from sv.proofpath import app as module
    module.worker.stop()
    if module.worker._thread:
        module.worker._thread.join(timeout=2)
    eid, bid, _ = create_confirm(client)
    path = f'/api/v1/evaluations/{eid}/runs'
    payload = {'brief_version_id': bid, 'idempotency_key': 'once'}
    first = data(client.post(path, json=payload), 202)
    duplicate = data(client.post(path, json=payload), 202)
    assert first['id'] == duplicate['id']
    assert client.post(path, json={**payload, 'brief_version_id': 'different'}).status_code == 409
    assert client.post(path, json={**payload, 'idempotency_key': 'twice'}).status_code == 409


@needs_core
def test_foreign_brief_cannot_be_confirmed_or_run(client):
    eid, _, _ = create_confirm(client)
    _, foreign_bid, _ = create_confirm(client)
    assert client.post(f'/api/v1/evaluations/{eid}/confirm', json={'brief_version_id': foreign_bid}).status_code == 404
    assert client.post(f'/api/v1/evaluations/{eid}/runs', json={'brief_version_id': foreign_bid, 'idempotency_key': 'foreign'}).status_code == 404


@needs_core
def test_unconfirmed_brief_cannot_run(client):
    created = data(client.post('/api/v1/evaluations', json={'preset_id': 'eu_technical'}), 201)
    response = client.post('/api/v1/evaluations/' + created['evaluation_id'] + '/runs', json={'brief_version_id': created['brief']['id'], 'idempotency_key': 'unconfirmed'})
    assert response.status_code == 409
