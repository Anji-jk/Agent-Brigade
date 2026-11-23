"use strict";
/*
 * What the Orchestrator tab decides from the data, with no DOM: the word and colour of a task,
 * the word of a run, and which of Stop, Continue and Cancel a task may use (and why not).
 * The buttons mirror what the server refuses with HTTP 409, so a person is told the reason
 * before pressing, not after.
 */
window.Brigade = window.Brigade || {};

Brigade.orchModel = (function () {
  const RUN_WORD = {
    not_started: ["Not started", "idle"],
    running: ["In progress", "busy"],
    finished: ["Done", "ok"],
    stopped: ["Needs attention", "bad"],
    paused: ["Paused", "warn"],
    interrupted: ["Interrupted", "warn"],
  };
  const STAGE_WORD = { builder: "building", checks: "checking", tester: "testing", reviewer: "reviewing", judge: "judging", documenter: "documenting", "doc-reviewer": "reviewing" };

  function runWord(buildState) {
    const [text, kind] = RUN_WORD[buildState] || [buildState, "idle"];
    return { text, kind };
  }

  function newest(task) {
    return task.attempts.length ? task.attempts[task.attempts.length - 1] : null;
  }

  /** {text, kind}: kind is one of ok, busy, warn, bad, idle (the chip colours). */
  function taskWord(task) {
    if (task.control === "stopping") return { text: "stopping", kind: "warn" };
    if (task.control === "cancelling") return { text: "cancelling", kind: "warn" };
    if (task.control === "continuing") return { text: "continuing", kind: "busy" };
    if (task.stage === "merged") return { text: "done", kind: "ok" };
    if (task.status === "cancelled" || task.control === "cancelled") return { text: "cancelled", kind: "bad" };
    if (task.status === "stopped" || task.control === "stopped") return { text: "stopped", kind: "warn" };
    if (task.status === "waiting" || task.status === "queued") return { text: "pending", kind: "idle" };
    if (task.status === "error") {
      const attempt = newest(task);
      return { text: attempt && attempt.outcome === "needs_review" ? "needs review" : "failed", kind: "bad" };
    }
    if (task.status === "done") return { text: "done, to merge", kind: "busy" };
    return { text: STAGE_WORD[task.stage] || "running", kind: "busy" };
  }

  const isMerged = (task) => task.stage === "merged";
  const isCancelled = (task) => task.status === "cancelled" || task.control === "cancelled";
  const isStopped = (task) => task.status === "stopped" || task.control === "stopped";

  function stopRule(task, buildState) {
    if (isMerged(task)) return "It is already merged.";
    if (isCancelled(task)) return "It was cancelled.";
    if (isStopped(task)) return "It is already stopped.";
    if (task.control) return "It is already being " + task.control.replace("ing", "ed") + ".";
    if (buildState !== "running") return "No loop is working on this run now.";
    if (task.status !== "running") return "It is not running now.";
    return null;
  }

  function continueRule(task) {
    if (isMerged(task)) return "It is already merged.";
    if (isCancelled(task)) return "It was cancelled: that is final.";
    if (task.control === "stopping") return "It is still being stopped: try again in a moment.";
    if (task.control === "continuing") return "It is already continuing.";
    if (!isStopped(task)) return "It is not stopped.";
    return null;
  }

  function cancelRule(task) {
    if (isMerged(task)) return "It is already merged: it is done.";
    if (isCancelled(task)) return "It was already cancelled.";
    if (task.control === "cancelling") return "It is already being cancelled.";
    return null;
  }

  /** For each action: null when allowed, else the reason in words. */
  function rules(task, buildState) {
    return { stop: stopRule(task, buildState), continue: continueRule(task), cancel: cancelRule(task) };
  }

  /** The strip's caption under a task: what it waits for, in plan order. */
  function after(task) {
    return task.depends_on.length ? "after " + task.depends_on.join(", ") : "";
  }

  function merged(tasks) {
    return tasks.filter(isMerged).length;
  }

  /** The task to show first: one that is running, else the first not merged, else the first. */
  function firstToShow(tasks) {
    return (
      tasks.find((t) => t.status === "running") || tasks.find((t) => !isMerged(t)) || tasks[0] || null
    );
  }

  return { runWord, taskWord, rules, after, merged, firstToShow, newest, isStopped, isMerged };
})();