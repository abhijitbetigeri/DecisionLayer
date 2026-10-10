from sv.proofpath import comparison
from sv.proofpath.comparison import NOT_ENOUGH, ScoringContext, score, score_preferences
from sv.proofpath.requirements import preset_brief


def test_formulas():
    s, cov = score([("a", 2.0, 1.0), ("b", 1.0, 0.0), ("c", 1.0, None)])
    assert s == round(2 / 3, 3) and cov == 0.75


def test_zero_guards_return_none_not_zero():
    assert score([]) == (None, None)                                  # no preferences at all
    assert score([("a", 0.0, 1.0)]) == (None, None)                  # all weights zero
    assert score([("a", 1.0, None), ("b", 2.0, None)]) == (None, 0.0)  # nothing evaluated


def test_not_enough_evidence_note():
    brief = preset_brief("eu_technical", "ev")
    ctx = ScoringContext("relayworks", (), False, "business", 899.0)
    weights = {"implementation_effort": 1.0}
    s, cov, notes = score_preferences(brief, [], weights, ctx)
    assert s is None and cov == 0.0 and NOT_ENOUGH in notes


def test_quote_only_price_scores_cost_clarity_zero():
    brief = preset_brief("strict_budget", "ev")
    quote = ScoringContext("relayworks", (), False, "enterprise", None)
    assert comparison.RUBRIC["cost_clarity"].score(brief, quote) == 0.0
    assert comparison.RUBRIC["cost_clarity"].score(brief, ScoringContext("x", (), False, None, None)) is None
