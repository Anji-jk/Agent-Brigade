"use strict";
/*
 * The plan panel of the Planning page: which story's plan is open, loading it, Re-plan and
 * Approve. Re-plan never blocks reading: the plan on screen stays as it is while the new run is
 * made, and the panel switches to the new plan when planning.js reports that it has finished.
 */
window.Brigade = window.Brigade || {};

Brigade.planPanel = (function () {
  const { $, api } = Brigade.dom;
  const SHOWN = ["waiting", "approved"];
  let ctx = null; // { memOf, poll, render } from planning.js
  let view = null;

  /** The run to read: the newest plan waiting or approved, else the newest replaced one. */
  function pick(runs) {
    return runs.find((r) => SHOWN.includes(r.status)) || runs.find((r) => r.status === "superseded") || null;
  }

  function paint() {
    const side = $("plan-side");
    side.hidden = !view;
    side.parentElement.classList.toggle("has-side", Boolean(view));
    if (!view) return side.replaceChildren();
    const old = side.querySelector(".pl-side-body");
    const keep = old && old.dataset.run === (view.runId || "") ? old.scrollTop : 0;
    side.replaceChildren(Brigade.planSide.render(view, handlers));
    side.querySelector(".pl-side-body").scrollTop = keep;
  }

  async function showRun(runId) {
    const mine = view;
    Object.assign(mine, { runId, run: null, loading: true });
    paint();
    try {
      const run = await api("GET", "/api/runs/" + runId);
      if (view === mine && mine.runId === runId) mine.run = run;
    } catch (error) {
      if (view === mine) mine.error = error.message;
    }
    if (view === mine) {
      mine.loading = false;
      paint();
    }
  }

  /** Reads the story's runs; `toLatest` also moves the panel to the newest plan. */
  async function refresh(key, toLatest) {
    const mine = view;
    let runs;
    try {
      runs = await api("GET", "/api/stories/" + key + "/runs");
    } catch (error) {
      if (view === mine) {
        mine.loading = false;
        mine.error = error.message;
        paint();
      }
      return;
    }
    if (view !== mine) return;
    const target = pick(runs);
    mine.runs = runs;
    mine.busy = runs.some((r) => r.status === "planning");
    ctx.memOf(key).hasPlan = Boolean(target);
    if (target && (toLatest || !mine.run)) return showRun(target.run_id);
    mine.loading = false;
    if (!target && runs[0] && runs[0].status === "failed") mine.error = runs[0].error;
    paint();
  }

  function open(key) {
    view = { key, runs: [], run: null, runId: null, busy: false, fresh: false, working: false, loading: true, error: null };
    paint();
    return refresh(key, true);
  }

  async function replan() {
    const mine = view;
    if (!mine || !mine.run) return;
    const changes = await Brigade.replanPopup.ask(mine.key);
    if (changes === undefined) return;
    Object.assign(mine, { error: null, fresh: false });
    try {
      const started = await api("POST", "/api/runs/" + mine.run.run_id + "/replan", { changes });
      const mem = ctx.memOf(mine.key);
      mem.prevRun = mine.run;
      mem.run = started;
      mem.hasPlan = true;
      mine.busy = true;
      mine.runs = [started, ...mine.runs];
      ctx.poll(mine.key, started.run_id, 0);
      ctx.render();
    } catch (error) {
      mine.error = error.message;
    }
    if (view === mine) paint();
  }

  async function approve() {
    const mine = view;
    if (!mine || !mine.run || mine.working) return;
    Object.assign(mine, { working: true, error: null });
    paint();
    try {
      mine.run = await api("POST", "/api/runs/" + mine.run.run_id + "/approve");
      ctx.memOf(mine.key).run = mine.run;
      await refresh(mine.key, false);
    } catch (error) {
      mine.error = error.message;
    }
    mine.working = false;
    if (view === mine) paint();
    ctx.render();
  }

  /** planning.js: a planning run of `key` has stopped (`run` is what the server now says). */
  function finished(key, run) {
    const mem = ctx.memOf(key);
    const failed = run.status === "failed";
    if (failed && mem.prevRun) mem.run = mem.prevRun; // the plan being read is still the story's plan
    mem.prevRun = null;
    if (!view) {
      if (!failed && run.status === "waiting") open(key);
      return;
    }
    if (view.key !== key) return;
    const wasBusy = view.busy;
    view.busy = false;
    view.error = failed ? "The new plan failed: " + (run.error || "no reason was given") : null;
    view.fresh = !failed && wasBusy;
    refresh(key, !failed);
  }

  /** planning.js: a story is being planned after a reload; find out whether it has a plan to read. */
  async function learn(key) {
    try {
      const runs = await api("GET", "/api/stories/" + key + "/runs");
      ctx.memOf(key).hasPlan = Boolean(pick(runs));
      ctx.render();
    } catch (error) {
      /* the card simply shows no View plan button */
    }
  }

  const handlers = {
    onClose: () => {
      view = null;
      paint();
    },
    onSelect: (runId) => {
      view.fresh = false;
      view.error = null;
      showRun(runId);
    },
    onLatest: () => {
      view.fresh = false;
      refresh(view.key, true);
    },
    onReplan: replan,
    onApprove: approve,
  };

  return { init: (context) => (ctx = context), open, finished, learn };
})();