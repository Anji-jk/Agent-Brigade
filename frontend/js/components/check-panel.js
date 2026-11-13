"use strict";
/* The readiness result of one story: a headline, one chip per group, and what to fix. */
window.Brigade = window.Brigade || {};

Brigade.checkPanel = (function () {
  const { el, icon, when } = Brigade.dom;
  const GROUPS = ["Story", "Checkout", "Project", "Tests"];

  function headline(t, ready) {
    if (!ready) return "Readiness Checks: " + t.failed + " failed (" + t.ok + "/" + t.total + ")";
    if (t.warning) {
      return "Readiness Checks: completed with " + Brigade.storyState.plural(t.warning, "warning") + " (" + t.ok + "/" + t.total + ")";
    }
    return "Readiness Checks: all checks passed (" + t.ok + "/" + t.total + ")";
  }

  function chips(t) {
    const row = el("div", "pl-groups");
    for (const name of GROUPS) {
      const g = t.groups[name];
      if (!g) continue;
      const kind = g.failed ? "bad" : g.warning ? "warn" : g.total === 0 ? "idle" : "ok";
      const chip = el("span", "pl-chip pl-" + kind);
      chip.append(el("b", "", name), g.total === 0 ? "skipped" : g.ok + "/" + g.total);
      row.append(chip);
    }
    return row;
  }

  /** What is wrong (or worth knowing) with one check, in the words the check gave. */
  function problem(item) {
    const kind = item.status === "failed" ? "bad" : item.status === "warning" ? "warn" : "idle";
    const line = el("div", "pl-problem pl-" + kind);
    line.append(icon(kind === "idle" ? "dots" : "warn"));
    const text = el("span");
    text.append(el("b", "", item.group + ": "), item.what + (item.detail ? " - " + item.detail : ""));
    line.append(text);
    return line;
  }

  function render(mem, onRun) {
    const t = Brigade.storyState.tally(mem.check);
    const kind = !mem.check.ready ? "bad" : t.warning ? "warn" : "ok";
    const box = el("div", "pl-checks box-" + kind);
    const top = el("div", "pl-checks-top");
    const title = el("div", "pl-checks-title");
    title.append(icon(kind === "ok" ? "ok" : "warn"), el("b", "", headline(t, mem.check.ready)));
    const run = el("button", "btn btn-outline btn-small", "Run Checks");
    run.type = "button";
    run.disabled = Boolean(mem.checking);
    run.addEventListener("click", onRun);
    top.append(title, el("span", "muted small", "Last run: " + when(mem.checkedAt)), run);
    box.append(top, chips(t));
    for (const item of mem.check.checks) {
      if (item.status === "failed" || item.status === "warning" || (item.status === "skipped" && item.detail)) {
        box.append(problem(item));
      }
    }
    return box;
  }

  /** A message that is not a check result: why a request failed, or why a plan did. */
  function message(text, kind) {
    const box = el("div", "pl-problem pl-" + (kind || "bad"));
    box.append(icon("warn"), el("span", "pl-pre", text));
    return box;
  }

  return { render, message };
})();
