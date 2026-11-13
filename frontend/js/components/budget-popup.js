"use strict";
/*
 * The optional budget asked before a story is planned. ask() resolves to a number (OK),
 * null (Skip and continue: plan without a budget) or undefined (dismissed: do not plan).
 */
window.Brigade = window.Brigade || {};

Brigade.budgetPopup = (function () {
  const { el } = Brigade.dom;
  const OK = "ok";

  function ask(storyKey) {
    const body = el("div", "popup-body");
    body.append(
      el("p", "", "Optional. The most this whole story may cost, planning and building together."),
    );
    const label = el("label", "pl-money-label", "Budget for " + storyKey + " (US dollars)");
    const field = el("span", "pl-money");
    const input = el("input");
    input.type = "number";
    input.min = "0.01";
    input.step = "0.01";
    input.inputMode = "decimal";
    input.placeholder = "for example 12";
    field.append(el("span", "pl-money-sign", "$"), input);
    label.append(field);
    body.append(
      label,
      el("p", "muted small", "Planning itself can never use more than this. To plan without a budget, choose Skip and continue."),
    );

    const popup = Brigade.popup.open({
      title: "Set a budget for this story?",
      iconName: "coin",
      body,
      buttons: [
        { label: "OK", value: OK, kind: "primary", disabled: true },
        { label: "Skip and continue", value: null },
      ],
    });
    const amount = () => Number(input.value);
    const valid = () => input.value.trim() !== "" && Number.isFinite(amount()) && amount() > 0;
    input.addEventListener("input", () => {
      popup.button(OK).disabled = !valid();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && valid()) popup.close(OK);
    });
    input.focus();
    return popup.closed.then((value) => (value === OK ? amount() : value));
  }

  return { ask };
})();