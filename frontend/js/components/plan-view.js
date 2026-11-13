"use strict";
/* A saved plan (plan.json) as the Planning screen shows it: summary, tasks, what Approve does. */
window.Brigade = window.Brigade || {};

Brigade.planView = (function () {
  const { el } = Brigade.dom;
  const { row } = Brigade.planTask;
  const usd = (value) => "$" + String(Math.round(Number(value) * 100) / 100);
  const plural = (count, word) => count + " " + word + (count === 1 ? "" : "s");

  function budgetLines(plan, run) {
    const budget = plan.config.budget_usd;
    const total = run.task_limits_usd;
    const sum = total == null ? "" : "the tasks' limits add up to " + usd(total);
    if (budget == null) return ["none set" + (sum ? " (" + sum + ")" : "")];
    const used = (plan.planner && plan.planner.total_cost_usd) || 0;
    const left = budget - used;
    const lines = [
      usd(budget) + " for planning and building this story",
      "planning used " + usd(used) + ", so " + usd(left) + " is left" + (sum ? "; " + sum : ""),
    ];
    if (total != null && total > left) {
      lines.push("Warning: the task limits add up to more than what is left, so the budget may stop the build before every task has used its full limit.");
    }
    return lines;
  }

  function header(plan, run) {
    const { source, config } = plan;
    const box = el("section", "pl-summary");
    box.append(el("h3", "", "Plan for story " + source.key + " - " + plan.issue.title));
    if (source.epic) box.append(row("Epic", source.epic.key + " " + source.epic.summary));
    box.append(
      row("Run ID", config.run_id),
      row("Branch", config.branch + " (from " + config.base_ref + " at " + String(config.base_commit).slice(0, 12) + ")"),
      row("Model", config.model || "(default)"),
      row("Budget", budgetLines(plan, run)),
    );
    if (config.replan) {
      box.append(row("Re-plan of", config.replan.from_run), row("Changes asked", config.replan.changes));
    }
    if (plan.summary) box.append(row("Summary", plan.summary));
    box.append(...commandRows(plan));
    return box;
  }

  /* The project's own commands the Planner copied from its CLAUDE.md; a person approves them. */
  function commandRows(plan) {
    const commands = plan.commands || {};
    const rows = [
      ["Setup", commands.setup || []],
      ["Checks", commands.project_checks || []],
    ]
      .filter(([, lines]) => lines.length)
      .map(([label, lines]) => row(label, lines));
    return rows.length ? rows : [row("Commands", "none listed")];
  }

  function notes(plan) {
    const nodes = [];
    if ((plan.skipped_subtasks || []).length) {
      nodes.push(row("Left out, done in Jira", plan.skipped_subtasks.map((s) => s.key + " (" + s.status + ")").join(", ")));
    }
    if ((plan.orchestrator_notes || []).length) {
      nodes.push(row("What Brigade changed in the Planner's answer", plan.orchestrator_notes));
    }
    return nodes;
  }

  function links(plan, approved) {
    const approval = plan.approval || {};
    const list = approved ? approval.written || [] : approval.jira_links || [];
    const title = approved ? "Written to Jira" : "Jira changes after approval";
    const lines = list.map((l) => l.subtask + " is blocked by " + l.blocked_by);
    for (const l of approved ? approval.already_in_jira || [] : []) {
      lines.push(l.subtask + " is blocked by " + l.blocked_by + " (already in Jira)");
    }
    return row(title + " (" + lines.length + ")", lines.length ? lines : "none: every dependency is already a Jira link");
  }

  function metrics(plan) {
    const p = plan.planner || {};
    const parts = [
      ["duration s", p.duration_seconds, 1],
      ["cost USD", p.total_cost_usd, 4],
      ["turns", p.num_turns, 0],
      ["rounds", p.rounds, 0],
    ]
      .filter(([, value]) => typeof value === "number")
      .map(([label, value, digits]) => label + " " + Number(value.toFixed(digits)));
    return parts.length ? row("Planner", parts.join(", ")) : null;
  }

  function render(run) {
    const plan = run.plan;
    const root = el("div", "pl-plan");
    if (!plan) {
      root.append(el("p", "muted", run.error ? "This run has no plan: " + run.error : "This run has no plan."));
      return root;
    }
    const approval = plan.approval || {};
    const approved = approval.status === "approved";
    const ctx = {
      byId: Object.fromEntries(plan.tasks.map((task) => [task.id, task])),
      newLinks: new Set((approval.jira_links || []).map((l) => l.subtask + "|" + l.blocked_by)),
      runAs: run.run_as || {},
      approved,
    };
    root.append(header(plan, run), el("h4", "pl-tasks-title", "Tasks (" + plan.tasks.length + "), in Jira's order:"));
    for (const task of plan.tasks) root.append(Brigade.planTask.render(task, ctx));
    const tail = el("section", "pl-tail");
    tail.append(...notes(plan), links(plan, approved));
    const m = metrics(plan);
    if (m) tail.append(m);
    root.append(tail);
    return root;
  }

  return { render, plural };
})();