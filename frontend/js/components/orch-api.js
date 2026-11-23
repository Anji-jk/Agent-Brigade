"use strict";
/* The Orchestrator tab's calls, in one place: what each URL is, so no other file spells one. */
window.Brigade = window.Brigade || {};

Brigade.orchApi = (function () {
  const { api } = Brigade.dom;
  const run = (id) => "/api/runs/" + encodeURIComponent(id);
  const task = (id, key) => run(id) + "/tasks/" + encodeURIComponent(key);
  // the report each agent wrote (the Doc Reviewer's is the judge's: the decision comes from it)
  const STAGE_OF = { builder: "build", tester: "test", reviewer: "judge", documenter: "docs", "doc-reviewer": "judge" };

  return {
    stories: () => api("GET", "/api/orchestrator/stories"),
    overview: () => api("GET", "/api/orchestrator/overview"),
    overviewRuns: (page, size) => api("GET", "/api/orchestrator/overview/runs?page=" + page + "&size=" + size),
    progress: (id) => api("GET", run(id) + "/progress"),
    start: (id) => api("POST", run(id) + "/start"),
    stopTask: (id, key) => api("POST", task(id, key) + "/stop"),
    cancelTask: (id, key) => api("POST", task(id, key) + "/cancel"),
    continueTask: (id, key) => api("POST", task(id, key) + "/continue"),
    stopAll: (id) => api("POST", run(id) + "/stop"),
    continueAll: (id) => api("POST", run(id) + "/continue"),
    events: (id, key, number, source, after) =>
      api(
        "GET",
        task(id, key) + "/attempts/" + number + "/events?source=" + source + "&after=" + after,
      ),
    report: (id, key, number, role) =>
      api("GET", task(id, key) + "/attempts/" + number + "/report/" + STAGE_OF[role]),
    hasReport: (role) => role in STAGE_OF,
  };
})();