/* Decision insights: server-owned findings, plain text rendering, no generated HTML. */
(function () {
  "use strict";
  const root = document.getElementById("ws");
  if (!root) return;
  const timeline = document.getElementById("decision-timeline");
  const next = document.getElementById("decision-next-steps");
  const status = document.getElementById("insight-status");
  let fingerprint = "", stopped = false;
  function element(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function describe(value) {
    if (value === null || value === undefined) return "Unknown";
    if (typeof value === "object") return Object.entries(value).map(([key, val]) => `${key.replaceAll("_", " ")}: ${describe(val)}`).join(", ");
    return String(value).replaceAll("_", " ");
  }
  function render(data) {
    timeline.replaceChildren(); next.replaceChildren();
    const rows = data.timeline || [];
    if (!rows.length) timeline.append(element("li", "Confirm your requirements to start an evidence-backed decision history.", "small muted"));
    for (const row of rows.slice(-12).reverse()) {
      const item = element("li", undefined, "decision-entry");
      item.append(element("strong", row.title), element("p", row.summary, "small"));
      for (const change of row.changes || []) {
        item.append(element("p", `${change.product_name || change.product_id}: ${(change.requirement_key || change.field || "Decision").replaceAll("_", " ")} · ${describe(change.before)} → ${describe(change.after)}`, "small insight-change"));
      }
      const details = element("details"); details.append(element("summary", "Evidence references", "small"));
      const references = [...(row.source_version_ids || []), ...(row.run_ids || [])];
      details.append(element("p", references.length ? references.join(" · ") : "Requirement confirmation; no new execution evidence.", "small mono"));
      item.append(details);
      if (row.created_at) item.append(element("time", new Date(row.created_at).toLocaleString(), "small muted"));
      timeline.append(item);
    }
    const steps = data.next_steps || [];
    if (!steps.length) next.append(element("p", "No unresolved actions for the current evaluation. Review the evidence and create a report.", "small"));
    for (const step of steps) {
      const card = element("div", undefined, "next-step");
      card.append(element("strong", step.title), element("p", `Owner: ${step.owner || "Buyer"}`, "small muted"), element("p", step.reason || "", "small"));
      const request = element("textarea"); request.readOnly = true; request.value = step.request_text || "";
      request.setAttribute("aria-label", `${step.title}: copyable request`); request.rows = 3;
      const copy = element("button", "Copy request", "btn btn-ghost btn-sm"); copy.type = "button";
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(request.value); status.textContent = "Request copied. Nothing has been sent."; }
        catch (_) { request.focus(); request.select(); status.textContent = "Select and copy the request text."; }
      });
      card.append(request, copy);
      if (step.action === "run_poc") {
        const run = element("button", "Go to proof of concept", "btn btn-secondary btn-sm"); run.type = "button";
        run.addEventListener("click", () => document.getElementById("p-poc").scrollIntoView({block: "start"})); card.append(run);
      }
      next.append(card);
    }
    status.textContent = data.stale ? "Requirements or evidence need review. Historical results are preserved." : "Derived from stored requirements, evidence, and test results.";
  }
  async function refresh() {
    if (stopped) return;
    try {
      const response = await fetch(`/api/v1/evaluations/${encodeURIComponent(root.dataset.evaluationId)}/insights`, {signal: AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.json(), key = JSON.stringify(body.data);
      if (key !== fingerprint) { render(body.data); fingerprint = key; }
    } catch (_) { status.textContent = "Decision insights could not refresh. Retrying shortly."; }
    if (!stopped) setTimeout(refresh, 4000);
  }
  window.addEventListener("pagehide", () => { stopped = true; });
  refresh();
})();
