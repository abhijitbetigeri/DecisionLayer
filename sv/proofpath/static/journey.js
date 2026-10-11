/* Journey state is derived from the same ownership-checked workspace as the findings. */
(function () {
  "use strict";
  window.renderDecisionJourney = function (ws) {
    var bar = document.getElementById("buyer-journey");
    if (!bar) return;
    var product = ((ws.comparison || {}).products || []).find(function (p) { return p.product_id === "flowbridge"; });
    var current = !ws.stale && !!ws.brief.confirmed_at;
    var recovery = product && product.findings.find(function (f) { return f.requirement_key === "recovery_demonstrated"; });
    var proven = current && recovery && recovery.status === "met" && recovery.basis === "demonstrated";
    var ready = current && product && product.decision === "fit";
    var base = "/evaluations/" + encodeURIComponent(ws.evaluation.id);
    var active = !current ? 0 : !proven ? 1 : 2;
    bar.hidden = false;
    bar.querySelectorAll("[data-journey-step]").forEach(function (node, i) {
      node.href = base + ["#p-brief", "#p-poc", "#p-matrix"][i];
      node.setAttribute("aria-current", i === active ? "step" : "false");
      node.dataset.complete = String(i === 0 ? current : i === 1 ? !!proven : !!ready);
    });
    var summary = document.getElementById("journey-summary");
    var parts = [];
    if (!current) parts.push("Current requirements need confirmation. Previous evidence does not establish current fit.");
    else if (product) product.findings.forEach(function (f) {
      var req = ws.brief.requirements.find(function (r) { return r.id === f.requirement_id; });
      if (f.requirement_key === "recovery_demonstrated") parts.push(proven ? "Recovery demonstrated on mock systems." : "Recovery still needs a passing test.");
      else if (f.requirement_key === "us_hosting" || f.requirement_key === "eu_hosting") parts.push(f.status === "met" ? (f.requirement_key === "eu_hosting" ? "EU" : "US") + " hosting documented." : f.reason);
      else if (f.requirement_key === "sso") parts.push(f.status === "met" ? "SSO documented." : "SSO unverified" + (req && req.hard ? "; required for fit." : " but optional."));
      else if (req && req.hard && f.status !== "met") parts.push(f.reason);
    });
    summary.textContent = parts.join(" ") || "Confirm requirements to evaluate the evidence.";
    var next = document.getElementById("journey-next");
    next.textContent = !current ? "Confirm requirements" : ready ? "Create report" : proven || (product && product.decision === "not_fit") ? "Review gaps" : "Run proof of concept";
    next.href = base + (!current ? "#p-brief" : ready ? "#p-report" : proven || (product && product.decision === "not_fit") ? "#p-matrix" : "#p-poc");
  };
  var root = document.getElementById("ws");
  if (root) {
    function refresh() {
      if (document.hidden) return;
      fetch("/api/v1/evaluations/" + encodeURIComponent(root.dataset.evaluationId) + "/workspace", {credentials:"same-origin", signal:AbortSignal.timeout(10000)})
        .then(function (r) { if (!r.ok) throw Error(r.status); return r.json(); })
        .then(function (body) { window.renderDecisionJourney(body.data); })
        .catch(function () { document.getElementById("journey-summary").textContent = "Could not refresh progress. Check the current requirements and evidence below."; });
    }
    refresh(); setInterval(refresh, 4000);
  }
})();
