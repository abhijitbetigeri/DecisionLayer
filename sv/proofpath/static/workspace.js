/* Evaluation Workspace by Decision Layer (WS4). Vanilla JS, polling, no build step.
 * Every API response is {schema_version, data} (optionally "stub": true). All untrusted text goes
 * through textContent; nothing from the API is injected as HTML.
 * The persona switch is presentation only: it reorders panels via CSS and never re-renders facts. */
(function () {
  "use strict";

  const root = document.getElementById("ws");
  if (!root) return;
  const EVAL_ID = root.dataset.evaluationId;
  const OPERATOR = root.dataset.operator === "true";
  const DEMO_MODE = root.dataset.demoMode || "local";
  const API = "/api/v1";
  const SCENARIO = "crm_warehouse_sync/v1";
  const TERMINAL = new Set(["closed", "failed", "cancelled"]);

  /* ------------------------------------------------------------ vocab: icon + text, never colour alone */
  const FINDING = {
    met: ["met", "ph-check-circle", "Met"],
    unmet: ["unmet", "ph-x-circle", "Unmet"],
    unknown: ["unknown", "ph-question", "Unknown"],
  };
  const EVIDENCE = {
    documented: ["documented", "ph-file-text", "Documented"],
    demonstrated: ["demonstrated", "ph-flask", "Demonstrated"],
    unknown: ["unknown", "ph-question", "Unknown"],
    contradicted: ["contradicted", "ph-warning", "Contradicted"],
  };
  const DECISION = {
    fit: ["met", "ph-check-circle", "Fit"],
    not_fit: ["unmet", "ph-x-circle", "Not a fit"],
    needs_verification: ["unknown", "ph-magnifying-glass", "Needs verification"],
  };
  const TEST = {
    pass: ["met", "ph-check-circle", "Pass"],
    fail: ["unmet", "ph-x-circle", "Fail"],
    blocked: ["unknown", "ph-prohibit", "Blocked"],
    pending: ["documented", "ph-circle-dashed", "Not run"],
  };
  const OUTCOME = {
    passed: ["met", "ph-check-circle", "Passed"],
    failed: ["unmet", "ph-x-circle", "Failed"],
    cancelled: ["unknown", "ph-stop-circle", "Cancelled"],
    timed_out: ["unmet", "ph-timer", "Timed out"],
    interrupted: ["unmet", "ph-plugs", "Interrupted"],
  };
  const RUN_STATE = {
    draft: "Draft", awaiting_approval: "Awaiting approval", queued: "Queued",
    provisioning: "Preparing mock sandbox", running: "Running", completed: "Completed, cleaning up next",
    failed: "Failed", cancelled: "Cancelled", cleaning_up: "Cleaning up mock sandbox", closed: "Finished",
  };
  const PLAN_STEPS = [
    ["insert_first", "First opportunity syncs into the mock warehouse"],
    ["transient_failure", "Injected transient failure before commit is detected"],
    ["bounded_retry", "Retry succeeds within 3 attempts with the same idempotency key"],
    ["single_record", "Exactly one destination record per source record"],
  ];
  const REQ_CATALOG = {
    eu_hosting: "EU deployment",
    us_hosting: "US deployment",
    sso: "Single sign-on (SAML)",
    recovery_demonstrated: "Failed syncs recover without duplicates (demonstrated)",
    idempotent_delivery: "No duplicate records on retry (documented)",
    budget_monthly_usd: "Monthly budget ceiling",
  };
  const EVENT_LABEL = {
    brief_parsed: "Brief parsed", brief_confirmed: "Brief confirmed", workspace_generated: "Workspace generated",
    poc_queued: "POC queued", poc_started: "POC started", poc_attempt: "Delivery attempt",
    poc_test_result: "Assertion result", poc_finished: "POC finished", poc_cleanup_finished: "Sandbox cleaned up",
    source_change_detected: "Source change detected", source_reviewed: "Source reviewed",
    comparison_updated: "Comparison updated", report_created: "Report created",
    agent_evaluation_finished: "Buyer agent finished",
  };
  const REFRESH_ON = new Set(["brief_confirmed", "workspace_generated", "poc_finished", "poc_cleanup_finished",
    "source_change_detected", "source_reviewed", "comparison_updated", "report_created", "agent_evaluation_finished"]);

  /* ------------------------------------------------------------ state */
  const state = {
    ws: null, stub: false,
    editing: false, draft: null, pendingConfirm: null, briefError: "",
    run: null, results: [], artifacts: {}, runError: "", runPoll: null, proveKey: null, sandboxLabel: "",
    events: [], seen: new Set(), lastSeq: 0, eventsTimer: null, eventErrors: 0, eventsPaused: false,
    attempts: [], replay: DEMO_MODE === "replay",
    approved: null, reviewError: "", reportIds: [], reportError: "", agentError: "", agentBusy: false,
    refreshTimer: null,
  };

  /* ------------------------------------------------------------ helpers */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const $ = (id) => document.getElementById(id);
  /* replaceChildren() would stringify null; drop empty slots first */
  const fill = (el, ...kids) => el.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  const icon = (name) => h("i", { class: "ph " + name, "aria-hidden": "true" });
  function badge(map, key) {
    const [cls, ic, label] = map[key] || ["unknown", "ph-question", "Unknown"];
    return h("span", { class: "status status-" + cls }, icon(ic), label);
  }
  const titleCase = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : "");
  const planText = (p) => (p ? titleCase(p) : "No applicable plan");
  const money = (v) => (v === null || v === undefined ? "Quote only (price unknown)" : "$" + Math.round(v) + "/mo");
  const pct = (v) => (v === null || v === undefined ? null : Math.round(v * 100) + "%");
  const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); } catch (_) { return ""; } };
  const fmtVal = (v) => (v === null || v === undefined ? "None" : typeof v === "object" ? JSON.stringify(v, null, 2) : String(v));
  function stateBox(kind, ic, text, action) {
    return h("div", { class: "state state-" + kind, role: kind === "failed" ? "alert" : "status" }, icon(ic), h("span", {}, text), action || null);
  }
  function retryBtn(fn, label) { return h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: fn }, icon("ph-arrow-clockwise"), label || "Retry"); }
  function reqLabel(key) {
    const r = state.ws && state.ws.brief.requirements.find((q) => q.key === key);
    return r ? r.label : REQ_CATALOG[key] || key;
  }

  async function api(method, path, body, timeoutMs) {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), timeoutMs || 15000);
    let res;
    try {
      res = await fetch(API + path, {
        method, credentials: "same-origin", signal: ctl.signal,
        headers: body ? { "content-type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw Object.assign(new Error(e.name === "AbortError" ? "The server did not respond in time" : "Network error"), { status: 0 });
    } finally { clearTimeout(t); }
    let json = null;
    try { json = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) {
      const msg = (json && json.error && json.error.message) || res.statusText || "Request failed";
      throw Object.assign(new Error(msg), { status: res.status, code: json && json.error && json.error.code });
    }
    if (json && json.stub) markStub();
    return json ? json.data : null;
  }
  function markStub() { state.stub = true; $("stub-badge").hidden = false; }

  /* ------------------------------------------------------------ persona (presentation only) */
  function setPersona(p) {
    root.dataset.persona = p === "finance" ? "finance" : "technical";
    document.querySelectorAll("[data-persona-btn]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.personaBtn === root.dataset.persona)));
    try { localStorage.setItem("dl-ws-persona", root.dataset.persona); } catch (_) { /* storage unavailable */ }
  }
  document.querySelectorAll("[data-persona-btn]").forEach((b) => b.addEventListener("click", () => setPersona(b.dataset.personaBtn)));

  /* ------------------------------------------------------------ workspace load */
  async function loadWorkspace(initial) {
    try {
      const ws = await api("GET", `/evaluations/${EVAL_ID}/workspace`);
      state.ws = ws;
      if (!ws.brief.confirmed_at) state.pendingConfirm = ws.brief;          // fresh brief: must be confirmed first
      else if (state.pendingConfirm && state.pendingConfirm.id === ws.brief.id) state.pendingConfirm = null;
      if (initial) {
        let saved = null;
        try { saved = localStorage.getItem("dl-ws-persona"); } catch (_) { /* ignore */ }
        setPersona(saved || ws.brief.persona);
        state.reportIds = (ws.reports || []).slice();
      } else {
        for (const id of ws.reports || []) if (!state.reportIds.includes(id)) state.reportIds.unshift(id);
      }
      const lr = ws.latest_run;
      const newer = lr && (!state.run || (lr.id !== state.run.id && lr.created_at >= state.run.created_at));
      if (lr && (newer || (lr.id === state.run.id && !state.runPoll))) {
        state.run = lr;
        state.results = ws.latest_results || [];
      }
      if (state.run && !TERMINAL.has(state.run.state) && !state.runPoll) pollRun(state.run.id);
      $("ws-global").hidden = true;
      $("panels").hidden = false;
      renderAll();
    } catch (e) {
      if (initial || !state.ws) {
        $("panels").hidden = true;
        const g = $("ws-global");
        g.hidden = false;
        g.replaceWith(Object.assign(stateBox("failed", "ph-warning-octagon",
          e.status === 404 ? "This evaluation was not found or belongs to another session." : "Could not load the workspace: " + e.message,
          e.status === 404 ? h("a", { class: "btn btn-ghost btn-sm", href: "/" }, "Start a new evaluation") : retryBtn(() => location.reload())), { id: "ws-global" }));
      }
    }
  }
  function scheduleRefresh() {
    clearTimeout(state.refreshTimer);
    state.refreshTimer = setTimeout(() => loadWorkspace(false), 400);
  }

  function renderAll() {
    renderHeader(); renderBanners();
    if (!state.editing) renderBrief();
    renderWorkflow(); renderMatrix(); renderPoc(); renderComparison(); renderFinance(); renderReports(); renderAgent();
  }

  function invalidated() { return !!(state.pendingConfirm || (state.ws && state.ws.stale)); }

  /* ------------------------------------------------------------ header + banners */
  function renderHeader() {
    const d = state.ws.flowbridge_decision;
    const el = $("hdr-decision");
    fill(el);
    if (d) { el.append(h("span", { class: "small muted" }, "FlowBridge"), badge(DECISION, d)); el.hidden = false; }
    else el.hidden = true;
    $("replay-badge").hidden = !state.replay;
  }

  function renderBanners() {
    const box = $("banners");
    fill(box);
    const ws = state.ws;
    const pu = ws.pending_update;
    if (pu) {
      const keys = new Set(pu.diff.map((d) => d.requirement_key));
      const controls = OPERATOR ? h("div", { class: "banner-actions" },
        h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: () => review(pu.source_version.id, "approved") }, icon("ph-check"), "Approve update"),
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => review(pu.source_version.id, "rejected") }, icon("ph-x"), "Reject update"))
        : h("p", { class: "small muted" }, "An operator reviews source updates before they change any conclusion.");
      box.append(h("section", { class: "banner banner-review", "aria-labelledby": "b-review" },
        h("div", { class: "banner-title" }, icon("ph-clock-countdown"), h("strong", { id: "b-review" }, "Requires review")),
        h("p", {}, `${pu.source_version.origin} has a new version. Affected requirements: ${[...keys].map(reqLabel).join(", ")}. Current values stay unchanged until the update is approved.`),
        pu.injection_flag !== null && pu.injection_flag !== undefined
          ? h("p", { class: "small muted" }, `Instruction screen on the new content: ${Math.round(pu.injection_flag * 100)}% likelihood of embedded AI instructions.`) : null,
        diffTable(pu.diff, "Proposed change"),
        state.reviewError ? stateBox("failed", "ph-warning-octagon", state.reviewError) : null,
        controls));
    } else if (state.approved) {
      box.append(h("section", { class: "banner banner-updated", "aria-labelledby": "b-upd" },
        h("div", { class: "banner-title" }, icon("ph-arrows-clockwise"), h("strong", { id: "b-upd" }, "Comparison updated")),
        h("p", {}, `${state.approved.origin} approved. Earlier reports keep the evidence they were created with.`),
        diffTable(state.approved.diff, "What changed"),
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => { state.approved = null; renderBanners(); } }, "Dismiss")));
    }
    if (state.pendingConfirm) {
      box.append(h("section", { class: "banner banner-stale" },
        h("div", { class: "banner-title" }, icon("ph-pencil-simple-line"), h("strong", {}, ws.comparison ? "Brief edited" : "Confirm your requirements")),
        h("p", {}, ws.comparison ? "Current conclusions are invalidated until you confirm the edited brief."
          : "Check the requirements below, then confirm. Evidence is evaluated only against a confirmed brief."),
        h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: confirmBrief }, icon("ph-check"), ws.comparison ? "Confirm to re-evaluate" : "Confirm requirements")));
    } else if (ws.stale && !pu) {
      box.append(h("section", { class: "banner banner-stale" },
        h("div", { class: "banner-title" }, icon("ph-hourglass"), h("strong", {}, "Stale")),
        h("p", {}, "These conclusions predate the latest brief or evidence. Confirm the brief to re-evaluate.")));
    }
    if (OPERATOR) {
      box.append(h("div", { class: "operator-bar" }, h("span", { class: "small muted" }, icon("ph-shield-check"), " Operator controls"),
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: simulateUpdate }, icon("ph-file-arrow-up"), "Simulate RelayWorks v2 source update")));
    }
  }

  function diffTable(diff, caption) {
    return h("div", { class: "table-wrap" }, h("table", { class: "diff" },
      h("caption", {}, caption),
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Requirement"), h("th", { scope: "col" }, "Before"), h("th", { scope: "col" }, "After"))),
      h("tbody", {}, (diff || []).map((d) => h("tr", {},
        h("th", { scope: "row" }, reqLabel(d.requirement_key)),
        h("td", { "data-label": "Before" }, h("del", {}, fmtVal(d.before))),
        h("td", { "data-label": "After" }, h("ins", {}, fmtVal(d.after))))))));
  }

  async function review(versionId, decision) {
    state.reviewError = "";
    const pu = state.ws.pending_update;
    try {
      const sv = await api("POST", `/sources/${versionId}/review`, { decision });
      if (decision === "approved") state.approved = { origin: (sv && sv.origin) || pu.source_version.origin, diff: pu ? pu.diff : [] };
      await loadWorkspace(false);
    } catch (e) { state.reviewError = "Review failed: " + e.message; renderBanners(); }
  }
  async function simulateUpdate() {
    try { await api("POST", "/demo/source-update", { scenario_id: "relayworks_v2" }); await loadWorkspace(false); }
    catch (e) { state.reviewError = "Source update failed: " + e.message; renderBanners(); }
  }

  /* ------------------------------------------------------------ 1. brief */
  function renderBrief() {
    const b = state.pendingConfirm || state.ws.brief;
    const body = $("brief-body"), actions = $("brief-actions");
    fill(actions, h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: startEdit }, icon("ph-pencil-simple"), "Edit requirements"));
    const confirmed = b.confirmed_at && !state.pendingConfirm;
    fill(body,
      h("p", { class: "brief-goal" }, b.goal),
      h("p", { class: "small muted" }, `Version ${b.version}. `, confirmed ? "Confirmed." : "Not confirmed yet.",
        ` Parsed by ${b.parsed_by === "preset" ? "preset" : b.parsed_by === "manual" ? "manual entry" : b.parsed_by}.`),
      h("ul", { class: "chips", "aria-label": "Systems" }, b.systems.map((s) => h("li", { class: "chip" }, s))),
      h("ul", { class: "req-list" }, b.requirements.map((q) => h("li", {},
        h("span", { class: "tag " + (q.hard ? "tag-hard" : "") }, q.hard ? "Hard" : `Preference, weight ${q.weight}`),
        h("span", {}, q.label, q.expected !== null && q.expected !== undefined ? ` (${q.key === "budget_monthly_usd" ? "$" + q.expected + "/mo" : q.expected})` : "")))),
      b.dropped_terms && b.dropped_terms.length ? h("p", { class: "small notice" }, icon("ph-info"), ` Not recognized, add manually: ${b.dropped_terms.join(", ")}`) : null,
      state.briefError ? stateBox("failed", "ph-warning-octagon", state.briefError) : null);
  }

  function startEdit() {
    const b = state.pendingConfirm || state.ws.brief;
    state.editing = true;
    state.draft = JSON.parse(JSON.stringify(b));
    renderBriefEditor();
  }
  function renderBriefEditor() {
    const d = state.draft;
    const body = $("brief-body");
    fill($("brief-actions"));
    const rows = d.requirements.map((q, i) => h("li", { class: "req-edit" },
      h("span", { class: "req-edit-label" }, q.label),
      h("label", { class: "field-inline" }, h("span", { class: "sr-only" }, "Type for " + q.label),
        h("select", { onchange: (e) => { q.hard = e.target.value === "hard"; renderBriefEditor(); } },
          h("option", { value: "hard", selected: q.hard }, "Hard requirement"),
          h("option", { value: "pref", selected: !q.hard }, "Preference"))),
      q.hard ? null : h("label", { class: "field-inline" }, h("span", {}, "Weight"),
        h("input", { type: "number", min: "0", max: "5", step: "0.5", value: String(q.weight), oninput: (e) => { q.weight = Number(e.target.value) || 0; } })),
      q.key === "budget_monthly_usd" ? h("label", { class: "field-inline" }, h("span", {}, "Max $/mo"),
        h("input", { type: "number", min: "0", step: "50", value: q.expected === null ? "" : String(q.expected), oninput: (e) => { q.expected = e.target.value === "" ? null : Number(e.target.value); } })) : null,
      h("button", { type: "button", class: "btn btn-ghost btn-icon", "aria-label": "Remove " + q.label, onclick: () => { d.requirements.splice(i, 1); renderBriefEditor(); } }, icon("ph-trash"))));
    const missing = Object.keys(REQ_CATALOG).filter((k) => !d.requirements.some((q) => q.key === k));
    const adder = missing.length ? h("label", { class: "field-inline" }, h("span", {}, "Add"),
      h("select", { onchange: (e) => { if (!e.target.value) return; const k = e.target.value;
        d.requirements.push({ key: k, label: REQ_CATALOG[k], hard: true, weight: 0, expected: k === "budget_monthly_usd" ? 900 : null, acceptance_criteria: "" }); renderBriefEditor(); } },
        h("option", { value: "" }, "Choose a requirement"), missing.map((k) => h("option", { value: k }, REQ_CATALOG[k])))) : null;
    fill(body,
      h("p", { class: "brief-goal" }, d.goal),
      h("ul", { class: "req-list" }, rows), adder,
      h("div", { class: "row-actions" },
        h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: saveBrief }, icon("ph-floppy-disk"), "Save edits"),
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => { state.editing = false; renderBrief(); } }, "Discard")),
      state.briefError ? stateBox("failed", "ph-warning-octagon", state.briefError) : null);
  }
  async function saveBrief() {
    const d = state.draft;
    state.briefError = "";
    try {
      const nb = await api("PUT", `/evaluations/${EVAL_ID}/brief`, {
        expected_version: (state.pendingConfirm || state.ws.brief).version, goal: d.goal, systems: d.systems,
        persona: state.ws.brief.persona, requirements: d.requirements,
      });
      state.pendingConfirm = Object.assign({}, nb, state.stub ? { requirements: d.requirements, confirmed_at: null } : {});
      state.editing = false;
      renderAll();
    } catch (e) {
      state.briefError = e.status === 409 ? "The brief changed elsewhere. Reload to see the latest version." : "Could not save: " + e.message;
      renderBriefEditor();
    }
  }
  async function confirmBrief() {
    const b = state.pendingConfirm;
    if (!b) return;
    try {
      await api("POST", `/evaluations/${EVAL_ID}/confirm`, { brief_version_id: b.id });
      state.pendingConfirm = null; state.briefError = "";
      await loadWorkspace(false);
    } catch (e) { state.briefError = "Could not confirm: " + e.message; renderAll(); }
  }

  /* ------------------------------------------------------------ 2. workflow diagram (inline SVG from data) */
  const SVGNS = "http://www.w3.org/2000/svg";
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    kids.forEach((k) => el.append(k instanceof Node ? k : document.createTextNode(String(k))));
    return el;
  }
  function renderWorkflow() {
    const sys = state.ws.brief.systems || [];
    const src = sys[0] || "CRM source", dst = sys[1] || "Warehouse destination";
    const run = state.run;
    const runLine = run ? (run.outcome ? `Last POC: ${(OUTCOME[run.outcome] || [, , run.outcome])[2]}` : `POC: ${RUN_STATE[run.state] || run.state}`) : "No POC run yet";
    const nodes = [
      { t: "Mock CRM", sub: "Stand-in for", sub2: src, cls: "wf-ext" },
      { t: "FlowBridge sync", sub: runLine, sub2: "Fictional vendor", cls: "wf-core" },
      { t: "Mock warehouse", sub: "Stand-in for", sub2: dst, cls: "wf-ext" },
    ];
    const clip = (t) => (t.length > 26 ? t.slice(0, 25) + "..." : t);
    function build(vertical) {
      const W = vertical ? 300 : 600, H = vertical ? 350 : 120, bw = vertical ? 240 : 172, bh = 90;
      const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "wf-svg " + (vertical ? "wf-v" : "wf-h"), role: "img",
        "aria-label": `Workflow: ${nodes.map((n) => n.t + " (" + n.sub + " " + n.sub2 + ")").join(", then ")}` });
      svg.append(s("defs", {}, s("marker", { id: "wf-arrow" + (vertical ? "v" : "h"), viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse" },
        s("path", { d: "M0,0 L10,5 L0,10 z", class: "wf-arrowhead" }))));
      nodes.forEach((n, i) => {
        const x = vertical ? (W - bw) / 2 : 10 + i * ((W - 20 - bw) / 2), y = vertical ? 10 + i * ((H - 20 - bh) / 2) : (H - bh) / 2;
        const g = s("g", { class: "wf-node " + n.cls });
        g.append(s("rect", { x, y, width: bw, height: bh, rx: 10 }),
          s("text", { x: x + bw / 2, y: y + 30, "text-anchor": "middle", class: "wf-title" }, n.t),
          s("text", { x: x + bw / 2, y: y + 52, "text-anchor": "middle", class: "wf-sub" }, clip(n.sub)),
          s("text", { x: x + bw / 2, y: y + 70, "text-anchor": "middle", class: "wf-sub" }, clip(n.sub2)));
        svg.append(g);
        if (i < nodes.length - 1) {
          const line = vertical
            ? { x1: W / 2, y1: y + bh + 2, x2: W / 2, y2: y + (H - 20 - bh) / 2 - 4 }
            : { x1: x + bw + 4, y1: H / 2, x2: x + (W - 20 - bw) / 2 - 6, y2: H / 2 };
          svg.append(s("line", Object.assign({ class: "wf-edge", "marker-end": `url(#wf-arrow${vertical ? "v" : "h"})` }, line)));
        }
      });
      return svg;
    }
    fill($("workflow-body"), build(false), build(true),
      h("p", { class: "small muted" }, "Mock CRM and warehouse are local stand-ins. No real Salesforce or Snowflake is contacted."));
  }

  /* ------------------------------------------------------------ 3. requirement matrix */
  function product(id) { const c = state.ws.comparison; return c ? c.products.find((p) => p.product_id === id) : null; }
  function findResult(id) { return state.results.find((r) => r.id === id) || ((state.ws && state.ws.latest_results) || []).find((r) => r.id === id); }
  function citeBtn(id) {
    const tr = findResult(id);
    const isTest = !!tr || id.startsWith("tr-");
    const label = tr ? "Test: " + tr.test_key.replace(/_/g, " ") : id;
    return h("button", { type: "button", class: "cite", title: id, onclick: () => openCitation(id) }, icon(isTest ? "ph-flask" : "ph-file-text"), label);
  }
  function citationLinks(f) {
    const ids = [...(f.claim_ids || []), ...(f.test_result_ids || [])];
    if (!ids.length) return h("span", { class: "muted small" }, "No citation");
    return h("span", { class: "cites" }, ids.map(citeBtn));
  }
  function renderMatrix() {
    const body = $("matrix-body");
    const fb = product("flowbridge");
    $("matrix-sub").textContent = "FlowBridge against your confirmed requirements";
    if (!state.ws.comparison) { fill(body, stateBox("empty", "ph-list-checks", "No findings yet. Confirm the brief to evaluate the evidence.")); return; }
    if (!fb) { fill(body, stateBox("empty", "ph-list-checks", "No FlowBridge findings in this comparison.")); return; }
    const rows = state.ws.brief.requirements.map((q) => {
      const f = fb.findings.find((x) => x.requirement_key === q.key);
      return h("tr", {},
        h("th", { scope: "row" }, h("div", { class: "req-name" }, q.label),
          h("span", { class: "tag " + (q.hard ? "tag-hard" : "") }, q.hard ? "Hard" : "Preference"),
          f ? h("div", { class: "small muted reason" }, f.reason) : null,
          f && f.limitations ? h("div", { class: "small limit" }, icon("ph-warning-circle"), " ", f.limitations) : null),
        h("td", { "data-label": "Status" }, f ? badge(FINDING, f.status) : h("span", { class: "muted small" }, "Not evaluated")),
        h("td", { "data-label": "Evidence" }, f ? badge(EVIDENCE, f.basis) : null),
        h("td", { "data-label": "Plan" }, f ? planText(f.applicable_plan) : null),
        h("td", { "data-label": "Citations" }, f ? citationLinks(f) : null));
    });
    fill(body,
      invalidated() ? h("p", { class: "invalid-note" }, icon("ph-hourglass"), " Invalidated: these conclusions predate your latest brief or evidence.") : null,
      h("div", { class: "table-wrap" }, h("table", { class: "matrix stack" + (invalidated() ? " is-invalid" : "") },
        h("thead", {}, h("tr", {}, ["Requirement", "Status", "Evidence", "Plan", "Citations"].map((t) => h("th", { scope: "col" }, t)))),
        h("tbody", {}, rows))));
  }

  /* ------------------------------------------------------------ citations side panel */
  function openDrawer(title, content) {
    $("drawer-title").textContent = title;
    fill($("drawer-body"), content);
    $("drawer").hidden = false; $("drawer-scrim").hidden = false;
    document.body.classList.add("drawer-open");
    $("drawer-close").focus();
  }
  function closeDrawer() { $("drawer").hidden = true; $("drawer-scrim").hidden = true; document.body.classList.remove("drawer-open"); }
  $("drawer-close").addEventListener("click", closeDrawer);
  $("drawer-scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("drawer").hidden) closeDrawer(); });

  function openCitation(id) {
    const claim = (state.ws.claims || []).find((c) => c.id === id);
    if (claim) {
      const src = (state.ws.sources || []).find((x) => x.id === claim.source_version_id);
      openDrawer(src ? src.origin : "Source", h("div", {},
        h("dl", { class: "kv" },
          h("dt", {}, "Claim"), h("dd", { class: "mono" }, claim.id),
          h("dt", {}, "Requirement"), h("dd", {}, reqLabel(claim.requirement_key)),
          h("dt", {}, "Evidence"), h("dd", {}, badge(EVIDENCE, claim.evidence_status)),
          h("dt", {}, "Value"), h("dd", { class: "mono" }, fmtVal(claim.value)),
          h("dt", {}, "Plan"), h("dd", {}, planText(claim.plan)),
          h("dt", {}, "Review"), h("dd", {}, titleCase(claim.review_status))),
        src ? h("div", {},
          h("h3", { class: "h3" }, "Source document"),
          src.fictional ? h("p", { class: "small notice" }, icon("ph-info"), " Fictional fixture document") : null,
          h("blockquote", { class: "source-doc" }, src.content),
          h("dl", { class: "kv small" },
            h("dt", {}, "Version"), h("dd", { class: "mono" }, src.id),
            h("dt", {}, "Content hash"), h("dd", { class: "mono" }, src.content_hash),
            h("dt", {}, "Retrieved"), h("dd", {}, new Date(src.retrieved_at).toLocaleString()),
            h("dt", {}, "Supersedes"), h("dd", { class: "mono" }, src.supersedes || "None")))
          : stateBox("failed", "ph-warning-octagon", "The source version for this claim is not available.")));
      return;
    }
    const tr = findResult(id);
    if (tr) { openTestResult(tr); return; }
    openDrawer("Citation " + id, stateBox("failed", "ph-warning-octagon", "This citation is not in the current workspace."));
  }
  function openTestResult(tr) {
    const label = (PLAN_STEPS.find((p) => p[0] === tr.test_key) || [, tr.test_key])[1];
    openDrawer("Test result", h("div", {},
      h("p", {}, badge(TEST, tr.status), " ", label),
      h("dl", { class: "kv" }, h("dt", {}, "Result id"), h("dd", { class: "mono" }, tr.id), h("dt", {}, "Run"), h("dd", { class: "mono" }, tr.run_id)),
      expObs(tr),
      tr.limitations ? h("p", { class: "small limit" }, icon("ph-warning-circle"), " ", tr.limitations) : null,
      (tr.artifact_ids || []).length ? h("div", {}, h("h3", { class: "h3" }, "Artifacts"), tr.artifact_ids.map((a) => artifactBtn(a))) : null));
  }
  function expObs(tr) {
    return h("div", { class: "expobs" },
      h("div", {}, h("div", { class: "small muted" }, "Expected"), h("pre", {}, fmtVal(tr.expected))),
      h("div", {}, h("div", { class: "small muted" }, "Observed"), h("pre", {}, fmtVal(tr.observed))));
  }
  function artifactBtn(id) {
    const name = state.artifacts[id] || id;
    return h("button", { type: "button", class: "cite", onclick: () => openArtifact(id) }, icon("ph-file-code"), name);
  }
  async function openArtifact(id) {
    openDrawer("Artifact " + (state.artifacts[id] || id), stateBox("loading", "ph-hourglass-medium", "Loading artifact"));
    try {
      const a = await api("GET", `/artifacts/${id}`);
      openDrawer(a.name, h("div", {}, h("p", { class: "small muted" }, `${a.media_type}, run ${a.run_id}`), h("pre", { class: "artifact" }, fmtVal(a.content))));
    } catch (e) {
      openDrawer("Artifact", stateBox("failed", "ph-warning-octagon", e.status === 404 ? "This artifact is not stored (example data or expired run)." : "Could not load artifact: " + e.message, retryBtn(() => openArtifact(id))));
    }
  }

  /* ------------------------------------------------------------ 4. POC */
  function runActive() { return state.run && !TERMINAL.has(state.run.state); }
  function renderPoc() {
    const run = state.run;
    const rs = $("run-state");
    $("btn-prove").disabled = runActive() || !!state.pendingConfirm;
    $("btn-prove").title = state.pendingConfirm ? "Confirm the edited brief first" : "";
    $("btn-cancel").hidden = !runActive();
    const kids = [];
    if (state.sandboxLabel && !/^Demo sandbox: mock CRM and warehouse stand-ins/.test(state.sandboxLabel)) kids.push(h("p", { class: "small muted" }, icon("ph-cube"), " ", state.sandboxLabel));
    if (!run) kids.push(stateBox("empty", "ph-play-circle", "No POC run yet. Prove it runs the four assertions below against local mocks."));
    else if (runActive()) kids.push(stateBox("loading", "ph-hourglass-medium", `${RUN_STATE[run.state] || run.state}. Attempts so far: ${run.attempts}.`));
    else if (run.state === "cancelled" || run.outcome === "cancelled") kids.push(stateBox("cancelled", "ph-stop-circle", "Run cancelled. Assertions that did not finish are shown as blocked, never as passed."));
    else if (run.state === "failed" || (run.outcome && run.outcome !== "passed")) kids.push(stateBox("failed", "ph-warning-octagon", `Run ${(OUTCOME[run.outcome] || [, , "failed"])[2].toLowerCase()}${run.error ? ": " + run.error : "."}`));
    else kids.push(h("div", { class: "run-summary" }, badge(OUTCOME, run.outcome || "passed"), h("span", { class: "small muted" }, ` Run ${run.id.slice(0, 8)}, ${run.attempts} delivery attempts`)));
    if (state.runError) kids.push(stateBox("failed", "ph-warning-octagon", state.runError, run && !runActive() ? null : retryBtn(() => { state.runError = ""; pollRun(run.id); })));
    fill(rs, ...kids);

    fill($("assertions"), ...PLAN_STEPS.map(([key, text]) => {
      const tr = state.results.find((r) => r.test_key === key);
      return h("li", { class: "assertion" },
        h("div", { class: "assertion-head" }, badge(TEST, tr ? tr.status : "pending"), h("span", {}, text)),
        tr ? h("details", {}, h("summary", {}, "Expected and observed"), expObs(tr),
          tr.limitations ? h("p", { class: "small limit" }, icon("ph-warning-circle"), " ", tr.limitations) : null,
          (tr.artifact_ids || []).length ? h("div", { class: "cites" }, tr.artifact_ids.map(artifactBtn)) : null) : null);
    }));
    renderEvents();
  }

  async function prove() {
    if (runActive()) return;
    state.runError = "";
    state.proveKey = state.proveKey || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
    $("btn-prove").disabled = true;
    try {
      const run = await api("POST", `/evaluations/${EVAL_ID}/runs`, { brief_version_id: state.ws.brief.id, scenario_version: SCENARIO, idempotency_key: state.proveKey });
      state.proveKey = null;
      state.run = run; state.results = []; state.attempts = [];
      renderPoc(); renderWorkflow();
      pollRun(run.id);
      startEvents(true);
    } catch (e) {
      state.runError = e.status === 409 ? "A run is already active for this evaluation." : "Could not start the run: " + e.message;
      if (e.status !== 0) state.proveKey = null;     // keep the key only for a network retry of the same click
      renderPoc();
    }
  }
  async function cancelRun() {
    if (!state.run) return;
    $("btn-cancel").disabled = true;
    try { const r = await api("POST", `/runs/${state.run.id}/cancel`); if (r && r.state) state.run = r; }
    catch (e) { state.runError = "Could not cancel: " + e.message; }
    $("btn-cancel").disabled = false;
    renderPoc();
  }
  $("btn-prove").addEventListener("click", prove);
  $("btn-cancel").addEventListener("click", cancelRun);

  function pollRun(runId) {
    clearTimeout(state.runPoll);
    let delay = 600, lastSig = "", lastChange = Date.now();
    const STALL_MS = 90000;
    async function tick() {
      try {
        const d = await api("GET", `/runs/${runId}`);
        state.run = d.run; state.results = d.results || [];
        (d.artifacts || []).forEach((a) => { state.artifacts[a.id] = a.name; });
        const sig = d.run.state + "|" + d.run.attempts + "|" + state.results.length;
        if (sig !== lastSig) { lastSig = sig; lastChange = Date.now(); delay = 600; } else delay = Math.min(delay * 1.5, 4000);
        renderPoc(); renderWorkflow();
        if (TERMINAL.has(d.run.state)) { state.runPoll = null; scheduleRefresh(); return; }
        if (Date.now() - lastChange > STALL_MS) { state.runPoll = null; state.runError = "No progress from the POC runner for 90 seconds. Polling stopped."; renderPoc(); return; }
      } catch (e) {
        if (e.status === 404) { state.runPoll = null; state.runError = "This run no longer exists."; renderPoc(); return; }
        delay = Math.min(delay * 2, 10000);
        if (Date.now() - lastChange > STALL_MS) { state.runPoll = null; state.runError = "Lost contact with the server: " + e.message; renderPoc(); return; }
      }
      state.runPoll = setTimeout(tick, delay);
    }
    state.runPoll = setTimeout(tick, 0);
  }

  /* ------------------------------------------------------------ live events */
  function eventSummary(ev) {
    const p = ev.payload || {};
    switch (ev.type) {
      case "poc_attempt":
        return `${p.record || "record"} attempt ${p.attempt ?? "?"}: ${p.ok ? "delivered" : "failed"}${p.ok ? "" : p.will_retry ? ", will retry" : ", no retry"}`;
      case "poc_test_result": return `${(PLAN_STEPS.find((s) => s[0] === p.test_key) || [, p.test_key || ""])[1]}: ${p.status || ""}`;
      case "poc_started": return p.sandbox_label || "";
      case "poc_finished": return p.outcome ? (OUTCOME[p.outcome] || [, , p.outcome])[2] : "";
      case "source_change_detected": return p.origin || p.source_version_id || "";
      case "source_reviewed": return p.decision ? titleCase(p.decision) : "";
      case "agent_evaluation_finished": return [p.mode === "rule_based" ? "Rule-based evaluation" : "AI agent", p.decision && (DECISION[p.decision] || [, , p.decision])[2]].filter(Boolean).join(", ");
      default: return "";
    }
  }
  function ingest(list) {
    let refresh = false, added = 0;
    for (const ev of list) {
      if (state.seen.has(ev.id)) continue;
      state.seen.add(ev.id);
      state.lastSeq = Math.max(state.lastSeq, ev.sequence || 0);
      state.events.push(ev); added++;
      if (ev.channel === "replay") state.replay = true;
      if (ev.type === "poc_started" && ev.payload && ev.payload.sandbox_label) state.sandboxLabel = ev.payload.sandbox_label;
      if (ev.type === "source_reviewed" && ev.payload && ev.payload.decision === "approved" && ev.payload.diff) state.approved = { origin: ev.payload.origin || "Source", diff: ev.payload.diff };
      if (REFRESH_ON.has(ev.type)) refresh = true;
      if (ev.run_id && state.run && ev.run_id === state.run.id && !state.runPoll && !TERMINAL.has(state.run.state)) pollRun(ev.run_id);
    }
    if (added) { renderEvents(); renderHeader(); if (state.sandboxLabel) renderPoc(); }
    return refresh;
  }
  function renderEvents() {
    const list = $("events");
    const evs = state.events.slice(-60).reverse();
    fill(list, ...evs.map((ev) => {
      const fail = ev.type === "poc_attempt" && ev.payload && ev.payload.ok === false;
      return h("li", { class: "event" + (fail ? " event-fail" : "") },
        h("span", { class: "event-time mono" }, fmtTime(ev.created_at)),
        h("span", { class: "event-type" }, fail ? icon("ph-arrow-counter-clockwise") : null, EVENT_LABEL[ev.type] || ev.type),
        ev.channel && ev.channel !== "live" ? h("span", { class: "tag" }, ev.channel === "replay" ? "Recorded replay" : titleCase(ev.channel)) : null,
        h("span", { class: "event-sum small muted" }, eventSummary(ev)));
    }));
    const st = $("events-state");
    fill(st);
    if (state.eventsPaused) st.append(stateBox("failed", "ph-wifi-slash", "Live updates paused after repeated errors.", retryBtn(() => { state.eventsPaused = false; state.eventErrors = 0; startEvents(true); })));
    else if (!state.events.length) st.append(stateBox("empty", "ph-broadcast", "No events yet."));
  }
  function startEvents(fast) {
    clearTimeout(state.eventsTimer);
    async function tick() {
      try {
        const list = await api("GET", `/evaluations/${EVAL_ID}/events?after=${state.lastSeq}`);
        state.eventErrors = 0;
        if (ingest(list || [])) scheduleRefresh();
      } catch (e) {
        state.eventErrors++;
        if (state.eventErrors >= 5) { state.eventsPaused = true; renderEvents(); return; }
      }
      const base = runActive() ? 1000 : 6000;
      const delay = state.eventErrors ? Math.min(base * 2 ** state.eventErrors, 30000) : base;
      state.eventsTimer = setTimeout(tick, document.hidden ? Math.max(delay, 15000) : delay);
    }
    state.eventsTimer = setTimeout(tick, fast ? 0 : 1000);
  }

  /* ------------------------------------------------------------ 5. comparison */
  function renderComparison() {
    const body = $("comparison-body");
    const c = state.ws.comparison;
    if (!c) { $("comparison-sub").textContent = ""; fill(body, stateBox("empty", "ph-table", "No comparison yet. Confirm the brief to compare products.")); return; }
    $("comparison-sub").textContent = `Snapshot ${c.id.slice(0, 8)}, ${c.rubric_version}. Hard requirements decide fit; preferences only affect score.`;
    const pu = state.ws.pending_update;
    const puProduct = pu ? pu.source_version.product_id : null;
    const puKeys = new Set(pu ? pu.diff.map((d) => d.requirement_key) : []);
    const hard = state.ws.brief.requirements.filter((q) => q.hard);
    const reviewTag = () => h("span", { class: "tag tag-review" }, icon("ph-clock-countdown"), "Requires review");
    const head = h("tr", {}, h("th", { scope: "col" }, "Requirement"), c.products.map((p) =>
      h("th", { scope: "col", class: p.product_id === "flowbridge" ? "col-primary" : "" }, p.product_name, p.product_id === puProduct ? h("div", {}, reviewTag()) : null)));
    const rows = hard.map((q) => h("tr", {}, h("th", { scope: "row" }, q.label),
      c.products.map((p) => {
        const f = p.findings.find((x) => x.requirement_key === q.key);
        const affected = p.product_id === puProduct && puKeys.has(q.key);
        return h("td", { class: affected ? "cell-affected" : "" }, f ? badge(FINDING, f.status) : h("span", { class: "muted small" }, "Not evaluated"),
          f ? h("div", { class: "small muted" }, (EVIDENCE[f.basis] || [, , f.basis])[2], f.applicable_plan ? `, ${planText(f.applicable_plan)}` : "") : null,
          affected ? reviewTag() : null);
      })));
    const metric = (label, fn, cls) => h("tr", { class: "metric " + (cls || "") }, h("th", { scope: "row" }, label), c.products.map((p) => h("td", {}, fn(p))));
    const nee = () => h("span", { class: "nee" }, icon("ph-question"), "Not enough evaluated evidence");
    fill(body,
      invalidated() ? h("p", { class: "invalid-note" }, icon("ph-hourglass"), " Invalidated until the edited brief is confirmed.") : null,
      h("div", { class: "table-wrap" }, h("table", { class: "compare" + (invalidated() ? " is-invalid" : "") },
        h("thead", {}, head),
        h("tbody", {}, rows,
          metric("Decision", (p) => badge(DECISION, p.decision), "metric-first"),
          metric("Cheapest qualifying plan", (p) => p.cheapest_qualifying_plan ? `${planText(p.cheapest_qualifying_plan)}, ${money(p.monthly_price_usd)}` : `No qualifying plan${p.monthly_price_usd != null ? " (listed from " + money(p.monthly_price_usd) + ")" : ""}`, "fin"),
          metric("Preference score", (p) => p.evaluated_score === null || p.evaluated_score === undefined ? nee() : p.evaluated_score.toFixed(2)),
          metric("Coverage", (p) => pct(p.coverage) === null ? nee() : pct(p.coverage)),
          metric("Gaps", (p) => p.gaps && p.gaps.length ? h("ul", { class: "gaps" }, p.gaps.map((g) => h("li", {}, g))) : h("span", { class: "muted small" }, "None listed"))))));
  }

  /* ------------------------------------------------------------ finance assumptions (same facts, different emphasis) */
  function renderFinance() {
    const body = $("finance-body");
    const c = state.ws.comparison;
    if (!c) { fill(body, stateBox("empty", "ph-currency-dollar", "Plan assumptions appear once a comparison exists.")); return; }
    const budget = state.ws.brief.requirements.find((q) => q.key === "budget_monthly_usd");
    const quotes = c.products.filter((p) => p.cheapest_qualifying_plan && (p.monthly_price_usd === null || p.monthly_price_usd === undefined));
    fill(body,
      h("ul", { class: "fin-list" }, c.products.map((p) => h("li", {},
        h("strong", {}, p.product_name), " ",
        p.cheapest_qualifying_plan ? (p.monthly_price_usd == null ? `needs ${planText(p.cheapest_qualifying_plan)}, quote only (price unknown)` : `needs ${planText(p.cheapest_qualifying_plan)} at ${money(p.monthly_price_usd)}`) : "has no plan that meets every capability requirement"))),
      h("p", { class: "small" }, budget ? `Budget ceiling in the brief: $${budget.expected}/mo.` : "No budget ceiling in the brief."),
      quotes.length ? h("p", { class: "small notice" }, icon("ph-question"), ` Quote unknowns: ${quotes.map((p) => p.product_name).join(", ")}. A quote-only plan is never treated as within budget.`)
        : h("p", { class: "small muted" }, "No quote-only plans among qualifying options."),
      h("p", { class: "small muted" }, "Implementation cost: not evaluated in this build; the fixtures contain no implementation cost evidence."));
  }

  /* ------------------------------------------------------------ 7. reports + agent */
  function renderReports() {
    const body = $("report-body");
    const c = state.ws.comparison;
    const btn = $("btn-report");
    btn.disabled = !c || !!state.pendingConfirm;
    btn.title = !c ? "Needs a comparison" : state.pendingConfirm ? "Confirm the edited brief first" : "";
    fill(body,
      h("p", { class: "small muted" }, "A report freezes the current brief version, comparison snapshot and run ids. Later evidence updates never change it."),
      state.reportIds.length ? h("ul", { class: "report-list" }, state.reportIds.map((id, i) => h("li", {},
        h("a", { href: `/reports/${encodeURIComponent(id)}` }, icon("ph-file-lock"), ` Report ${id.slice(0, 8)}`), i === 0 ? h("span", { class: "tag" }, "Latest") : null)))
        : stateBox("empty", "ph-file-dashed", "No reports yet."),
      state.reportError ? stateBox("failed", "ph-warning-octagon", state.reportError) : null);
  }
  async function createReport() {
    const c = state.ws.comparison;
    if (!c) return;
    state.reportError = "";
    $("btn-report").disabled = true;
    try {
      const r = await api("POST", `/evaluations/${EVAL_ID}/reports`, { brief_version_id: state.ws.brief.id, comparison_snapshot_id: c.id });
      if (!state.reportIds.includes(r.id)) state.reportIds.unshift(r.id);
    } catch (e) { state.reportError = "Could not create the report: " + e.message; }
    renderReports();
  }
  $("btn-report").addEventListener("click", createReport);

  function renderAgent() {
    const body = $("agent-body");
    const a = state.ws.agent_result;
    $("btn-agent").disabled = state.agentBusy || !state.ws.comparison;
    const kids = [];
    if (state.agentBusy) kids.push(stateBox("loading", "ph-hourglass-medium", "The buyer agent is reading the agent context. This usually takes under a minute."));
    else if (!a) kids.push(stateBox("empty", "ph-robot", "Not run yet. The buyer agent reads only the published agent context and must cite every claim."));
    if (a) {
      kids.push(h("div", { class: "agent-card" },
        h("div", { class: "agent-row" }, h("span", { class: "tag" }, a.mode === "rule_based" ? "Rule-based evaluation" : "AI agent"),
          a.model_id && a.mode !== "rule_based" ? h("span", { class: "mono small" }, a.model_id) : null),
        h("div", { class: "agent-row" }, h("span", { class: "small muted" }, "Decision"), badge(DECISION, a.decision),
          a.correct === true ? h("span", { class: "small" }, icon("ph-check"), " Matches the evidence rule") : a.correct === false ? h("span", { class: "small" }, icon("ph-x"), ` Differs from the evidence rule (${(DECISION[a.expected_decision] || [, , a.expected_decision])[2]})`) : null),
        h("ul", { class: "agent-reqs" }, Object.entries(a.requirement_statuses || {}).map(([k, v]) => h("li", {}, h("span", {}, reqLabel(k)), badge(FINDING, v)))),
        h("div", {}, h("div", { class: "small muted" }, "Citations"), a.citations.length ? h("span", { class: "cites" }, a.citations.map(citeBtn)) : h("span", { class: "small muted" }, "None")),
        a.rejected_citations && a.rejected_citations.length ? h("p", { class: "small limit" }, icon("ph-warning-circle"), ` Rejected citations (not found in evidence): ${a.rejected_citations.join(", ")}`) : null,
        h("p", { class: "small muted" }, `Input version ${a.input_version}, ${a.turns} turns. A model never decides pass or fail.`)));
    }
    if (state.agentError) kids.push(stateBox("failed", "ph-warning-octagon", state.agentError, retryBtn(runAgent)));
    fill(body, ...kids);
  }
  async function runAgent() {
    state.agentBusy = true; state.agentError = ""; renderAgent();
    try { const r = await api("POST", `/evaluations/${EVAL_ID}/agent-evaluation`, {}, 120000); state.ws.agent_result = r; }
    catch (e) { state.agentError = "The buyer agent did not finish: " + e.message; }
    state.agentBusy = false; renderAgent();
  }
  $("btn-agent").addEventListener("click", runAgent);

  /* ------------------------------------------------------------ boot */
  function focusAnchor() {
    if (location.hash !== "#evidence") return;
    const el = $("p-matrix");
    if (!el || $("panels").hidden) return;
    el.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    el.classList.add("is-highlight");
    setTimeout(() => el.classList.remove("is-highlight"), 2400);
  }
  window.addEventListener("hashchange", focusAnchor);
  loadWorkspace(true).then(() => { if (state.ws) { startEvents(true); requestAnimationFrame(focusAnchor); } });
})();
