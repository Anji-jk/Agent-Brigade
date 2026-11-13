"use strict";
/*
 * The Re-plan question: what should change. ask() resolves to the text (Re-plan) or to
 * undefined (Cancel, X, Esc or a click outside: nothing is re-planned). The text is required.
 */
window.Brigade = window.Brigade || {};

Brigade.replanPopup = (function () {
  const { el } = Brigade.dom;
  const GO = "go";
  const MAX = 4000;

  function ask(storyKey) {
    const body = el("div", "popup-body");
    const label = el("label", "pl-money-label", "What do you want to change in the plan for " + storyKey + "?");
    const box = el("textarea", "pl-textarea");
    box.rows = 5;
    box.maxLength = MAX;
    box.placeholder = "Write your own idea or what should change, for example: put the CSV button before the filter.";
    label.append(box);
    body.append(
      label,
      el("p", "muted small", "The Planner makes a new plan from your idea. The plan you are reading stays open until the new one is ready. Sub-tasks cannot be added or removed here: change those in Jira."),
    );
    const popup = Brigade.popup.open({
      title: "Re-plan this story",
      iconName: "refresh",
      body,
      buttons: [
        { label: "Re-plan", value: GO, kind: "primary", disabled: true },
        { label: "Cancel", value: undefined },
      ],
    });
    const valid = () => box.value.trim() !== "";
    box.addEventListener("input", () => {
      popup.button(GO).disabled = !valid();
    });
    box.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && valid()) popup.close(GO);
    });
    box.focus();
    return popup.closed.then((value) => (value === GO ? box.value.trim() : undefined));
  }

  return { ask };
})();
