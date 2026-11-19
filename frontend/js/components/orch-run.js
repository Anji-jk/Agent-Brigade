"use strict";
/* The run header: story, run word, cost against budget, and Start / Stop all / Continue all. */
window.Brigade = window.Brigade || {};

Brigade.orchRun = (function () {
  const { el, when } = Brigade.dom;
  const { runWord, merged, isStopped } = Brigade.orchModel;
  const { money } = Brigade.orchStories;

  function button(label, kind, reason, onClick) {
    const node = el("button", "btn btn-small " + kind, label);
    node.type = "button";
    node.disabled = reason !== null;
    if (reason !== null) node.title = reason;
    node.addEventListener("click", onClick);
    return node;
  }

  /** The words for a run that has a cancelled task: it is over but not fully done. */
  function summary(run) {
    const done = merged(run.tasks);
    const cancelled = run.tasks.filter((t) => t.status === "cancelled" || t.control === "cancelled").length;
    let text = done + " of " + run.tasks.length + " sub-tasks merged";
    if (run.build_state === "finished" && cancelled) {
      text = "Finished, with " + cancelled + " cancelled task" + (cancelled > 1 ? "s" : "") + ": not fully done. " + text;
    }
    return text;
  }

  function render(box, run, summaryText, act) {
    box.replaceChildren();
    const word = runWord(run.build_state);
    const title = el("div", "orch-run-title");
    title.append(el("b", "", run.story_key + " \u00B7 " + (summaryText || "")), el("span", "orch-chip orch-" + word.kind, word.text));
    const chips = el("div", "orch-chips");
    chips.append(el("span", "orch-info", "Run: " + run.run_id));
    if (run.branch) chips.append(el("span", "orch-info", "Branch: " + run.branch));
    const cost = run.budget != null ? money(run.cost) + " of " + money(run.budget) : money(run.cost);
    const meta = el("div", "muted small", [summary(run), "Cost " + cost, run.started_at && "Started " + when(run.started_at)].filter(Boolean).join(" · "));

    const state = run.build_state;
    const anyRunning = run.tasks.some((t) => t.status === "running" && !t.control);
    const anyStopped = run.tasks.some(isStopped);
    const startWhy = state === "not_started" ? null : state === "running" ? "It is already running." : "Use Continue for a stopped run.";
    const stopWhy = state === "running" && anyRunning ? null : "Nothing is running now.";
    const contWhy = anyStopped || state === "stopped" ? null : "No task is stopped.";
    const buttons = el("div", "orch-bar-actions");
    buttons.append(
      button("Start", "btn-gold", startWhy, act.start),
      button("Stop all", "btn-outline", stopWhy, act.stopAll),
      button("Continue all", "btn-outline", contWhy, act.continueAll),
    );
    chips.append(buttons);
    box.append(title, chips, meta);
  }

  return { render };
})();