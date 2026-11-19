"use strict";
/* The Orchestrator's view switch: Overview (the project) or Stories (one story). The choice is remembered. */
window.Brigade = window.Brigade || {};

Brigade.orchViews = (function () {
  const { $ } = Brigade.dom;
  const KEY = "brigade.orchView";
  const heard = [];
  let current = "stories";

  function show(name) {
    current = name;
    const overview = name === "overview";
    $("orchestrator").classList.toggle("on-overview", overview); // hides the run pill (css): Overview is the project, not one run
    $("orch-overview").hidden = !overview;
    document.querySelector(".orch-layout").hidden = overview;
    for (const [id, mine] of [["orch-view-overview", overview], ["orch-view-stories", !overview]]) {
      $(id).classList.toggle("selected", mine);
      $(id).setAttribute("aria-pressed", String(mine));
    }
    try {
      localStorage.setItem(KEY, name);
    } catch (error) {
      /* not remembered */
    }
    heard.forEach((listener) => listener(name));
  }

  function init() {
    let saved = null;
    try {
      saved = localStorage.getItem(KEY);
    } catch (error) {
      /* storage blocked: it starts on Stories */
    }
    $("orch-view-overview").addEventListener("click", () => show("overview"));
    $("orch-view-stories").addEventListener("click", () => show("stories"));
    show(saved === "overview" ? "overview" : "stories");
  }

  return { init, show, current: () => current, onChange: (listener) => heard.push(listener) };
})();