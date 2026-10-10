"""C1-C3 contract journeys, isolated from user data and external models."""
import importlib
import importlib.util
import time

import pytest
from fastapi.testclient import TestClient


def available(*modules):
    try:
        return all(importlib.util.find_spec('sv.proofpath.' + m) for m in modules)
    except ModuleNotFoundError:
        return False


needs_core = pytest.mark.skipif(not available('requirements', 'evaluation', 'evidence'), reason='WS1 not built yet')
needs_poc = pytest.mark.skipif(not available('poc.runner', 'reports'), reason='POC/report modules not built yet')


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('PROOFPATH_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('PROOFPATH_ENABLE_LLM', '0')
    monkeypatch.setenv('PROOFPATH_OPERATOR_TOKEN', 'qa-local-token')
    monkeypatch.setenv('PROOFPATH_DEMO_MODE', 'local')
    monkeypatch.delenv('PROOFPATH_DISABLE_WORKER', raising=False)
    from sv.proofpath import app as module
    module = importlib.reload(module)
    with TestClient(module.app) as c:
        yield c


def data(response, status=200):
    assert response.status_code == status, response.text
    body = response.json()
    assert not body.get('stub'), 'Expected real implementation, received stub'
    return body['data']


def create_confirm(client, preset='eu_technical'):
    created = data(client.post('/api/v1/evaluations', json={'preset_id': preset}), 201)
    eid, bid = created['evaluation_id'], created['brief']['id']
    confirmed = data(client.post(f'/api/v1/evaluations/{eid}/confirm', json={'brief_version_id': bid}))
    return eid, bid, confirmed['comparison']


def workspace(client, eid):
    return data(client.get(f'/api/v1/evaluations/{eid}/workspace'))


def product(comparison, name='flowbridge'):
    return next(p for p in comparison['products'] if p['product_id'] == name)


def run_poc(client, eid, bid):
    run = data(client.post(f'/api/v1/evaluations/{eid}/runs', json={'brief_version_id': bid, 'idempotency_key': 'qa-run'}), 202)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = data(client.get('/api/v1/runs/' + run['id']))
        if result['run']['state'] == 'closed':
            assert result['run']['outcome'] == 'passed', result
            assert len(result['results']) == 4
            assert all(t['status'] == 'pass' for t in result['results'])
            return result
        time.sleep(.05)
    pytest.fail('POC did not close within 15 seconds')


@needs_core
@needs_poc
def test_c1_eu_journey(client):
    eid, bid, comparison = create_confirm(client)
    fb = product(comparison)
    assert fb['decision'] == 'needs_verification'
    assert next(f for f in fb['findings'] if f['requirement_key'] == 'sso')['status'] == 'unknown'
    run_poc(client, eid, bid)
    current = workspace(client, eid)['comparison']
    fb = product(current)
    recovery = next(f for f in fb['findings'] if f['requirement_key'] == 'recovery_demonstrated')
    assert (recovery['status'], recovery['basis']) == ('met', 'demonstrated')
    assert fb['decision'] == 'needs_verification'
    report = data(client.post(f'/api/v1/evaluations/{eid}/reports', json={'brief_version_id': bid, 'comparison_snapshot_id': current['id']}), 201)
    assert data(client.get('/api/v1/reports/' + report['id'])) == report


@needs_core
@needs_poc
def test_us_operations_reaches_fit(client):
    eid, bid, before = create_confirm(client, 'us_operations')
    assert product(before)['decision'] == 'needs_verification'
    run_poc(client, eid, bid)
    assert product(workspace(client, eid)['comparison'])['decision'] == 'fit'


@needs_core
@needs_poc
def test_c2_pending_approve_preserves_report(client):
    eid, bid, before = create_confirm(client, 'strict_budget')
    report = data(client.post(f'/api/v1/evaluations/{eid}/reports', json={'brief_version_id': bid, 'comparison_snapshot_id': before['id']}), 201)
    headers = {'x-operator-token': 'qa-local-token'}
    update = data(client.post('/api/v1/demo/source-update', json={}, headers=headers))
    pending = workspace(client, eid)['comparison']
    assert pending['products'] == before['products']
    sid = update['source_version']['id']
    data(client.post(f'/api/v1/sources/{sid}/review', json={'decision': 'approved'}, headers=headers))
    after = workspace(client, eid)['comparison']
    rw = product(after, 'relayworks')
    budget = next(f for f in rw['findings'] if f['requirement_key'] == 'budget_monthly_usd')
    assert budget['status'] == 'unknown'
    assert data(client.get('/api/v1/reports/' + report['id'])) == report
    events = data(client.get(f'/api/v1/evaluations/{eid}/events'))
    assert any(e['type'] == 'comparison_updated' for e in events)


@needs_core
def test_c2_rejection_preserves_approved_evidence(client):
    eid, _, before = create_confirm(client)
    headers = {'x-operator-token': 'qa-local-token'}
    update = data(client.post('/api/v1/demo/source-update', json={}, headers=headers))
    data(client.post('/api/v1/sources/' + update['source_version']['id'] + '/review', json={'decision': 'rejected'}, headers=headers))
    after = workspace(client, eid)['comparison']
    assert after['products'] == before['products']
    assert after['source_version_ids'] == before['source_version_ids']


@needs_core
@pytest.mark.skipif(not available('agent'), reason='WS5 not built yet')
def test_c3_agent_uses_workspace_ids_and_rule_based_fallback(client):
    eid, bid, _ = create_confirm(client)
    human = workspace(client, eid)
    ctx = data(client.get(f'/api/v1/evaluations/{eid}/agent-context'))
    assert ctx['evaluation_id'] == eid and ctx['brief']['id'] == bid
    assert ctx['comparison_snapshot_id'] == human['comparison']['id']
    assert ctx['products'] == human['comparison']['products']
    assert {c['id'] for c in ctx['claims']} == {c['id'] for c in human['claims']}
    result = data(client.post(f'/api/v1/evaluations/{eid}/agent-evaluation', json={}))
    assert result['mode'] == 'rule_based'
    assert result['decision'] == 'needs_verification'
