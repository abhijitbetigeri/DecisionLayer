import os

os.environ["PROOFPATH_ENABLE_LLM"] = "0"

import pytest

from sv.proofpath import requirements
from sv.proofpath.contracts import Evaluation
from sv.proofpath.fixtures import DEMO_BRIEF
from sv.proofpath.repository import ConflictError, Repository


def test_demo_brief_falls_back_to_preset_when_llm_disabled(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "0")
    b = requirements.parse_brief(DEMO_BRIEF, "ev-1", None)
    assert b.parsed_by == "preset"
    assert {r.key for r in b.requirements if r.hard} == {"eu_hosting", "sso", "recovery_demonstrated"}
    assert b.input_hash == requirements.input_hash(DEMO_BRIEF)
    assert b.confirmed_at is None


def test_model_output_is_validated_against_allowlist(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "1")
    monkeypatch.setattr(requirements, "_call_model", lambda model, text: {
        "goal": "Sync", "systems": ["Salesforce (CRM)"],
        "requirements": [{"key": "eu_hosting", "hard": True}, {"key": "sso", "hard": True},
                         {"key": "recovery_demonstrated", "hard": True},
                         {"key": "hipaa", "hard": True}, {"key": "idempotent_delivery", "hard": False}],
        "unrecognized": ["SOC 2 report"]})
    b = requirements.parse_brief(DEMO_BRIEF, "ev-1", None)
    assert b.parsed_by == requirements.MODELS[0]
    assert [r.key for r in b.requirements] == ["eu_hosting", "sso", "recovery_demonstrated", "idempotent_delivery"]
    assert "hipaa" in b.dropped_terms and "SOC 2 report" in b.dropped_terms


def test_model_chain_falls_through_to_kimi_then_preset(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "1")
    calls = []

    def fake(model, text):
        calls.append(model)
        if model == requirements.MODELS[0]:
            raise TimeoutError("down")
        return {"requirements": [{"key": "made_up"}]}       # invalid: nothing allowlisted

    monkeypatch.setattr(requirements, "_call_model", fake)
    b = requirements.parse_brief(DEMO_BRIEF, "ev-1", "eu_technical")
    assert calls == list(requirements.MODELS)
    assert b.parsed_by == "preset"


def test_edit_brief_creates_new_version_and_checks_expected_version():
    repo = Repository(":memory:")
    ev = repo.create_evaluation(Evaluation(session_id="s", brief_text=DEMO_BRIEF))
    v1 = repo.append_brief(requirements.preset_brief("eu_technical", ev.id))
    body = {"expected_version": 1, "goal": "g", "systems": ["Salesforce"], "persona": "finance",
            "requirements": [{"key": "eu_hosting", "hard": True}, {"key": "bogus", "hard": True},
                             {"key": "sso", "hard": False, "weight": 0}]}
    v2 = requirements.edit_brief(repo, ev.id, body)
    assert v2.version == 2 and v2.parsed_by == "manual" and v2.dropped_terms == ["bogus"]
    assert v2.requirements[1].weight == 0.0
    assert repo.get_evaluation(ev.id).current_brief_version_id == v2.id
    assert repo.get_brief(v1.id).version == 1                # old version untouched
    with pytest.raises(ConflictError):
        requirements.edit_brief(repo, ev.id, body)            # stale expected_version
