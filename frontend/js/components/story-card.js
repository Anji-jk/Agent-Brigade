"use strict";
/*
 * One story as a card: title, a status badge, the button for the next step (Check or Plan) and
 * a panel that opens to show the check result or what went wrong. It draws; planning.js acts.
 */
window.Brigade = window.Brigade || {};

Brigade.storyCard = (function () {
  const { el, icon } = Brigade.dom;
  const money = (value) => "$" + Number(value).toFixed(2);
  const BADGE_ICON = { ok: "ok", warn: "warn", bad: "warn" };

  function badge(state) {
    const node = el("span", "pl-badge pl-" + state.kind);
    if (state.kind === "busy") node.append(el("span", "dots small"));
    else if (BADGE_ICON[state.kind]) node.append(icon(BADGE_ICON[state.kind]));
    node.append(state.text);
    return node;
  }

  function button(action, handlers) {
    const plan = action === "plan";
    const node = el("button", "btn " + (plan ? "btn-gold" : "btn-outline"));
    node.type = "button";
    node.append(...(plan ? [icon("network"), "Plan"] : ["Check"]));
    node.addEventListener("click", plan ? handlers.onPlan : handlers.onCheck);
    return node;
  }

  function viewButton(onView) {
    const node = el("button", "btn btn-outline btn-small", "View plan");
    node.type = "button";
    node.addEventListener("click", onView);
    return node;
  }

  function runLine(run) {
    const parts = ["Plan run " + run.run_id + ": " + run.status];
    if (run.budget) parts.push("budget " + money(run.budget));
    if (run.cost) parts.push("cost " + money(run.cost));
    return el("div", "muted small pl-runline", parts.join(" - "));
  }

  function panel(story, mem, handlers) {
    const body = el("div", "pl-panel");
    const run = mem.run || story.latest_run;
    if (run) body.append(runLine(run));
    if (run && run.status === "failed" && run.error) body.append(Brigade.checkPanel.message(run.error));
    if (mem.planError) body.append(Brigade.checkPanel.message(mem.planError));
    if (mem.checkError) body.append(Brigade.checkPanel.message(mem.checkError));
    if (mem.check) body.append(Brigade.checkPanel.render(mem, handlers.onCheck));
    else if (!mem.checkError) {
      body.append(el("p", "muted", "Press Check to see whether this story is ready to plan."));
    }
    return body;
  }

  function render(story, mem, handlers) {
    const state = Brigade.storyState.describe(story, mem);
    const card = el("article", "pl-card" + (mem.open ? " open" : ""));
    const row = el("div", "pl-card-row");
    const mark = el("span", "pl-mark");
    mark.append(icon("book"));
    const title = el("div", "pl-card-title");
    title.append(
      el("b", "", story.key + ": " + story.summary),
      el("span", "muted small", Brigade.storyState.plural(story.subtasks.length, "sub-task")),
    );
    const toggle = el("button", "icon-btn small pl-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", String(Boolean(mem.open)));
    toggle.setAttribute("aria-label", (mem.open ? "Hide" : "Show") + " details of " + story.key);
    toggle.append(icon("chevron"));
    toggle.addEventListener("click", handlers.onToggle);
    row.append(mark, title, badge(state));
    if (state.action) row.append(button(state.action, handlers));
    if (handlers.onView && (state.group === "ready" || state.group === "approved" || mem.hasPlan)) {
      row.append(viewButton(handlers.onView));
    }
    row.append(toggle);
    card.append(row);
    if (mem.open) card.append(panel(story, mem, handlers));
    return card;
  }

  return { render };
})();