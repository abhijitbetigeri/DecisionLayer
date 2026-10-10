from sv.proofpath import evidence, evaluation, requirements
from sv.proofpath.contracts import Evaluation, ReviewStatus
from sv.proofpath.insights import build_insights
from sv.proofpath.repository import Repository


def setup(preset):
    repo = Repository(':memory:')
    evidence.seed(repo)
    ev = repo.create_evaluation(Evaluation(session_id='insights', preset_id=preset, brief_text='demo'))
    brief = repo.append_brief(requirements.preset_brief(preset, ev.id))
    repo.confirm_brief(brief.id)
    evaluation.recompute(repo, ev.id)
    return repo, ev, brief


def test_eu_poc_resolves_recovery_but_keeps_sso_gap():
    repo, ev, brief = setup('eu_technical')
    first = build_insights(repo, ev.id)
    evaluation.add_passing_run(repo, ev.id, brief.id)
    result = build_insights(repo, ev.id)
    assert len(result['timeline']) == len(first['timeline']) + 1
    latest = result['timeline'][-1]
    assert 'needs verification' in latest['summary'] and 'sso' in latest['summary']
    recovery = next(c for c in latest['changes'] if c['product_id'] == 'flowbridge' and c['requirement_key'] == 'recovery_demonstrated')
    assert recovery['before']['status'] == 'unknown'
    assert recovery['after']['basis'] == 'demonstrated' and len(recovery['test_result_ids']) == 4
    steps = [s for s in result['next_steps'] if s['product_id'] == 'flowbridge']
    assert any(s['requirement_key'] == 'sso' and s['owner'] == 'Vendor security' for s in steps)
    assert not any(s['requirement_key'] == 'recovery_demonstrated' for s in steps)
    assert build_insights(repo, ev.id) == result  # polling never invents history


def test_us_poc_changes_decision_to_fit():
    repo, ev, brief = setup('us_operations')
    evaluation.add_passing_run(repo, ev.id, brief.id)
    result = build_insights(repo, ev.id)
    decision = next(c for c in result['timeline'][-1]['changes'] if c['product_id'] == 'flowbridge' and c['field'] == 'decision')
    assert decision['before'] == 'needs_verification' and decision['after'] == 'fit'
    assert not any(s['product_id'] == 'flowbridge' for s in result['next_steps'])


def test_pending_source_does_not_change_timeline_and_approved_price_does():
    repo, ev, brief = setup('eu_technical')
    initial = build_insights(repo, ev.id)
    update = evidence.simulate_update(repo, 'relayworks_v2', screen=False)
    pending = build_insights(repo, ev.id)
    assert pending['timeline'] == initial['timeline'] and pending['stale']
    assert pending['next_steps'][0]['action'] == 'review_source'
    evidence.review(repo, update.source_version.id, ReviewStatus.approved)
    final = build_insights(repo, ev.id)
    latest = final['timeline'][-1]
    plan = next(c for c in latest['changes'] if c['product_id'] == 'relayworks' and c['field'] == 'cheapest_qualifying_plan')
    assert plan['before'] == 'business' and plan['after'] == 'enterprise'
    assert update.source_version.id in latest['source_version_ids']
    assert latest['source_version_ids'] != initial['timeline'][0]['source_version_ids']
    assert final['timeline'][0] == initial['timeline'][0]


def test_unconfirmed_edit_requires_confirmation_not_stale_actions():
    repo, ev, brief = setup('us_operations')
    requirements.edit_brief(repo, ev.id, {'expected_version': 1, 'goal': 'edited', 'systems': [], 'requirements': [{'key': 'sso', 'hard': True}]})
    result = build_insights(repo, ev.id)
    assert result['stale']
    assert [s['action'] for s in result['next_steps']] == ['confirm_brief']
