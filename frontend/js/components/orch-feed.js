"use strict";
/*
 * The live event feed of one agent. Items are kept by their index. A running tool call is
 * "pending" and gets its result later, so the next read starts at the first pending item and
 * redraws it; everything before is final and is not fetched again.
 */
window.Brigade = window.Brigade || {};

Brigade.orchFeed = (function () {
  const { el, when } = Brigade.dom;

  function row(item) {
    const node = el("div", "orch-ev orch-ev-" + item.kind + (item.status ? " st-" + item.status : ""));
    const head = el("div", "orch-ev-head");
    const clock = item.at ? new Date(item.at).toLocaleTimeString([], { hour12: false }) : "";
    head.append(el("span", "orch-ev-at", clock), el("span", "orch-ev-kind orch-k-" + item.kind, item.tool || item.kind), el("span", "orch-ev-title", item.title));
    const done = item.result && item.result.status;
    if (item.pending) head.append(el("span", "orch-chip orch-busy", "running"));
    else if (done) head.append(el("span", "orch-chip " + (done === "error" ? "orch-bad" : "orch-ok"), done === "error" ? "error" : "ok"));
    node.append(head);
    const parts = [item.detail, item.result && (item.result.summary || item.result.detail)].filter(Boolean);
    if (parts.length) {
      const more = el("details", "orch-ev-more");
      more.append(el("summary", "", item.truncated ? "Details (shortened)" : "Details"), el("pre", "", parts.join("\n\n")));
      node.append(more);
    }
    return node;
  }

  /** feed(box, follow) -> { reset(), apply(answer), after(), count() } */
  function create(box, follow) {
    let items = new Map();
    let next = 0;

    function draw() {
      const stick = follow();
      box.replaceChildren(...[...items.keys()].sort((a, b) => a - b).map((k) => row(items.get(k))));
      if (!items.size) box.append(el("p", "muted small", "Nothing yet."));
      if (stick) box.scrollTop = box.scrollHeight;
    }

    return {
      reset() {
        items = new Map();
        next = 0;
        draw();
      },
      after() {
        const pending = [...items.values()].filter((i) => i.pending).map((i) => i.index);
        return pending.length ? Math.min(...pending) : next;
      },
      apply(answer) {
        for (const item of answer.items) items.set(item.index, item);
        next = Math.max(next, answer.next);
        draw();
      },
      count: () => items.size,
      redraw: draw,
    };
  }

  return { create };
})();