"use strict";
/* The Orchestrator tab, Stories view: pick a story, watch its run, act on its tasks. */
window.Brigade = window.Brigade || {};

Brigade.orchestrator = (function () {
  const { $, el } = Brigade.dom;
  const api = Brigade.orchApi;
  const model = Brigade.orchModel;
  const TICK = 2500;
  const s = { stories: [], counts: {}, needle: "", key: null, runId: null, run: null, task: null, attempt: null, role: "builder", report: null };
  let feed, timer, queue = Promise.resolve(), working = false;
  const countsAt = {}; // when each story's n / m was last read

  const notice = (text, bad) => {
    const box = $("orch-notice");
    box.textContent = text || "";
    box.hidden = !text;
    box.classList.toggle("status-error", Boolean(bad));
  };
  const task = () => (s.run ? s.run.tasks.find((t) => t.key === s.task) : null);
  const attempt = () => {
    const t = task();
    return t && t.attempts.find((a) => a.number === s.attempt);
  };

  async function guarded(work) {
    try {
      notice("");
      const answer = await work();
      await refresh();
      return answer;
    } catch (error) {
      notice(error.message, true);
      return undefined;
    }
  }

  async function confirm(title, text, label) {
    const body = el("div", "popup-body");
    body.append(el("p", "", text));
    const popup = Brigade.popup.open({ title, iconName: "warn", body, buttons: [{ label, value: "yes", kind: "primary" }, { label: "Back", value: "no" }] });
    return (await popup.closed) === "yes";
  }

  const startRun = async () => {
    const budget = s.run.budget != null ? "Budget stored on this run: " + Brigade.orchStories.money(s.run.budget) + "." : "This run has no budget.";
    if (await confirm("Start building " + s.run.story_key + "?", budget + " Closing this window starts nothing.", "Start")) {
      guarded(() => api.start(s.runId));
    }
  };
  const cancelTask = async () => {
    const text = "Cancel " + s.task + "? A cancelled task cannot be continued.";
    if (await confirm("Cancel task?", text, "Cancel Task")) guarded(() => api.cancelTask(s.runId, s.task));
  };
  const say = async (call) => {
    const answer = await guarded(call);
    if (answer && answer.detail) notice(answer.detail);
  };
  const act = {
    start: startRun,
    stopAll: () => say(() => api.stopAll(s.runId)),
    continueAll: () => say(() => api.continueAll(s.runId)),
  };
  const taskAct = {
    continue: () => say(() => api.continueTask(s.runId, s.task)),
    stop: () => say(() => api.stopTask(s.runId, s.task)),
    cancel: cancelTask,
  };

  function pickTask(key) {
    s.task = key;
    const t = task();
    s.attempt = t && t.attempts.length ? t.attempts[t.attempts.length - 1].number : null;
    resetAgent();
  }

  function resetAgent() {
    s.role = "builder";
    s.report = null;
    feed.reset();
    paintTask();
  }

  function paintTask() {
    const t = task();
    const none = $("orch-detail");
    none.hidden = !t;
    if (!t) return;
    Brigade.orchTaskbar.render($("orch-bar"), t, s.run.build_state, taskAct);
    const a = attempt();
    const picker = $("orch-attempt");
    picker.hidden = t.attempts.length < 2;
    picker.replaceChildren(...t.attempts.map((x) => new Option("Attempt " + x.number + (x.outcome ? " · " + x.outcome : ""), x.number)));
    picker.value = String(s.attempt);
    if (a && !a.sources.includes(s.role)) s.role = a.sources[0] || s.role;
    Brigade.orchAgent.tabs($("orch-tabs"), a, s.role, (role) => {
      s.role = role;
      s.report = null;
      feed.reset();
      paintTask();
    });
    Brigade.orchAgent.usage($("orch-usage"), a, s.role);
    $("orch-report").hidden = !api.hasReport(s.role);
    Brigade.orchReport.render($("orch-report"), s.report, Brigade.orchAgent.JOB[s.role]);
  }

  function paintRun() {
    const story = s.stories.find((x) => x.key === s.key);
    $("orch-empty").hidden = Boolean(s.run);
    $("orch-run-area").hidden = !s.run;
    if (!s.run) return;
    Brigade.orchRun.render($("orch-run"), s.run, story && story.summary, act);
    Brigade.orchStrip.render($("orch-strip"), s.run.tasks, s.task, (key) => {
      pickTask(key);
      paintRun();
    });
    const runs = story ? story.runs : [];
    const picker = $("orch-runs");
    picker.hidden = runs.length < 2;
    picker.replaceChildren(...runs.map((r) => new Option(r.run_id + " · " + model.runWord(r.build_state).text, r.run_id)));
    picker.value = s.runId;
    paintTask();
  }

  async function selectStory(key) {
    s.key = key;
    const story = s.stories.find((x) => x.key === key);
    s.runId = story && story.runs[0] ? story.runs[0].run_id : null;
    s.run = null;
    s.task = null;
    paintStories();
    await refresh();
    const first = model.firstToShow(s.run ? s.run.tasks : []);
    if (first) pickTask(first.key);
    paintRun();
  }

  const refresh = () => (queue = queue.then(readAll)); // one read at a time, in order

  async function readAll() {
    working = true;
    try {
      s.stories = await api.stories();
      if (s.runId) s.run = await api.progress(s.runId);
      paintStories();
      readCounts(); // not awaited: the other stories' n / m must not hold up this run
      const t = task();
      if (t && s.attempt === null && t.attempts.length) s.attempt = t.attempts[t.attempts.length - 1].number;
      paintRun();
      await readFeed();
      $("orch-updated").textContent = "Last updated " + new Date().toLocaleTimeString();
    } catch (error) {
      notice(error.message, true);
    } finally {
      working = false;
    }
  }

  const on = { pick: (key) => selectStory(key), start: async (key) => (await selectStory(key), startRun()) };

  function paintStories() {
    Brigade.orchStories.render($("orch-stories"), s.stories, s.key, s.counts, on, s.needle);
    const n = s.stories.filter((x) => x.runs.length).length;
    $("orch-count").textContent = "Stories (" + n + ")";
    $("orch-view-stories").textContent = "Stories (" + n + ")";
    const run = s.run;
    $("orch-runpill").hidden = !run;
    if (run) {
      $("orch-runpill").textContent = "Run: " + run.run_id;
      $("orch-runpill").classList.toggle("live", run.build_state === "running");
    }
  }

  /** "n / m merged" for each story with a started run: one progress read each. */
  async function readCounts() {
    const now = Date.now();
    for (const story of s.stories) {
      const newest = story.runs[0];
      if (!newest || newest.build_state === "not_started") continue;
      const mine = newest.run_id === s.runId && s.run;
      if (!mine && now - (countsAt[story.key] || 0) < 30000) continue; // others: every 30 s
      try {
        const run = mine ? s.run : await api.progress(newest.run_id);
        s.counts[story.key] = { done: model.merged(run.tasks), total: run.tasks.length };
        countsAt[story.key] = now;
      } catch (error) {
        /* the bar just stays as it was */
      }
    }
    paintStories();
  }

  async function readFeed() {
    const a = attempt();
    if (!a || !a.sources.includes(s.role)) return;
    const answer = await api.events(s.runId, s.task, a.number, s.role, feed.after());
    feed.apply(answer);
    if (api.hasReport(s.role) && !(s.report && s.report.exists)) {
      s.report = await api.report(s.runId, s.task, a.number, s.role);
      Brigade.orchReport.render($("orch-report"), s.report, Brigade.orchAgent.JOB[s.role]);
    }
  }

  /** A fold button on the stories list: collapsed it is a narrow rail, and the choice is remembered. */
  function foldLeft() {
    const layout = document.querySelector(".orch-layout");
    const button = el("button", "icon-btn small orch-fold");
    button.type = "button";
    button.append(Brigade.dom.icon("chevron"));
    const set = (collapsed) => {
      layout.classList.toggle("left-closed", collapsed);
      const label = collapsed ? "Show the stories" : "Hide the stories";
      button.title = label;
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-expanded", String(!collapsed));
    };
    let saved = null;
    try {
      saved = localStorage.getItem("brigade.orchLeft");
    } catch (error) {
      /* storage blocked: it just starts open */
    }
    set(saved === "closed");
    button.addEventListener("click", () => {
      const collapsed = !layout.classList.contains("left-closed");
      set(collapsed);
      try {
        localStorage.setItem("brigade.orchLeft", collapsed ? "closed" : "open");
      } catch (error) {
        /* not remembered */
      }
    });
    document.querySelector(".orch-left-head").prepend(button);
  }

  function init() {
    foldLeft();
    const list = $("orch-feed");
    const section = el("section", "orch-act");
    list.before(section);
    section.append(el("h3", "orch-act-head", "Activities"), list);
    feed = Brigade.orchFeed.create(list, () => $("orch-follow").checked);
    $("orch-attempt").addEventListener("change", (e) => {
      s.attempt = Number(e.target.value);
      resetAgent();
    });
    $("orch-runs").addEventListener("change", (e) => {
      s.runId = e.target.value;
      s.run = null;
      refresh().then(() => {
        const first = model.firstToShow(s.run ? s.run.tasks : []);
        if (first) pickTask(first.key);
        paintRun();
      });
    });
    $("orch-refresh").addEventListener("click", refresh);
    $("orch-search").addEventListener("input", (e) => {
      s.needle = e.target.value;
      paintStories();
    });
    $("orch-stories").append(el("p", "muted small", "Loading stories..."));
    refresh();
    timer = setInterval(() => !working && !document.hidden && !$("orchestrator").hidden && refresh(), TICK);
  }

  return { init, stop: () => clearInterval(timer) };
})();