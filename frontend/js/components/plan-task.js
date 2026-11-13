"use strict";
/* One task of a plan (T1, T2...) and the label/value row the plan screen is built from. */
window.Brigade = window.Brigade || {};

Brigade.planTask = (function () {
  const { el, icon } = Brigade.dom;

  /** A label and its value. `content` is a string, a node, or a list of them (one line each). */
  function row(label, content) {
    const line = el("div", "pl-prow");
    const value = el("div", "pl-pvalue");
    for (const part of [].concat(content)) {
      value.append(typeof part === "string" ? el("div", "", part) : part);
    }
    line.append(el("span", "pl-plabel", label + ":"), value);
    return line;
  }

  /** File names as badges, the way the Publisher shows attached documents. */
  function badges(paths) {
    const box = el("div", "chips");
    for (const path of paths) {
      const chip = el("span", "file-chip");
      chip.append(icon("file"), path);
      box.append(chip);
    }
    return box;
  }

  function needs(task, ctx) {
    if (!task.depends_on.length) return "nothing";
    return task.depends_on.map((id) => {
      const other = ctx.byId[id];
      const reason = (task.dependency_reasons || {})[id] || "";
      const line = el("div", "", id + " (" + other.jira_key + "): " + reason + " ");
      if (ctx.newLinks.has(task.jira_key + "|" + other.jira_key)) {
        line.append(el("span", "pl-new", ctx.approved ? "added to Jira" : "new: added to Jira on approval"));
      }
      return line;
    });
  }

  function render(task, ctx) {
    const card = el("section", "pl-task");
    const head = el("div", "pl-task-head");
    head.append(el("span", "pl-tid", task.id), el("b", "", task.jira_key + "  " + task.title));
    card.append(head, row("Needs", needs(task, ctx)));
    const parallel = task.parallel_safe ? "parallel-safe" : "one at a time";
    const size = ctx.runAs[task.id];
    card.append(row("Run as", task.complexity + ", " + parallel + (size ? " -> " + size : "")));
    const context = task.context || {};
    const optional = [
      ["Files", task.files && task.files.length ? badges(task.files) : null],
      ["Accept", task.acceptance_criteria],
      ["Outcome", task.expected_outcome],
      ["Verify", task.verification],
      ["Doc", task.doc_target ? badges([task.doc_target]) : null],
      ["Read", context.read_first && context.read_first.length ? badges(context.read_first) : null],
      ["Notes", context.notes],
    ];
    for (const [label, value] of optional) {
      if (value && (value.length || value.nodeType)) card.append(row(label, value));
    }
    return card;
  }

  return { render, row };
})();