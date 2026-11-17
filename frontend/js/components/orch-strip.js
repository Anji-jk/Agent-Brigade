"use strict";
/* The pipeline strip: Plan, then the run's sub-tasks in plan order, each with its word and what it waits for. */
window.Brigade = window.Brigade || {};

Brigade.orchStrip = (function () {
  const { el } = Brigade.dom;
  const { taskWord, after } = Brigade.orchModel;

  function node(key, word, kind, caption, selected, onPick, title) {
    const box = el(onPick ? "button" : "div", "orch-node orch-" + kind + (selected ? " selected" : ""));
    if (onPick) {
      box.type = "button";
      box.setAttribute("aria-pressed", String(selected));
      box.addEventListener("click", onPick);
    }
    box.title = title || key;
    const head = el("div", "orch-node-head");
    head.append(el("span", "orch-dot"), el("b", "", key));
    box.append(head, el("span", "orch-node-word", word));
    if (caption) box.append(el("span", "muted small", caption));
    return box;
  }

  function render(box, tasks, selectedKey, onPick) {
    box.replaceChildren(node("Plan", "planner succeeded", "ok", "", false, null, "The approved plan"));
    for (const task of tasks) {
      const word = taskWord(task);
      box.append(
        el("span", "orch-link"),
        node(task.key, word.text, word.kind, after(task), task.key === selectedKey, () => onPick(task.key), task.title),
      );
    }
  }

  return { render };
})();