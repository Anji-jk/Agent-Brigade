"use strict";
/*
 * What a story card shows, worked out from the tree (the story and its newest run) and from
 * what this page has done to the story in this visit: `mem` = { check, checking, run, ... }.
 * The check result is kept only while the page is open; Plan needs a check that passed.
 */
window.Brigade = window.Brigade || {};

Brigade.storyState = (function () {
  const FILTERS = [
    ["all", "All stories"],
    ["new", "Not checked"],
    ["passed", "Checks passed"],
    ["failed", "Needs fixing"],
    ["planning", "Planning"],
    ["ready", "Plan ready"],
    ["approved", "Approved"],
  ];

  const plural = (count, word) => count + " " + word + (count === 1 ? "" : "s");

  function newTally() {
    return { ok: 0, warning: 0, failed: 0, skipped: 0, total: 0 };
  }

  /** Counts of a check result, overall and per group; skipped checks are not part of the total. */
  function tally(check) {
    const all = Object.assign(newTally(), { groups: {} });
    for (const item of check.checks) {
      const group = (all.groups[item.group] = all.groups[item.group] || newTally());
      for (const t of [all, group]) {
        t[item.status] += 1;
        if (item.status !== "skipped") t.total += 1;
      }
    }
    return all;
  }

  /** { group, kind, text, action }: action is "check", "plan" or null (nothing to press). */
  function describe(story, mem) {
    const run = mem.run || story.latest_run;
    const status = run && run.status !== "superseded" ? run.status : null;
    if (mem.checking) return { group: "checking", kind: "busy", text: "Checking...", action: null };
    if (status === "planning") return { group: "planning", kind: "busy", text: "Planning...", action: null };
    if (status === "waiting") return { group: "ready", kind: "ok", text: "Plan ready", action: null };
    if (status === "approved") return { group: "approved", kind: "ok", text: "Approved", action: null };
    if (mem.check) {
      const t = tally(mem.check);
      if (!mem.check.ready) return { group: "failed", kind: "bad", text: t.failed + " failed", action: "check" };
      if (t.warning) return { group: "passed", kind: "warn", text: plural(t.warning, "Warning"), action: "plan" };
      return { group: "passed", kind: "ok", text: "Checks Passed", action: "plan" };
    }
    if (status === "failed") return { group: "failed", kind: "bad", text: "Plan failed", action: "check" };
    return { group: "new", kind: "idle", text: "Not Checked", action: "check" };
  }

  function inFilter(filter, group) {
    return filter === "all" || filter === group;
  }

  return { FILTERS, tally, describe, inFilter, plural };
})();