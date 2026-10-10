"""Read recorded Visitor Lab measurements. Never runs models or trusts arbitrary fields."""
from __future__ import annotations
import json
import math
from pathlib import Path

SUMMARY_PATH = Path(__file__).resolve().parents[2] / 'runs' / 'proofpath-summary.json'
PACKAGED_SUMMARY_PATH = Path(__file__).parent / 'fixtures' / 'visitor_lab_summary.json'
PRESETS = ('eu_technical', 'us_operations', 'strict_budget')


def _cell(raw: dict) -> dict:
    k, n, errors = raw['correct'], raw['n'], raw['errors']
    if any(type(v) is not int for v in (k, n, errors)) or not (0 <= k <= n and n > 0 and 0 <= errors <= n - k):
        raise ValueError('Invalid measurement counts')
    p, z = k / n, 1.96
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    spread = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return {'correct': k, 'n': n, 'errors': errors, 'rate': p,
            'percent': round(p*100, 1), 'interval': [round(max(0, center-spread)*100, 1), round(min(1, center+spread)*100, 1)]}


def load_results(path: Path | None = None) -> dict:
    """Return a safe presentation DTO, including honest unavailable/stub states."""
    out = {'state': 'unavailable', 'label': 'Recorded offline agent measurement',
           'message': 'No recorded measurement is available. No model calls are started by this page.'}
    try:
        selected = path if path is not None else (SUMMARY_PATH if SUMMARY_PATH.is_file() else PACKAGED_SUMMARY_PATH)
        raw = json.loads(selected.read_text())
        if raw.get('channel') != 'simulated' or type(raw.get('stub_context')) is not bool:
            raise ValueError('Invalid provenance')
        if raw['stub_context']:
            return {**out, 'state': 'stub', 'message': 'Recorded run used stub evaluation contexts. Results are withheld because they do not measure the implemented workspace.'}
        results = raw['results']
        arms = [{'id': arm, 'name': name, **_cell(results[arm])} for arm, name in (
            ('A', 'Baseline website'), ('B', 'Evidence context'))]
        presets = []
        for preset in PRESETS:
            if f'A|{preset}' in results and f'B|{preset}' in results:
                presets.append({'name': preset.replace('_', ' ').title(),
                                'a': _cell(results[f'A|{preset}']), 'b': _cell(results[f'B|{preset}'])})
        citations = raw['invalid_citations_arm_b']
        if type(citations) is not int or citations < 0:
            raise ValueError('Invalid citation count')
        models = raw['models']
        if not isinstance(models, list) or not all(isinstance(m, str) and len(m) < 200 for m in models):
            raise ValueError('Invalid model list')
        return {**out, 'state': 'ready', 'message': '', 'arms': arms, 'presets': presets,
                'experiment': str(raw.get('experiment', ''))[:120], 'created_at': str(raw.get('created_at', ''))[:40],
                'models': models, 'invalid_citations': citations}
    except FileNotFoundError:
        return out
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return {**out, 'state': 'invalid', 'message': 'Recorded summary could not be validated. Results are withheld; no substitute scores are shown.'}
