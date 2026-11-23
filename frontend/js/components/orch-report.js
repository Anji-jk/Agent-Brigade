"use strict";
/* The REPORT box: what the agent did, from its stage report. Unfilled fields are not shown. */
window.Brigade = window.Brigade || {};

Brigade.orchReport = (function () {
  const { el } = Brigade.dom;
  const LABEL = {
    report: "What it did", changed: "Files changed", error: "Error", summary: "Summary", ran: "Tests run",
    coverage: "Coverage", uncovered: "Not covered", suspected_defects: "Suspected defects", notes: "Notes",
    wrote: "Test files written", outside: "Changes outside tests", weakened: "Weakened tests",
    invalid: "Invalid", no_tests: "No tests", skipped: "Skipped", outcome: "Outcome", verdict: "Verdict",
    reasons: "Reasons", criteria: "Criteria", problems: "Problems", commit: "Commit", reviewer_skipped: "Reviewer skipped",
  };
  const DOCS_LABEL = { wrote: "Files written", outside: "Written outside the task's files", ok: "Accepted" }; // the Documenter's report
  const ORDER = Object.keys(LABEL);
  const LONG = ["report", "summary", "notes"]; // the agent's own words: folded until asked for
  const empty = (v) => v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length) || v === false;

  function value(v) {
    if (Array.isArray(v)) {
      const list = el("ul", "orch-rep-list");
      for (const item of v) list.append(el("li", "", typeof item === "string" ? item : JSON.stringify(item)));
      return list;
    }
    if (v === true) return el("p", "", "yes");
    if (typeof v === "object") return el("pre", "orch-rep-pre", JSON.stringify(v, null, 2));
    const p = el("div", "orch-rep-text");
    p.append(Brigade.markdown.render(String(v)));
    return p;
  }

  const label = (data, name) => (data.stage === "docs" && DOCS_LABEL[name]) || LABEL[name];

  /** `data` is the endpoint's answer; nothing is drawn until the stage has written its report. */
  function render(box, data, job) {
    const was = box.querySelector("details");
    const open = was ? was.open : true; // keep the person's choice across refreshes
    const opened = new Set([...box.querySelectorAll("details.orch-fold-row[open]")].map((d) => d.dataset.name));
    const wrap = el("details", "orch-rep");
    wrap.open = open;
    wrap.append(el("summary", "orch-rep-head", "REPORT"));
    box.replaceChildren(wrap);
    box = wrap;
    if (job) {
      const row = el("section", "orch-rep-row");
      row.append(el("h4", "", "Job"), el("p", "", job));
      box.append(row);
    }
    if (!data || !data.exists) {
      box.append(el("p", "muted small", "This agent has not written its report yet."));
      return;
    }
    let shown = 0;
    for (const name of ORDER) {
      if (empty(data[name])) continue;
      if (LONG.includes(name)) {
        const fold = el("details", "orch-fold-row");
        fold.dataset.name = name;
        fold.open = opened.has(name);
        fold.append(el("summary", "", label(data, name)), value(data[name]));
        box.append(fold);
      } else {
        const row = el("section", "orch-rep-row");
        row.append(el("h4", "", label(data, name)), value(data[name]));
        box.append(row);
      }
      shown += 1;
    }
    if (!shown) box.append(el("p", "muted small", "The report holds nothing to show."));
  }

  return { render };
})();