/* FlowBridge homepage behaviour (WS3): hero preview from real evaluation data, evaluation submit,
   preset chips, security-evidence entry, scroll reveal. Vanilla JS, no build. */
(function () {
  "use strict";

  var cfg = window.FLOWBRIDGE || {};
  var EXAMPLE_ID = cfg.exampleId || "11111111-1111-4111-8111-111111111111";
  var API = "/api/v1";

  var STATUS = {
    met: { cls: "status-met", icon: "ph-check-circle", label: "Met" },
    unmet: { cls: "status-unmet", icon: "ph-x-circle", label: "Unmet" },
    unknown: { cls: "status-unknown", icon: "ph-question", label: "Unknown" }
  };
  var BASIS = {
    documented: { icon: "ph-file-text", label: "Documented" },
    demonstrated: { icon: "ph-flask", label: "Demonstrated" },
    contradicted: { icon: "ph-warning", label: "Contradicted" },
    unknown: { icon: "ph-question", label: "No evidence" }
  };
  var DECISION = {
    fit: { cls: "status-met", icon: "ph-check-circle", label: "Fit" },
    not_fit: { cls: "status-unmet", icon: "ph-x-circle", label: "Not a fit" },
    needs_verification: { cls: "status-unknown", icon: "ph-magnifying-glass", label: "Needs verification" }
  };
  var TEST_LABELS = {
    insert_first: "First record inserted",
    transient_failure: "Failure injected before commit",
    bounded_retry: "Retried with the same key",
    single_record: "Exactly one record written"
  };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "class") node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function icon(name, extra) { return el("i", { class: "ph " + name + (extra ? " " + extra : ""), "aria-hidden": "true" }); }
  function badge(def) { return el("span", { class: "status " + def.cls }, [icon(def.icon), document.createTextNode(def.label)]); }
  function $(sel, root) { return (root || document).querySelector(sel); }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (body) { return body && body.data ? body.data : body; });
  }

  /* ------------------------------------------------------------ hero preview */
  function loadShowcase() {
    // Preferred: a seeded showcase route (requested from the coordinator). Fallback: stub example.
    return getJSON(API + "/showcase").catch(function () {
      return getJSON(API + "/evaluations/" + EXAMPLE_ID + "/workspace");
    });
  }

  function renderPreview(ws) {
    var fig = $("#hero-preview");
    if (!fig) return;
    var cmp = ws.comparison || {};
    var product = (cmp.products || []).filter(function (p) { return p.product_id === "flowbridge"; })[0];
    if (!product || !ws.brief) throw new Error("payload missing FlowBridge findings");

    var reqs = {};
    (ws.brief.requirements || []).forEach(function (r) { reqs[r.id] = r; });
    var claims = {};
    (ws.claims || []).forEach(function (c) { claims[c.id] = c; });
    var sources = {};
    (ws.sources || []).forEach(function (s) { sources[s.id] = s; });

    $("[data-preview=goal]", fig).textContent = ws.brief.goal || "Example evaluation";
    var dec = DECISION[product.decision || ws.flowbridge_decision];
    var decSlot = $("[data-preview=decision]", fig);
    decSlot.textContent = "";
    if (dec) decSlot.appendChild(badge(dec));

    var list = $("[data-preview=matrix]", fig);
    list.textContent = "";
    var hardFindings = product.findings.filter(function (f) { var r = reqs[f.requirement_id]; return r && r.hard; });
    var rows = hardFindings.length ? hardFindings : product.findings;
    rows.slice(0, 4).forEach(function (f, i) {
      var req = reqs[f.requirement_id] || { label: f.requirement_key };
      var st = STATUS[f.status] || STATUS.unknown;
      var basis = BASIS[f.basis] || BASIS.unknown;
      var meta = el("span", { class: "matrix-meta" }, [
        el("span", null, [icon(basis.icon), document.createTextNode(basis.label)]),
        f.applicable_plan ? el("span", { text: "Plan: " + f.applicable_plan.charAt(0).toUpperCase() + f.applicable_plan.slice(1) }) : null,
        f.reason ? el("span", { text: f.reason }) : null
      ]);
      var row = el("li", { class: "matrix-row enter" + (req.hard ? " is-hard" : ""), style: "--i:" + i }, [
        el("span", { class: "matrix-label", text: req.label }), badge(st), meta
      ]);
      list.appendChild(row);
    });

    // One citation, taken from the first documented finding with a claim.
    var cited = product.findings.filter(function (f) { return f.claim_ids && f.claim_ids.length && claims[f.claim_ids[0]]; })[0];
    var citeBox = $("[data-preview=citation]", fig);
    if (cited) {
      var claim = claims[cited.claim_ids[0]];
      var src = sources[claim.source_version_id] || {};
      citeBox.textContent = "";
      citeBox.appendChild(el("div", { class: "cite-head" }, [
        icon("ph-quotes"), el("span", { text: "Citation for " + ((reqs[cited.requirement_id] || {}).label || cited.requirement_key) }),
      ]));
      citeBox.appendChild(el("blockquote", { text: "“" + (src.content || "") + "”" }));
      citeBox.appendChild(el("code", { text: (src.origin || "source") + "  |  " + claim.id }));
      citeBox.hidden = false;
    }

    // Systems for the connectors cell.
    (ws.brief.systems || []).slice(0, 2).forEach(function (s, i) {
      var slot = $("[data-preview=system-" + i + "]");
      if (slot) slot.textContent = s.replace(/\s*\(.*\)\s*$/, "");
    });

    renderRun(ws);
    fig.setAttribute("aria-busy", "false");
  }

  function renderRun(ws) {
    var box = $("[data-preview=run]");
    if (!box) return;
    var results = ws.latest_results || [];
    box.textContent = "";
    if (!results.length) {
      // No POC run on the showcase yet: show what the live test checks, clearly marked as not run.
      Object.keys(TEST_LABELS).forEach(function (k) {
        box.appendChild(el("li", { class: "run-step" }, [
          icon("ph-circle-dashed"),
          el("span", null, [el("strong", { text: TEST_LABELS[k] }), el("small", { text: "Checked when you run the live test" })])
        ]));
      });
      var n = $("[data-preview=run-note]");
      if (n) n.textContent = "Runs crm_warehouse_sync/v1 on local mock systems.";
      return;
    }
    results.slice(0, 4).forEach(function (t) {
      var pass = t.status === "pass";
      box.appendChild(el("li", { class: "run-step" }, [
        icon(pass ? "ph-check-circle" : "ph-x-circle", pass ? "pass" : ""),
        el("span", null, [
          el("strong", { text: TEST_LABELS[t.test_key] || t.test_key }),
          el("small", { text: (pass ? "Pass" : "Fail") + (typeof t.observed === "string" ? ": " + t.observed : "") })
        ])
      ]));
    });
    var run = ws.latest_run;
    var note = $("[data-preview=run-note]");
    if (run && note) note.textContent = "From the example run (" + run.scenario_version + ") on local mock systems.";
  }

  function previewFailed() {
    var fig = $("#hero-preview");
    if (!fig) return;
    $("[data-preview=goal]", fig).textContent = "Example evaluation unavailable";
    $("[data-preview=matrix]", fig).textContent = "";
    $("[data-preview=error]", fig).hidden = false;
    fig.setAttribute("aria-busy", "false");
    var box = $("[data-preview=run]");
    if (box) {
      box.textContent = "";
      box.appendChild(el("li", { class: "run-step" }, [icon("ph-circle-dashed"), el("span", { text: "Run an evaluation to see a live test." })]));
    }
  }

  loadShowcase().then(function (ws) {
    try { renderPreview(ws); } catch (e) { previewFailed(); }
  }).catch(previewFailed);

  /* ------------------------------------------------------------ evaluation form */
  var form = $("#eval-form");
  var textarea = $("#brief");
  var submit = $("#eval-submit");
  var errorBox = $("#brief-error");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip[data-preset]"));
  var presetId = "eu_technical";

  function selectChip(chip) {
    chips.forEach(function (c) { c.setAttribute("aria-checked", c === chip ? "true" : "false"); });
    presetId = chip ? chip.getAttribute("data-preset") : null;
  }
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      selectChip(chip);
      textarea.value = chip.getAttribute("data-brief");
      clearError();
    });
  });
  if (textarea) textarea.addEventListener("input", function () {
    // A hand-edited brief is no longer the preset text: drop the preset so the parser reads the text.
    var active = chips.filter(function (c) { return c.getAttribute("aria-checked") === "true"; })[0];
    if (active && textarea.value.trim() !== active.getAttribute("data-brief")) selectChip(null);
    clearError();
  });

  function showError(msg) {
    errorBox.textContent = "";
    errorBox.appendChild(icon("ph-warning-circle"));
    errorBox.appendChild(el("span", { text: msg }));
    errorBox.hidden = false;
  }
  function clearError() { if (errorBox) errorBox.hidden = true; if (textarea) textarea.removeAttribute("aria-invalid"); }
  function setLoading(on) {
    submit.disabled = on;
    submit.classList.toggle("is-loading", on);
    submit.setAttribute("aria-busy", on ? "true" : "false");
  }

  function createEvaluation(briefText, preset) {
    return fetch(API + "/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ brief_text: briefText, preset_id: preset || null })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) {
          var msg = body && body.error && body.error.message;
          throw new Error(msg || "The server answered with status " + r.status + ".");
        }
        var id = body && body.data && body.data.evaluation_id;
        if (!id) throw new Error("The server did not return an evaluation id.");
        return id;
      });
    });
  }

  if (form) form.addEventListener("submit", function (e) {
    e.preventDefault();
    clearError();
    var text = textarea.value.trim();
    if (text.length < 12 && !presetId) {
      textarea.setAttribute("aria-invalid", "true");
      showError("Describe your use case in a sentence or pick a preset.");
      textarea.focus();
      return;
    }
    setLoading(true);
    createEvaluation(text, presetId).then(function (id) {
      window.location.href = "/evaluations/" + encodeURIComponent(id);
    }).catch(function (err) {
      setLoading(false);
      showError("We could not start the evaluation. " + (err && err.message ? err.message : "") + " Please try again.");
    });
  });

  /* ------------------------------------------------------------ CTAs */
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target.closest("[data-action]") : null;
    if (!t) return;
    var action = t.getAttribute("data-action");
    if (action === "focus-brief") {
      e.preventDefault();
      var target = $("#evaluate");
      var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      setTimeout(function () { textarea.focus({ preventScroll: true }); }, reduce ? 0 : 450);
    } else if (action === "security-evidence") {
      // Opens the evidence view of a fresh EU technical evaluation (SSO starts as Unknown there).
      e.preventDefault();
      if (t.getAttribute("aria-busy") === "true") return;
      t.setAttribute("aria-busy", "true");
      createEvaluation(chips[0] ? chips[0].getAttribute("data-brief") : "", "eu_technical").then(function (id) {
        window.location.href = "/evaluations/" + encodeURIComponent(id) + "#evidence";
      }).catch(function () {
        t.removeAttribute("aria-busy");
        window.location.hash = "evaluate";
        showError("Security evidence opens inside an evaluation. Start one here.");
      });
    }
  });

  /* ------------------------------------------------------------ scroll reveal */
  var revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    revealEls.forEach(function (n) { io.observe(n); });
  } else {
    revealEls.forEach(function (n) { n.classList.add("is-in"); });
  }
})();
