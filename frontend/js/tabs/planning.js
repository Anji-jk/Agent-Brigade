"use strict";
/*
 * The Planning tab: the Jira tree (Sync), then for each story Check and Plan (with the optional
 * budget). Talks to /api/tracker and /api/stories (backend/api/planning.py). A plan takes
 * minutes, so after Plan the page asks for the run every few seconds until it has finished.
 * The plan itself is read and approved in the panel on the right (tabs/plan-panel.js).
 * What this page learned about a story (its check, its run) is kept in memory only.
 */
window.Brigade = window.Brigade || {};

Brigade.planning = (function () {
  const { $, el, when, api } = Brigade.dom;
  const POLL_MS = 3000;
  const MAX_POLL_ERRORS = 3;
  const state = {
    tree: null,
    epicKey: undefined,
    filter: "all",
    search: "",
    mem: {},
    polls: {},
    leftOpen: true,
  };
  const memOf = (key) => (state.mem[key] = state.mem[key] || {});

  // ---------- what is shown ----------

  function hit(item, query) {
    return (item.key + " " + item.summary).toLowerCase().includes(query);
  }

  function shownStories(epic) {
    const query = state.search.trim().toLowerCase();
    const epicHit = query && hit({ key: epic.key || "", summary: epic.summary }, query);
    return epic.stories.filter((story) => {
      const { group } = Brigade.storyState.describe(story, memOf(story.key));
      return Brigade.storyState.inFilter(state.filter, group) && (!query || epicHit || hit(story, query));
    });
  }

  function epicShown(epic) {
    const narrowed = state.filter !== "all" || state.search.trim() !== "";
    return !narrowed || shownStories(epic).length > 0;
  }

  function notice(text) {
    $("plan-notice").textContent = text || "";
    $("plan-notice").hidden = !text;
  }

  function render() {
    const tree = state.tree;
    if (!tree) return;
    $("plan-synced").textContent = "Last synced: " + (tree.last_synced ? when(tree.last_synced) : "never");
    const epics = tree.epics.filter(epicShown);
    if (!epics.some((epic) => epic.key === state.epicKey)) state.epicKey = epics.length ? epics[0].key : undefined;
    $("plan-epics").replaceChildren(
      Brigade.epicList.render(
        tree.space,
        epics,
        state.epicKey,
        (key) => {
          state.epicKey = key;
          render();
        },
        { collapsed: !state.leftOpen, onToggle: toggleLeft },
      ),
    );
    $("plan-epics").parentElement.classList.toggle("left-closed", !state.leftOpen);
    const epic = epics.find((item) => item.key === state.epicKey);
    if (!epic) {
      const empty = tree.epics.length ? "No story matches the filter or the search." : "Nothing synced yet. Press Sync from JIRA.";
      $("plan-main").replaceChildren(el("p", "empty", empty));
      return;
    }
    const stories = shownStories(epic);
    const list = el("div", "pl-cards");
    for (const story of stories) list.append(card(story));
    $("plan-main").replaceChildren(
      Brigade.epicList.header(epic),
      el("h3", "pl-subhead", "Stories (" + stories.length + ")"),
      list,
    );
  }

  function toggleLeft() {
    state.leftOpen = !state.leftOpen;
    remember("brigade.planLeft", state.leftOpen ? "open" : "closed");
    render();
  }

  function card(story) {
    const mem = memOf(story.key);
    return Brigade.storyCard.render(story, mem, {
      onCheck: () => check(story.key),
      onPlan: () => plan(story.key),
      onView: () => Brigade.planPanel.open(story.key),
      onToggle: () => {
        mem.open = !mem.open;
        render();
      },
    });
  }

  // ---------- actions ----------

  async function load() {
    try {
      state.tree = await api("GET", "/api/tracker/tree");
      notice("");
    } catch (error) {
      notice(error.message);
      return;
    }
    for (const epic of state.tree.epics) {
      for (const story of epic.stories) {
        const run = story.latest_run;
        if (run && run.status === "planning" && !state.polls[story.key]) {
          poll(story.key, run.run_id, 0);
          Brigade.planPanel.learn(story.key);
        }
      }
    }
    render();
  }

  async function sync() {
    const button = $("plan-sync");
    button.disabled = true;
    $("plan-synced").textContent = "Syncing...";
    try {
      await api("POST", "/api/tracker/sync");
      await load();
    } catch (error) {
      notice(error.message);
    } finally {
      button.disabled = false;
      if (state.tree) render();
    }
  }

  async function check(key) {
    const mem = memOf(key);
    mem.checking = true;
    mem.checkError = null;
    mem.open = true;
    render();
    try {
      mem.check = await api("POST", "/api/stories/" + key + "/checks", { run_tests: true });
      mem.checkedAt = Date.now();
    } catch (error) {
      mem.check = null;
      mem.checkError = error.message;
    }
    mem.checking = false;
    render();
  }

  async function plan(key) {
    const budget = await Brigade.budgetPopup.ask(key);
    if (budget === undefined) return; // dismissed: nothing is planned
    const mem = memOf(key);
    mem.planError = null;
    try {
      mem.run = await api("POST", "/api/stories/" + key + "/plan", budget === null ? {} : { budget });
      mem.open = false;
      poll(key, mem.run.run_id, 0);
    } catch (error) {
      mem.planError = error.message;
      mem.open = true;
    }
    render();
  }

  function poll(key, runId, errors) {
    clearTimeout(state.polls[key]);
    state.polls[key] = setTimeout(async () => {
      const mem = memOf(key);
      try {
        mem.run = await api("GET", "/api/runs/" + runId);
        if (mem.run.status === "planning") return poll(key, runId, 0);
        mem.open = mem.run.status === "failed";
        Brigade.planPanel.finished(key, mem.run);
      } catch (error) {
        if (errors + 1 < MAX_POLL_ERRORS) return poll(key, runId, errors + 1);
        mem.planError = "Lost contact with the server: " + error.message;
        mem.open = true;
      }
      delete state.polls[key];
      render();
    }, POLL_MS);
  }

  // ---------- start ----------

  function init() {
    Brigade.planPanel.init({ memOf, poll, render });
    state.leftOpen = recall("brigade.planLeft") !== "closed";
    $("plan-sync").addEventListener("click", sync);
    $("plan-filter").addEventListener("change", (event) => {
      state.filter = event.target.value;
      render();
    });
    $("plan-search").addEventListener("input", (event) => {
      state.search = event.target.value;
      render();
    });
    for (const [value, label] of Brigade.storyState.FILTERS) {
      const option = el("option", "", label);
      option.value = value;
      $("plan-filter").append(option);
    }
    load();
  }

  return { init };
})();