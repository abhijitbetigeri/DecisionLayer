"""WS5 buyer agent: citation rejection, rule-based labeling, scoring, bounded loop. No network."""
import json
from types import SimpleNamespace

import pytest

from sv.proofpath import agent as A
from sv.proofpath.contracts import (BriefVersion, ComparisonSnapshot, Evaluation, FindingStatus,
                                    FitDecision, ProductComparison)
from sv.proofpath.repository import Repository


def _ctx():
    return A._example_context()


def _tool_call(name, args, id_="c1"):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)),
                           model_dump=lambda: {"id": id_, "type": "function",
                                               "function": {"name": name, "arguments": json.dumps(args)}})


def _resp(*calls, content=""):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content,
                                                                            tool_calls=list(calls) or None))])


def scripted(*responses):
    """A fake llm.chat that returns the scripted responses in order and records calls."""
    seq = list(responses)
    calls = []

    def chat(model, messages, **kw):
        calls.append(model)
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    chat.calls = calls
    return chat


SUBMIT_OK = {"decision": "needs_verification",
             "requirement_statuses": {"eu_hosting": "met", "sso": "unknown", "recovery_demonstrated": "met",
                                      "made_up_key": "met"},
             "citations": ["clm-fb-eu", "tr-4", "clm-fake-999", "tr-4"]}


def test_citations_to_nonexistent_ids_are_rejected():
    chat = scripted(_resp(_tool_call("get_agent_context", {})), _resp(_tool_call("submit_decision", SUBMIT_OK)))
    res = A.evaluate_context(_ctx(), "e1", None, preset_id="eu_technical", chat=chat, use_llm=True)
    assert res.mode == "ai_agent" and res.model_id == A.PRIMARY_MODEL
    assert res.citations == ["clm-fb-eu", "tr-4"]
    assert res.rejected_citations == ["clm-fake-999"]
    assert "made_up_key" not in res.requirement_statuses        # only the brief's hard keys
    assert res.turns == 2


def test_split_citations_only_accepts_existing_claims_and_tests():
    ok, bad = A.split_citations(["clm-ps-eu", "tr-1", "req-sso", "art-1", ""], _ctx())
    assert ok == ["clm-ps-eu", "tr-1"] and bad == ["req-sso", "art-1"]


def test_scored_against_expected_decision():
    wrong = dict(SUBMIT_OK, decision="fit")
    chat = scripted(_resp(_tool_call("submit_decision", wrong)))
    res = A.evaluate_context(_ctx(), "e1", None, preset_id="eu_technical", chat=chat, use_llm=True)
    assert res.expected_decision == FitDecision.needs_verification
    assert res.decision == FitDecision.fit and res.correct is False


@pytest.mark.parametrize("preset,poc,expected", [
    ("eu_technical", True, "needs_verification"), ("us_operations", True, "fit"),
    ("us_operations", False, "needs_verification"), ("strict_budget", False, "not_fit")])
def test_expected_table_matches_shared_truth(preset, poc, expected, monkeypatch):
    monkeypatch.setattr(A, "poc_passed", lambda ctx: poc)
    assert A.expected_decision(_ctx(), preset).value == expected


def test_llm_disabled_returns_labeled_rule_based(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "0")
    def boom(*a, **k):
        raise AssertionError("LLM must not be called")
    res = A.evaluate_context(_ctx(), "e1", None, preset_id="eu_technical", chat=boom)
    assert res.mode == "rule_based" and res.model_id is None
    assert A.label(res) == "Rule-based evaluation"
    assert res.decision == FitDecision.needs_verification and res.correct is True
    assert res.requirement_statuses["sso"] == FindingStatus.unknown
    assert set(res.citations) == {"clm-fb-eu", "tr-2", "tr-3", "tr-4"}


def test_fallback_chain_primary_then_qwen_then_rule_based():
    # primary errors, fallback succeeds
    chat = scripted(RuntimeError("provider down"), _resp(_tool_call("submit_decision", SUBMIT_OK)))
    res = A.evaluate_context(_ctx(), "e1", None, chat=chat, use_llm=True)
    assert chat.calls == [A.PRIMARY_MODEL, A.FALLBACK_MODEL] and res.model_id == A.FALLBACK_MODEL
    # both fail -> rule-based, labeled
    chat = scripted(RuntimeError("x"), _resp(_tool_call("submit_decision", {"decision": "maybe"})))
    res = A.evaluate_context(_ctx(), "e1", None, chat=chat, use_llm=True)
    assert res.mode == "rule_based" and A.label(res) == "Rule-based evaluation"


def test_turn_cap_is_enforced():
    chat = scripted(*[_resp(content="thinking") for _ in range(A.MAX_TURNS)])
    with pytest.raises(A.AgentFailure):
        A.run_tool_loop("m", "s", "u", [A.SUBMIT_TOOL], lambda n, a: "", chat=chat)
    assert len(chat.calls) == A.MAX_TURNS


def test_banned_or_unknown_models_never_used():
    assert A.model_chain("openrouter/deepseek/deepseek-v3")[0] == A.PRIMARY_MODEL
    assert A.model_chain("openrouter/openai/gpt-oss-20b")[0] == A.PRIMARY_MODEL
    assert A.model_chain("openrouter/moonshotai/kimi-k2")[0] == "openrouter/moonshotai/kimi-k2"


def test_run_agent_evaluation_stores_result_with_repository(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "0")
    repo = Repository(":memory:")
    ex = _ctx()
    ev = repo.create_evaluation(Evaluation(session_id="s", preset_id="strict_budget", brief_text=""))
    brief = BriefVersion.model_validate({**ex["brief"], "id": "b1", "evaluation_id": ev.id})
    repo.append_brief(brief)
    snap = ComparisonSnapshot(evaluation_id=ev.id, brief_version_id="b1", source_version_ids=[], run_ids=[],
                              products=[ProductComparison.model_validate(p) for p in ex["products"]])
    repo.put_comparison(snap)
    ctx = A.agent_context(repo, ev.id)
    assert ctx["comparison_snapshot_id"] == snap.id and ctx["brief"]["id"] == "b1"
    res = A.run_agent_evaluation(repo, ev.id, None)
    assert repo.latest_agent_result(ev.id).id == res.id
    assert res.input_version == f"b1+{snap.id}"
    # strict_budget expects not_fit for FlowBridge; this context's findings say needs_verification
    assert res.expected_decision == FitDecision.not_fit and res.correct is False


def test_example_evaluation_served_in_stub_mode():
    assert A.agent_context(Repository(":memory:"), A.EXAMPLE_EVALUATION_ID)["evaluation_id"] == A.EXAMPLE_EVALUATION_ID


def test_jev_summary_check_falls_back_to_template(monkeypatch):
    from sv import jev

    def unavailable(*a, **k):
        raise jev.JevUnavailable("no key")
    monkeypatch.setattr(jev, "yes_probability", unavailable)
    assert A.checked_summary("FlowBridge has SSO.", "facts", "TEMPLATE") == ("TEMPLATE", "jev_unavailable")
    monkeypatch.setattr(jev, "yes_probability", lambda *a, **k: 0.1)
    assert A.checked_summary("FlowBridge has SSO.", "facts", "TEMPLATE") == ("TEMPLATE", "jev_unsupported")
    monkeypatch.setattr(jev, "yes_probability", lambda *a, **k: 0.9)
    assert A.checked_summary("EU on Business.", "facts", "TEMPLATE") == ("EU on Business.", "jev_supported")
