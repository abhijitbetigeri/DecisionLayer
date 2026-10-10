"""The expected-decision matrix from proofpath/plan/shared-truth.md §4.

WS1 must expose:
    sv.proofpath.evaluation.decision_for(preset_id, product_id, *, poc_passed: bool,
                                         relayworks_v2: bool) -> FitDecision
computed with the real fixtures and the real decision rule (no hard-coded table).
Red until WS1 lands; green is the WS1 "done" bar.
"""
import pytest

from sv.proofpath.contracts import FitDecision as D

NV, FIT, NOT = D.needs_verification, D.fit, D.not_fit

CASES = [
    # preset,          product,      poc_passed, relayworks_v2, expected
    ("eu_technical",  "flowbridge", False, False, NV),
    ("eu_technical",  "flowbridge", True,  False, NV),     # SSO still unknown after the POC
    ("eu_technical",  "relayworks", False, False, NV),
    ("eu_technical",  "relayworks", True,  True,  NV),
    ("eu_technical",  "pipestack",  False, False, NOT),
    ("us_operations", "flowbridge", False, False, NV),
    ("us_operations", "flowbridge", True,  False, FIT),
    ("us_operations", "relayworks", True,  False, NV),
    ("us_operations", "pipestack",  True,  False, NV),
    ("strict_budget", "flowbridge", False, False, NOT),    # EU needs Business at $999 > $900
    ("strict_budget", "flowbridge", True,  False, NOT),
    ("strict_budget", "relayworks", False, False, NV),
    ("strict_budget", "relayworks", False, True,  NV),     # budget becomes unknown (quote), never fit
    ("strict_budget", "pipestack",  False, False, NOT),
]


@pytest.mark.parametrize("preset,product,poc,v2,expected", CASES)
def test_expected_decision(preset, product, poc, v2, expected):
    evaluation = pytest.importorskip("sv.proofpath.evaluation")
    assert evaluation.decision_for(preset, product, poc_passed=poc, relayworks_v2=v2) == expected
