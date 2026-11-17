"use strict";
/* The task bar: the task's title and word, and Continue, Stop and Cancel Task with their reasons. */
window.Brigade = window.Brigade || {};

Brigade.orchTaskbar = (function () {
  const { el } = Brigade.dom;
  const { taskWord, rules } = Brigade.orchModel;

  function button(label, kind, reason, onClick) {
    const node = el("button", "btn btn-small " + kind, label);
    node.type = "button";
    node.disabled = reason !== null;
    if (reason !== null) node.title = reason;
    node.addEventListener("click", onClick);
    return node;
  }

  /** `act` is {continue, stop, cancel}: each takes no argument and does the call. */
  function render(box, task, buildState, act) {
    box.replaceChildren();
    const word = taskWord(task);
    const left = el("div", "orch-bar-title");
    left.append(el("b", "", "Task: " + task.key + " \u2013 " + (task.title || "")), el("span", "orch-chip orch-" + word.kind, word.text));
    const can = rules(task, buildState);
    const buttons = el("div", "orch-bar-actions");
    buttons.append(
      button("\u25B7 Continue Task", "btn-outline", can.continue, act.continue),
      button("\u275A\u275A Stop Task", "btn-outline", can.stop, act.stop),
      button("\u2715 Cancel Task", "btn-outline orch-danger", can.cancel, act.cancel),
    );
    box.append(left, buttons);
    const why = [can.continue && "Continue: " + can.continue, can.stop && "Stop: " + can.stop, can.cancel && "Cancel: " + can.cancel].filter(Boolean);
    if (why.length) box.append(el("p", "muted small orch-why", why.join("  ")));
  }

  return { render };
})();