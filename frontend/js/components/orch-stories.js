"use strict";
/* The left list: approved stories, each with the word of its newest run, a progress bar or Start Story. */
window.Brigade = window.Brigade || {};

Brigade.orchStories = (function () {
  const { el, icon } = Brigade.dom;
  const { runWord } = Brigade.orchModel;
  const money = (n) => "$" + Number(n || 0).toFixed(2);

  function bar(done, total) {
    const box = el("div", "orch-prog");
    const track = el("span", "orch-track");
    const fill = el("span", "orch-fill");
    fill.style.width = total ? Math.round((100 * done) / total) + "%" : "0%";
    track.append(fill);
    box.append(el("b", "small", done + " / " + total), track);
    return box;
  }

  /** counts: {key: {done, total}} read from each started run's progress. */
  function card(story, selected, counts, on) {
    const newest = story.runs[0];
    const node = el("div", "orch-story" + (selected ? " selected" : ""));
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    const word = runWord(newest.build_state);
    const head = el("div", "orch-story-head");
    const title = el("div", "orch-story-sum");
    title.append(icon("book"), el("span", "", story.key + ": " + (story.summary || "")));
    head.append(title);
    node.append(head);
    if (newest.build_state === "not_started") {
      const start = el("button", "btn btn-small btn-outline orch-start", "\u25B7 Start Story");
      start.type = "button";
      start.addEventListener("click", (event) => {
        event.stopPropagation();
        on.start(story.key);
      });
      node.append(start);
    } else {
      node.append(el("span", "orch-chip orch-" + word.kind, word.text));
      const c = counts[story.key];
      if (c) node.append(bar(c.done, c.total));
    }
    node.addEventListener("click", () => on.pick(story.key));
    node.addEventListener("keydown", (e) => e.key === "Enter" && on.pick(story.key));
    return node;
  }

  /** Fills `box`; `needle` filters by key or title. */
  function render(box, stories, selectedKey, counts, on, needle) {
    box.replaceChildren();
    const q = (needle || "").trim().toLowerCase();
    const shown = stories.filter((s) => s.runs.length && (s.key + " " + (s.summary || "")).toLowerCase().includes(q));
    if (!shown.length) {
      box.append(el("p", "empty", stories.length ? "No story matches." : "No approved story yet. Approve a plan in the Planning tab."));
      return;
    }
    for (const story of shown) box.append(card(story, story.key === selectedKey, counts, on));
  }

  return { render, money };
})();