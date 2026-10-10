import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sv.proofpath.visitor_lab import load_results


def summary():
    return {'channel': 'simulated', 'stub_context': False, 'experiment': 'test',
            'created_at': '2026-10-10T00:00:00Z', 'models': ['model'], 'invalid_citations_arm_b': 0,
            'results': {'A': {'correct': 15, 'n': 24, 'errors': 3, 'rate': 0, 'wilson95': [0, 0]},
                        'B': {'correct': 24, 'n': 24, 'errors': 0}}}


def write(tmp_path, data):
    path = tmp_path / 'summary.json'
    path.write_text(json.dumps(data))
    return path


def test_missing_results_are_honest(tmp_path):
    assert load_results(tmp_path / 'absent')['state'] == 'unavailable'


def test_counts_drive_scores_not_untrusted_rate(tmp_path):
    result = load_results(write(tmp_path, summary()))
    assert result['state'] == 'ready'
    assert result['arms'][0]['percent'] == 62.5
    assert result['arms'][0]['interval'] == [42.7, 78.8]
    assert result['arms'][1]['interval'] == [86.2, 100.0]
    assert result['arms'][0]['errors'] == 3


def test_stub_scores_withheld(tmp_path):
    data = summary()
    data['stub_context'] = True
    result = load_results(write(tmp_path, data))
    assert result['state'] == 'stub'
    assert 'arms' not in result


def test_invalid_results_withheld(tmp_path):
    for count in [-1, True, 25]:
        data = summary()
        data['results']['A']['correct'] = count
        assert load_results(write(tmp_path, data))['state'] == 'invalid'
    assert load_results(write(tmp_path, []))['state'] == 'invalid'


def test_template_escapes_metadata_and_explains_limits(tmp_path):
    data = summary()
    data['experiment'] = '<script>alert(1)</script>'
    result = load_results(write(tmp_path, data))
    templates = Path(__file__).resolve().parents[2] / 'sv/proofpath/templates'
    env = Environment(loader=FileSystemLoader(templates), autoescape=select_autoescape())
    rendered = env.get_template('visitor_lab.html').render(results=result)
    assert '<script>alert(1)</script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert 'causal lift claim' in rendered
    assert '15 / 24' in rendered
    assert 'No paid model sweep' in rendered
