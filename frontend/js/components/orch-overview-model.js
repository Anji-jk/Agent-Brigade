"use strict";
/*
 * What the Overview page decides from the data, with no DOM: how numbers are written, the cards,
 * the slim row under them and the bars of the chart. The cards hold project totals only (every
 * run added up); one run's numbers appear in the chart and the table, never on a card.
 */
window.Brigade = window.Brigade || {};

Brigade.overviewModel = (function () {
  const money = (n) => {
    const value = Number(n) || 0;
    return "$" + (value > 0 && value < 0.01 ? value.toFixed(4) : value.toFixed(2));
  };
  const num = (n) => (Number(n) || 0).toLocaleString("en-US");

  function compact(n) {
    const value = Number(n) || 0;
    if (value >= 1e6) return +(value / 1e6).toFixed(1) + "M";
    if (value >= 1e3) return +(value / 1e3).toFixed(1) + "k";
    return String(Math.round(value));
  }

  function duration(seconds) {
    const total = Math.round(Number(seconds) || 0);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    if (h) return h + "h " + m + "m";
    return m ? m + "m " + (total % 60) + "s" : total + "s";
  }

  const STATE = {
    finished: ["Done", "ok"],
    running: ["In progress", "busy"],
    failed: ["Failed", "bad"],
    stopped: ["Needs attention", "warn"],
    interrupted: ["Interrupted", "warn"],
  };
  const stateWord = (state) => {
    const [text, kind] = STATE[state] || [state, "idle"];
    return { text, kind };
  };

  const tail = (runId) => String(runId).split("-").pop();
  const label = (row) => row.story_key + " · " + tail(row.run_id);

  /** The top cards: totals over all the runs of the project. */
  function cards(data) {
    const { runs, cost, tokens, time } = data;
    const unrecorded = tokens.planning_recorded < tokens.planning_plans;
    return [
      { title: "Stories completed", value: runs.stories_complete + " / " + runs.stories_approved, sub: runs.stories_approved + " approved · " + runs.stories + " run", icon: "ok" },
      { title: "Active now", value: String(runs.stories_active), sub: runs.stories_active === 1 ? "story being built" : "stories being built", icon: "bolt" },
      {
        title: "Tokens",
        value: num(tokens.input) + " in / " + num(tokens.output) + " out",
        sub: "cache " + num(tokens.cache),
        note: unrecorded ? "Planning tokens recorded for " + tokens.planning_recorded + " of " + tokens.planning_plans + " plans" : "",
        icon: "bot",
      },
      { title: "Cost", value: money(cost.total), sub: "build " + money(cost.build) + " + planning " + money(cost.planning), icon: "coin" },
      { title: "Total time", value: duration(time.wall_clock_seconds), sub: "agents worked " + duration(time.agent_seconds), icon: "refresh" },
    ];
  }

  /** The slim row: [label, text] pairs. */
  function facts(data) {
    const { runs, tasks, by_role: roles } = data;
    const states = Object.entries(runs.by_state).map(([state, n]) => n + " " + stateWord(state).text.toLowerCase());
    return [
      ["Runs", runs.total ? runs.total + " (" + states.join(", ") + ")" : "none yet"],
      ["Tasks merged", tasks.merged + " / " + tasks.planned],
      ["Attempts", tasks.attempts + " (" + tasks.retries + " " + (tasks.retries === 1 ? "retry" : "retries") + ")"],
      ["Cost by role", roles.length ? roles.map((g) => g.name + " " + money(g.cost)).join(" · ") : "none yet"],
    ];
  }

  const shortDate = (stamp) => {
    const date = new Date(stamp);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };
  /** The small line under a bar: date, tasks merged / planned, attempts. */
  const runNote = (row) => [shortDate(row.started_at), row.tasks_merged + " / " + row.tasks_planned + " tasks", row.attempts + (row.attempts === 1 ? " attempt" : " attempts")].filter(Boolean).join(" · ");
  const average = (rows) => (rows.length ? rows.reduce((sum, row) => sum + row.cost, 0) / rows.length : 0);

  /** A page of runs (newest first) as the chart draws them: oldest left, newest right. */
  const chartRows = (items) => items.slice().reverse();

  /** A round number at or above `value`, for an axis (1, 2, 5 times a power of ten). */
  function niceMax(value) {
    if (!(value > 0)) return 1;
    const power = Math.pow(10, Math.floor(Math.log10(value)));
    const step = [1, 2, 5, 10].find((s) => s * power >= value);
    return step * power;
  }

  return { money, num, compact, duration, stateWord, tail, label, cards, facts, chartRows, niceMax, shortDate, runNote, average };
})();
