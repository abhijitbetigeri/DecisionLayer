(function () {
  "use strict";
  var stages = [
    ["ph-list-checks", "Start with the buyer’s requirements.", "Separate mandatory needs from preferences, then confirm what the evaluation should check.", "The homepage adapts to the selected use case."],
    ["ph-flask", "Test the claim. Inspect the evidence.", "The mock POC injects a failure, retries delivery, and checks that each source record appears exactly once.", "Documentation and demonstrated behavior stay distinct."],
    ["ph-check-square", "Give the buyer a clear next step.", "A passing US operations test can establish fit. An EU evaluation still needs SSO evidence before it qualifies.", "Return to the homepage to see the updated evidence and action."]
  ];
  document.querySelectorAll("[data-stage]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-stage]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
      var s = stages[Number(button.dataset.stage)];
      document.getElementById("stage-icon").className = "ph " + s[0];
      document.getElementById("stage-title").textContent = s[1];
      document.getElementById("stage-copy").textContent = s[2];
      document.getElementById("stage-note").textContent = s[3];
    });
  });
})();
