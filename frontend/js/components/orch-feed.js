"use strict";
/*
 * The live event feed of one agent. Items are kept by their index. A running tool call is
 * "pending" and gets its result later, so the next read starts at the first pending item and
 * redraws it; everything before is final and is not fetched again.
 */
window.Brigade = window.Brigade || {};

Brigade.orchFeed = (function () {
  const { el, when } = Brigade.dom;

  const isMarkdownFile = (item) => item.tool === "Write" && /\.(md|markdown)\b/i.test(item.title || "");

  /** The words under "Details": a diff for an edit, a formatted page for a markdown file, else plain text. */
  function view(item, head) {
    const result = item.result && (item.result.summary || item.result.detail);
    const plain = (text) => el("pre", "", text);
    const edit = item.tool === "Edit" || item.tool === "MultiEdit" ? Brigade.orchDiff.render(item.detail) : null;
    if (edit) {
      const change = el("span", "orch-ev-stat");
      change.append(el("b", "orch-plus", "+" + edit.added), " ", el("b", "orch-minus", "\u2212" + edit.removed));
      head.children[2].append(" ", change); // beside the file name
      return [edit.node, ...(result ? [plain(result)] : [])];
    }
    if (isMarkdownFile(item) && item.detail) {
      const page = el("div", "orch-md-box");
      const raw = plain(item.detail);
      const show = (formatted) => {
        page.replaceChildren(formatted ? Brigade.orchMarkdown.render(item.detail) : raw);
        for (const b of switcher.children) b.classList.toggle("on", (b.dataset.mode === "page") === formatted);
      };
      const switcher = el("div", "orch-md-switch");
      for (const [mode, label] of [["page", "Preview"], ["raw", "Raw"]]) {
        const button = el("button", "", label);
        button.type = "button";
        button.dataset.mode = mode;
        button.addEventListener("click", () => show(mode === "page"));
        switcher.append(button);
      }
      show(true);
      return [switcher, page, ...(result ? [plain(result)] : [])];
    }
    const parts = [item.detail, result].filter(Boolean);
    return parts.length ? [plain(parts.join("\n\n"))] : null;
  }

  function row(item) {
    const node = el("div", "orch-ev orch-ev-" + item.kind + (item.status ? " st-" + item.status : ""));
    const head = el("div", "orch-ev-head");
    const clock = item.at ? new Date(item.at).toLocaleTimeString([], { hour12: false }) : "";
    head.append(el("span", "orch-ev-at", clock), el("span", "orch-ev-kind orch-k-" + item.kind, item.tool || item.kind), el("span", "orch-ev-title", item.title));
    const done = item.result && item.result.status;
    if (item.pending) head.append(el("span", "orch-chip orch-busy", "running"));
    else if (done) head.append(el("span", "orch-chip " + (done === "error" ? "orch-bad" : "orch-ok"), done === "error" ? "error" : "ok"));
    node.append(head);
    const body = view(item, head);
    if (body) {
      const more = el("details", "orch-ev-more");
      more.append(el("summary", "", item.truncated ? "Details (shortened)" : "Details"), ...body);
      node.append(more);
    }
    return node;
  }

  /** feed(box, follow) -> { reset(), apply(answer), after(), count() } */
  function create(box, follow) {
    let items = new Map();
    let shown = new Map(); // index -> { node, sig }: the row on the page and what it was drawn from
    let next = 0;

    // What a row shows; a row is redrawn only when this changes.
    const signature = (i) => JSON.stringify([i.pending, i.status, i.title, i.detail, i.truncated, i.result]);

    // A row the reader has opened stays open when it is drawn again.
    function rowFor(item, old) {
      const node = row(item);
      const was = old && old.node.querySelector("details");
      const now = node.querySelector("details");
      if (was && now && was.open) now.open = true;
      return node;
    }

    let drawn = 0; // how many items the last draw showed

    function draw() {
      // Follow only scrolls when new items arrived and the reader was already at the bottom,
      // so a redraw never moves someone who scrolled up or opened a detail to read it.
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
      const stick = follow() && items.size > drawn && (atBottom || drawn === 0);
      const top = box.scrollTop;
      drawn = items.size;
      const kept = new Map();
      const nodes = [...items.keys()]
        .sort((a, b) => a - b)
        .map((k) => {
          const item = items.get(k);
          const sig = signature(item);
          const old = shown.get(k);
          const entry = old && old.sig === sig ? old : { node: rowFor(item, old), sig };
          kept.set(k, entry);
          return entry.node;
        });
      shown = kept;
      box.replaceChildren(...nodes);
      if (!items.size) box.append(el("p", "muted small", "Nothing yet."));
      box.scrollTop = stick ? box.scrollHeight : top;
    }

    return {
      reset() {
        items = new Map();
        shown = new Map();
        next = 0;
        drawn = 0;
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