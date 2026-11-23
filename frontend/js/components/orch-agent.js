"use strict";
/* The agent area: Builder / Tester / Reviewer / Orchestrator tabs, the title line, the Job text. */
window.Brigade = window.Brigade || {};

Brigade.orchAgent = (function () {
  const { el, icon } = Brigade.dom;
  const TABS = [["builder", "Builder", "bolt"], ["tester", "Tester", "check"], ["reviewer", "Reviewer", "search"], ["documenter", "Documenter", "book"], ["doc-reviewer", "Doc Reviewer", "search"], ["orchestrator", "Orchestrator", "network"]];
  const FOR_BUILD = ["builder", "tester", "reviewer", "orchestrator"];
  const FOR_DOCS = ["documenter", "doc-reviewer", "orchestrator"]; // a documentation task has no Builder or Tester
  const DB_ROLE = { "doc-reviewer": "reviewer" }; // the Doc Reviewer's row in the database is a "reviewer"
  const JOB = {
    builder: "Makes the change. Cannot commit or move branches.",
    tester: "Writes and runs tests for the change.",
    reviewer: "Judges the change and decides whether it can merge.",
    documenter: "Writes the documentation. May only write the files the task lists.",
    "doc-reviewer": "Checks every claim in the documentation against what the run measured.",
    orchestrator: "Runs the steps around the agents: set-up, checks, merge.",
  };
  const NAME = { builder: "Builder", tester: "Tester", reviewer: "Reviewer", documenter: "Documenter", "doc-reviewer": "Doc Reviewer", orchestrator: "Orchestrator" };
  const money = (n) => "$" + Number(n || 0).toFixed(2);

  /** The agent row of a role: the newest, since a documentation attempt can try twice. */
  function agentOf(attempt, role) {
    const rows = attempt ? attempt.agents.filter((a) => a.role === (DB_ROLE[role] || role)) : [];
    return rows[rows.length - 1];
  }

  /** The tabs a task shows: its own agents only. `documentation`: it is a "Documentation:" task. */
  const rolesOf = (documentation) => (documentation ? FOR_DOCS : FOR_BUILD);

  /** Tabs for the attempt: one without events is disabled and says why. onPick(role). */
  function tabs(box, attempt, current, onPick, documentation) {
    box.replaceChildren();
    for (const [role, label, iconName] of TABS.filter((t) => rolesOf(documentation).includes(t[0]))) {
      const has = attempt && attempt.sources.includes(role);
      const tab = el("button", "orch-tab" + (role === current ? " selected" : ""));
      tab.append(icon(iconName), label);
      tab.type = "button";
      tab.disabled = !has;
      if (!has) tab.title = role === "tester" ? "Skipped or not reached yet." : "Nothing written yet.";
      tab.addEventListener("click", () => onPick(role));
      box.append(tab);
    }
  }

  const STATUS = { done: ["Succeeded", "ok"], error: ["Failed", "bad"], running: ["Running", "busy"] };

  /** Title line: name, status chip and the usage from the agent row. Missing values are left out. */
  function usage(box, attempt, role) {
    box.replaceChildren(el("h3", "orch-agent-name", NAME[role]));
    const agent = agentOf(attempt, role);
    if (!agent) {
      box.append(el("span", "muted small", role === "orchestrator" ? "The loop's own steps." : "Not started."));
      return;
    }
    const [text, kind] = STATUS[agent.status] || [agent.status || "", "idle"];
    if (text) box.append(el("span", "orch-chip orch-" + kind, text));
    const bits = [agent.turns != null && agent.turns + " turns", agent.model, agent.effort && agent.effort + " effort", agent.seconds != null && agent.seconds + " s", money(agent.cost)].filter(Boolean);
    box.append(el("span", "small", bits.join(" \u00B7 ")));
  }

  return { tabs, usage, agentOf, rolesOf, JOB };
})();