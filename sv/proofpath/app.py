"""Decision Layer · Evaluation Workspace: FastAPI composition (coordinator-owned).

  uv run uvicorn sv.proofpath.app:app --host 127.0.0.1 --port 8001

Routes follow proofpath/README.md "HTTP contracts". Each route calls the owning workstream's module
through the agreed function (see proofpath/plan/workstreams/*). Until a module lands, the route
serves the matching example payload from sv/proofpath/examples/ with `"stub": true`, so UI work can
proceed against the frozen contract.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from pydantic import BaseModel

from sv.proofpath import auth
from sv.proofpath.contracts import (SCENARIO_VERSION, Evaluation, Event, EventType, POCRun,
                                    ReviewStatus, RunState, new_id)
from sv.proofpath.repository import ConflictError, NotFoundError, Repository, dumps
from sv.proofpath.worker import Worker

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
DATA_DIR = Path(os.environ.get("PROOFPATH_DATA_DIR", ".proofpath-data"))
DEMO_MODE = os.environ.get("PROOFPATH_DEMO_MODE", "local")    # local | stage | public

repo = Repository(DATA_DIR / "proofpath.db")
worker = Worker(repo)
templates = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))


# ------------------------------------------------------------------ wiring helpers
def _module(name: str):
    try:
        return importlib.import_module(f"sv.proofpath.{name}")
    except ImportError:
        return None


def _impl(module: str, fn: str):
    """The real implementation if its module and function exist, else None (serve a stub)."""
    mod = _module(module)
    return getattr(mod, fn, None) if mod else None


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def ok(data, status: int = 200, stub: bool = False) -> JSONResponse:
    if isinstance(data, BaseModel):
        data = dumps(data)
    body = {"schema_version": 1, "data": data}
    if stub:
        body["stub"] = True
    return JSONResponse(body, status_code=status)


def err(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse({"schema_version": 1, "error": {"code": code, "message": message, "details": details or {}}},
                        status_code=status)


EXAMPLE_EVALUATION_ID = "11111111-1111-4111-8111-111111111111"


def _owned_evaluation(request: Request, evaluation_id: str) -> Evaluation:
    # Stub mode only: until WS1 lands, the example evaluation is viewable by anyone so UI work can
    # proceed at /evaluations/<example id>. Disappears automatically once requirements.py exists.
    if evaluation_id == EXAMPLE_EVALUATION_ID and not _impl("requirements", "parse_brief"):
        return Evaluation.model_validate(_example("workspace")["evaluation"])
    try:
        ev = repo.get_evaluation(evaluation_id)
    except NotFoundError:
        raise HTTPException(404, "evaluation not found")
    if ev.session_id != auth.session_id(request) and not auth.is_operator(request):
        raise HTTPException(404, "evaluation not found")        # do not reveal existence
    return ev


def emit(evaluation_id: str | None, type_: EventType, run_id: str | None = None, **payload) -> None:
    repo.append_event(Event(evaluation_id=evaluation_id, run_id=run_id, type=type_, payload=payload))


def track(evaluation_id: str, name: str) -> None:
    """Internal telemetry (WS5); never breaks the request if telemetry fails."""
    record = _impl("telemetry", "record")
    if not record:
        return
    try:
        record(repo, evaluation_id, name, "live")
        qualified = _impl("telemetry", "qualified_evaluation_completed")
        if qualified and name in ("brief_confirmed", "poc_completed") and qualified(repo, evaluation_id):
            record(repo, evaluation_id, "qualified_evaluation_completed", "live")
    except Exception:
        pass


# ------------------------------------------------------------------ app lifecycle
@asynccontextmanager
async def lifespan(_: FastAPI):
    seed = _impl("evidence", "seed")
    if seed:
        seed(repo)                                  # idempotent: seeds once per data dir
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Decision Layer · Evaluation Workspace", lifespan=lifespan)
from sv.proofpath import public_guard
public_guard.install(app)
app.mount("/static", StaticFiles(directory=HERE / "static", check_dir=False), name="static")


@app.middleware("http")
async def session_cookie(request: Request, call_next):
    new_sid = None
    if not request.cookies.get(auth.SESSION_COOKIE):
        new_sid = auth.new_session_id()
        request.state.new_session = new_sid
    response = await call_next(request)
    if new_sid:
        response.set_cookie(auth.SESSION_COOKIE, new_sid, httponly=True, samesite="lax",
                            secure=DEMO_MODE == "public")
    return response


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    codes = {400: "invalid_operation", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
             409: "conflict", 422: "invalid_schema", 503: "unavailable"}
    return err(exc.status_code, codes.get(exc.status_code, "error"), str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return err(422, "invalid_schema", "request body failed validation", {"errors": exc.errors()[:5]})


@app.exception_handler(ConflictError)
async def conflict_error(_: Request, exc: ConflictError):
    return err(409, "conflict", str(exc))


@app.exception_handler(NotFoundError)
async def not_found_error(_: Request, exc: NotFoundError):
    return err(404, "not_found", "resource not found")


# ------------------------------------------------------------------ request bodies
class CreateEvaluation(BaseModel):
    brief_text: str = ""
    preset_id: str | None = None


class EditBrief(BaseModel):
    expected_version: int
    goal: str
    systems: list[str]
    persona: str = "technical"
    requirements: list[dict]


class ConfirmBrief(BaseModel):
    brief_version_id: str


class StartRun(BaseModel):
    brief_version_id: str
    scenario_version: str = SCENARIO_VERSION
    idempotency_key: str


class SourceUpdate(BaseModel):
    scenario_id: str = "relayworks_v2"


class Review(BaseModel):
    decision: ReviewStatus


class CreateReport(BaseModel):
    brief_version_id: str
    comparison_snapshot_id: str


class AgentEvaluation(BaseModel):
    model: str | None = None


# ------------------------------------------------------------------ pages
def _page(template: str, fallback_title: str, **ctx) -> HTMLResponse:
    try:
        html = templates.get_template(template).render(demo_mode=DEMO_MODE, **ctx)
    except TemplateNotFound:
        html = (f"<!doctype html><title>{fallback_title}</title><h1>{fallback_title}</h1>"
                f"<p>Template <code>{template}</code> not built yet.</p><pre>{json.dumps(ctx, default=str)[:2000]}</pre>")
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _page("home.html", "FlowBridge", operator=auth.is_operator(request))


@app.get("/visitor-lab", response_class=HTMLResponse)
def visitor_lab_page():
    from sv.proofpath.visitor_lab import load_results
    return _page("visitor_lab.html", "Visitor Lab", results=load_results())


@app.get("/api/v1/visitor-lab/results")
def visitor_lab_results():
    from sv.proofpath.visitor_lab import load_results
    return ok(load_results())


@app.get("/api/v1/evaluations/{evaluation_id}/insights")
def evaluation_insights(request: Request, evaluation_id: str):
    _owned_evaluation(request, evaluation_id)
    from sv.proofpath.insights import build_insights
    return ok(build_insights(repo, evaluation_id))


@app.get("/api/v1/evaluations/{evaluation_id}/sources/{source_id}")
def insight_source(request: Request, evaluation_id: str, source_id: str):
    _owned_evaluation(request, evaluation_id)
    snapshots = repo._list("comparisons", "evaluation_id=?", (evaluation_id,))
    if not any(source_id in snapshot.source_version_ids for snapshot in snapshots):
        raise HTTPException(404, "source not found in this evaluation")
    return ok(repo.get_source_version(source_id))


@app.get("/evaluations/{evaluation_id}", response_class=HTMLResponse)
def workspace_page(request: Request, evaluation_id: str):
    _owned_evaluation(request, evaluation_id)
    return _page("workspace.html", "Evaluation Workspace", evaluation_id=evaluation_id,
                 operator=auth.is_operator(request))


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_page(request: Request, report_id: str):
    report = repo.get_report(report_id)
    _owned_evaluation(request, report.evaluation_id)
    return _page("report.html", "Evaluation report", report=dumps(report))


@app.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt():
    return ("# FlowBridge (fictional) · Evaluation Workspace by Decision Layer\n"
            "> Fictional products and evidence; live tests use local mock integrations.\n\n"
            "Agents: create an evaluation with POST /api/v1/evaluations {brief_text}, confirm it, then read\n"
            "GET /api/v1/evaluations/{id}/agent-context for facts, citations and limitations.\n")


@app.post("/operator/login")
async def operator_login(request: Request):
    is_form = "form" in request.headers.get("content-type", "")
    if is_form:   # parse urlencoded by hand: avoids a python-multipart dependency
        from urllib.parse import parse_qs
        token = (parse_qs((await request.body()).decode()).get("token") or [None])[0]
    else:
        try:
            token = (await request.json()).get("token")
        except Exception:
            token = None
    if not auth.check_token(token):
        raise HTTPException(403, "invalid operator token")
    resp = RedirectResponse(request.headers.get("referer") or "/", status_code=303) if is_form else ok({"operator": True})
    resp.set_cookie(auth.OPERATOR_COOKIE, auth.grant_operator(), httponly=True, samesite="strict",
                    secure=DEMO_MODE == "public")
    return resp


# ------------------------------------------------------------------ API
API = "/api/v1"


@app.get(f"{API}/health")
@app.get("/health")
def health():
    from sv import jev
    return ok({"ready": True, "demo_mode": DEMO_MODE,
               "modules": {m: _module(m) is not None for m in
                           ["requirements", "evidence", "evaluation", "comparison", "reports", "agent", "telemetry", "poc.runner"]},
               "jev_configured": jev.available(), "llm_enabled": os.environ.get("PROOFPATH_ENABLE_LLM", "1") != "0"})


@app.get(f"{API}/showcase")
def showcase():
    """Read-only workspace for the homepage hero preview: a real eu_technical evaluation seeded once
    under a dedicated session, so the hero shows the product truthfully. Falls back to the example."""
    parse, recompute, build = (_impl("requirements", "parse_brief"), _impl("evaluation", "recompute"),
                               _impl("evaluation", "workspace"))
    if not (parse and recompute and build):
        return ok(_example("workspace"), stub=True)
    try:
        ev_id = repo.get_meta("showcase_evaluation_id")
        if not ev_id:
            ev = repo.create_evaluation(Evaluation(session_id="showcase", preset_id="eu_technical", brief_text=""))
            brief = repo.append_brief(parse("", ev.id, "eu_technical"))
            repo.confirm_brief(brief.id)
            recompute(repo, ev.id)
            repo.set_meta("showcase_evaluation_id", ev.id)
            ev_id = ev.id
        return ok(build(repo, ev_id))
    except Exception:
        return ok(_example("workspace"), stub=True)


@app.get(f"{API}/showcase/agent-context")
def showcase_agent_context():
    """Public, read-only agent view of the showcase evaluation (what the homepage advertises to agents)."""
    showcase()                                        # ensures the showcase evaluation exists
    ev_id, ctx = repo.get_meta("showcase_evaluation_id"), _impl("agent", "agent_context")
    if not (ev_id and ctx):
        return ok(_example("agent_context"), stub=True)
    return ok(ctx(repo, ev_id))


@app.post(f"{API}/evaluations")
def create_evaluation(request: Request, body: CreateEvaluation):
    parse = _impl("requirements", "parse_brief")
    if not parse:
        return ok(_example("create_evaluation"), 201, stub=True)
    if not body.brief_text and not body.preset_id:
        raise HTTPException(400, "brief_text or preset_id required")
    ev = repo.create_evaluation(Evaluation(session_id=auth.session_id(request), preset_id=body.preset_id,
                                           brief_text=body.brief_text))
    brief = parse(body.brief_text, ev.id, body.preset_id)
    repo.append_brief(brief)
    emit(ev.id, EventType.brief_parsed, parsed_by=brief.parsed_by, version=brief.version)
    return ok({"evaluation_id": ev.id, "brief": dumps(brief)}, 201)


@app.put(f"{API}/evaluations/{{evaluation_id}}/brief")
def edit_brief(request: Request, evaluation_id: str, body: EditBrief):
    _owned_evaluation(request, evaluation_id)
    edit = _impl("requirements", "edit_brief")
    if not edit:
        return ok(_example("brief"), stub=True)
    brief = edit(repo, evaluation_id, body.model_dump())
    return ok(brief)


@app.post(f"{API}/evaluations/{{evaluation_id}}/confirm")
def confirm(request: Request, evaluation_id: str, body: ConfirmBrief):
    _owned_evaluation(request, evaluation_id)
    if repo.get_brief(body.brief_version_id).evaluation_id != evaluation_id:
        raise HTTPException(404, "brief not found")
    recompute = _impl("evaluation", "recompute")
    if not recompute:
        return ok(_example("confirm"), stub=True)
    brief = repo.confirm_brief(body.brief_version_id)
    emit(evaluation_id, EventType.brief_confirmed, brief_version_id=brief.id)
    snapshot = recompute(repo, evaluation_id)
    emit(evaluation_id, EventType.workspace_generated, comparison_snapshot_id=snapshot.id)
    track(evaluation_id, "brief_confirmed")
    return ok({"brief": dumps(brief), "comparison": dumps(snapshot)})


@app.get(f"{API}/evaluations/{{evaluation_id}}/workspace")
def get_workspace(request: Request, evaluation_id: str):
    _owned_evaluation(request, evaluation_id)
    build = _impl("evaluation", "workspace")
    if not build:
        return ok(_example("workspace"), stub=True)
    return ok(build(repo, evaluation_id))


@app.post(f"{API}/evaluations/{{evaluation_id}}/runs", status_code=202)
def start_run(request: Request, evaluation_id: str, body: StartRun):
    evaluation = _owned_evaluation(request, evaluation_id)
    if body.scenario_version != SCENARIO_VERSION:
        raise HTTPException(400, f"unsupported scenario {body.scenario_version}")
    payload_hash = hashlib.sha256(f"{body.brief_version_id}|{body.scenario_version}".encode()).hexdigest()
    with repo.transaction():
        existing = repo.find_run_by_key(evaluation_id, body.idempotency_key)
        if existing:
            if existing.payload_hash != payload_hash:
                raise ConflictError("idempotency key reused with a different payload")
            return ok(existing, 202)
        brief = repo.get_brief(body.brief_version_id)
        if brief.evaluation_id != evaluation_id:
            raise HTTPException(404, "brief not found")
        if evaluation.current_brief_version_id != brief.id or brief.confirmed_at is None:
            raise ConflictError("run requires the current confirmed brief")
        active = [r for r in repo.list_runs(evaluation_id)
                  if r.state in (RunState.queued, RunState.provisioning, RunState.running, RunState.cleaning_up)]
        if active:
            raise ConflictError("a run is already active for this evaluation")
        run = repo.create_run(POCRun(evaluation_id=evaluation_id, brief_version_id=body.brief_version_id,
                                     idempotency_key=body.idempotency_key, payload_hash=payload_hash))
    emit(evaluation_id, EventType.poc_queued, run_id=run.id)
    track(evaluation_id, "poc_started")
    return ok(run, 202)


@app.get(f"{API}/runs/{{run_id}}")
def get_run(request: Request, run_id: str):
    run = repo.get_run(run_id)
    _owned_evaluation(request, run.evaluation_id)
    return ok({"run": dumps(run), "results": [dumps(r) for r in repo.list_results(run_id)],
               "artifacts": [{"id": a.id, "name": a.name, "media_type": a.media_type} for a in repo.list_artifacts(run_id)]})


@app.post(f"{API}/runs/{{run_id}}/cancel")
def cancel_run(request: Request, run_id: str):
    run = repo.get_run(run_id)
    _owned_evaluation(request, run.evaluation_id)
    cancel = _impl("poc.runner", "cancel")
    if not cancel:
        raise HTTPException(503, "POC runner not available")
    return ok(cancel(repo, run_id))


@app.get(f"{API}/evaluations/{{evaluation_id}}/events")
def list_events(request: Request, evaluation_id: str, after: int = 0):
    _owned_evaluation(request, evaluation_id)
    return ok([dumps(e) for e in repo.list_events(evaluation_id, after)])


@app.post(f"{API}/demo/source-update")
def source_update(request: Request, body: SourceUpdate):
    auth.require_operator(request)
    simulate = _impl("evidence", "simulate_update")
    if not simulate:
        return ok(_example("pending_update"), stub=True)
    return ok(simulate(repo, body.scenario_id))


@app.post(f"{API}/sources/{{version_id}}/review")
def review_source(request: Request, version_id: str, body: Review):
    auth.require_operator(request)
    review = _impl("evidence", "review")
    if not review:
        return ok(_example("source_version"), stub=True)
    if body.decision == ReviewStatus.pending:
        raise HTTPException(400, "decision must be approved or rejected")
    return ok(review(repo, version_id, body.decision))


@app.post(f"{API}/evaluations/{{evaluation_id}}/reports")
def create_report(request: Request, evaluation_id: str, body: CreateReport):
    _owned_evaluation(request, evaluation_id)
    make = _impl("reports", "create_report")
    if not make:
        return ok(_example("report"), 201, stub=True)
    report = make(repo, evaluation_id, body.brief_version_id, body.comparison_snapshot_id)
    emit(evaluation_id, EventType.report_created, report_id=report.id)
    track(evaluation_id, "report_created")
    return ok(report, 201)


@app.get(f"{API}/reports/{{report_id}}")
def get_report(request: Request, report_id: str):
    report = repo.get_report(report_id)
    _owned_evaluation(request, report.evaluation_id)
    return ok(report)


@app.get(f"{API}/evaluations/{{evaluation_id}}/agent-context")
def agent_context(request: Request, evaluation_id: str):
    _owned_evaluation(request, evaluation_id)
    ctx = _impl("agent", "agent_context")
    if not ctx:
        return ok(_example("agent_context"), stub=True)
    return ok(ctx(repo, evaluation_id))


@app.post(f"{API}/evaluations/{{evaluation_id}}/agent-evaluation")
def agent_evaluation(request: Request, evaluation_id: str, body: AgentEvaluation):
    _owned_evaluation(request, evaluation_id)
    run_agent = _impl("agent", "run_agent_evaluation")
    if not run_agent:
        return ok(_example("agent_result"), stub=True)
    result = run_agent(repo, evaluation_id, body.model)
    emit(evaluation_id, EventType.agent_evaluation_finished, decision=result.decision.value, mode=result.mode)
    return ok(result)


@app.get(f"{API}/artifacts/{{artifact_id}}")
def get_artifact(request: Request, artifact_id: str):
    try:
        artifact = repo.get_artifact(artifact_id)          # ids are opaque; never touch the filesystem
    except NotFoundError:
        raise HTTPException(404, "artifact not found")
    run = repo.get_run(artifact.run_id)
    _owned_evaluation(request, run.evaluation_id)
    return ok(artifact)


@app.post(f"{API}/demo/reset")
def demo_reset(request: Request):
    """Operator-only: clears ProofPath demo state only (never Pulse runs/ or fixtures on disk)."""
    auth.require_operator(request)
    reset = _impl("evidence", "reset")
    if not reset:
        raise HTTPException(503, "reset not available yet")
    reset(repo)
    return ok({"reset": True, "id": new_id()})
