"use strict";
/*
 * The plan panel on the right of the Planning page: a title, the story's runs, notices, the plan
 * itself and the approval bar. It only draws what `view` says; tabs/plan-panel.js acts.
 *   view = { key, run, runs, runId, busy, fresh, working, loading, error }
 */
window.Brigade = window.Brigade || {};

Brigade.planSide = (function () {
  const { el, icon, when } = Brigade.dom;

  function runStrip(view, handlers) {
    const strip = el("div", "pl-runs");
    strip.append(el("span", "muted small", "Runs of " + view.key + ":"));
    for (const run of view.runs.filter((r) => r.status !== "planning")) {
      const tail = run.run_id.replace(view.key + "-", "");
      const chip = el("button", "pl-chip pl-runchip" + (run.run_id === view.runId ? " current" : ""));
      chip.type = "button";
      chip.append(el("b", "", tail), " " + run.status);
      chip.addEventListener("click", () => handlers.onSelect(run.run_id));
      strip.append(chip);
    }
    return strip;
  }

  function notice(text, kind, busy) {
    const box = el("div", "pl-notice pl-" + kind);
    box.append(busy ? el("span", "dots small") : icon(kind === "bad" ? "warn" : "ok"), el("span", "", text));
    return box;
  }

  function notices(view, handlers) {
    const out = [];
    if (view.busy) {
      out.push(notice("A new plan is being made from your suggestion. You can keep reading this one; this panel switches to the new plan when it is ready.", "busy", true));
    }
    if (view.fresh) out.push(notice("The new plan is ready. This is the latest plan.", "ok"));
    if (view.error) out.push(notice(view.error, "bad"));
    const run = view.run;
    if (run && run.status === "superseded") {
      const box = notice("This plan was replaced by a newer one.", "warn");
      const latest = el("button", "btn btn-outline btn-small", "Show latest");
      latest.type = "button";
      latest.addEventListener("click", handlers.onLatest);
      box.append(latest);
      out.push(box);
    }
    return out;
  }

  function approvalBar(view, handlers) {
    const run = view.run;
    if (!run || !run.plan) return null;
    const approval = run.plan.approval || {};
    const bar = el("footer", "pl-approve");
    if (run.status === "approved") {
      const count = (approval.written || []).length + (approval.already_in_jira || []).length;
      bar.append(icon("ok"), el("b", "", "Approved " + when(approval.approved_at)), el("span", "muted small", Brigade.planView.plural(count, "blocked-by link") + " in Jira."));
      return bar;
    }
    if (run.status !== "waiting") return null;
    const links = (approval.jira_links || []).length;
    const off = view.busy || view.working;
    const replan = el("button", "btn btn-outline", "Re-plan");
    replan.type = "button";
    replan.disabled = off;
    replan.prepend(icon("refresh"));
    replan.addEventListener("click", handlers.onReplan);
    const approve = el("button", "btn btn-gold", view.working ? "Approving..." : "Approve Plan");
    approve.type = "button";
    approve.disabled = off;
    approve.prepend(icon("check"));
    approve.addEventListener("click", handlers.onApprove);
    const ask = el("div", "pl-ask");
    ask.append(el("b", "", "Do you approve this plan?"));
    if (links) ask.append(el("span", "muted small", "Approve adds " + Brigade.planView.plural(links, "blocked-by link") + " in Jira."));
    bar.append(icon("bot"), ask, replan, approve);
    return bar;
  }

  function render(view, handlers) {
    const root = el("div", "pl-side-in");
    const head = el("header", "pl-side-head");
    const close = el("button", "icon-btn small");
    close.type = "button";
    close.setAttribute("aria-label", "Close the plan");
    close.append(icon("x"));
    close.addEventListener("click", handlers.onClose);
    head.append(icon("bot"), el("h2", "", "Plan for Story " + view.key), close);
    const body = el("div", "pl-side-body");
    body.dataset.run = view.runId || "";
    if (view.runs.length > 1) body.append(runStrip(view, handlers));
    body.append(...notices(view, handlers));
    if (view.loading) body.append(el("p", "muted", "Loading the plan..."));
    else if (view.run) body.append(Brigade.planView.render(view.run));
    else if (!view.error && !view.busy) body.append(el("p", "muted", "This story has no plan yet."));
    root.append(head, body);
    const bar = approvalBar(view, handlers);
    if (bar) root.append(bar);
    return root;
  }

  return { render };
})();