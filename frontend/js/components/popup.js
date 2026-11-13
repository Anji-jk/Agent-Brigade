"use strict";
/*
 * A small dialog in the page's own look. open() returns { closed, close, button }:
 * `closed` resolves to the `value` of the button that was pressed, or to undefined when the
 * dialog was dismissed (X, Esc or a click outside), so a caller can tell "no" from "skip".
 */
window.Brigade = window.Brigade || {};

Brigade.popup = (function () {
  const { el, icon } = Brigade.dom;

  function open({ title, iconName, body, buttons }) {
    const dialog = el("dialog", "popup");
    const head = el("header", "popup-head");
    const badge = el("span", "popup-icon");
    badge.append(icon(iconName || "sparkle"));
    const close = el("button", "icon-btn small popup-x");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    close.append(icon("x"));
    head.append(badge, el("h2", "", title), close);

    const foot = el("footer", "popup-foot");
    const made = new Map();
    for (const spec of buttons) {
      const button = el("button", "btn " + (spec.kind === "primary" ? "btn-gold" : "btn-outline"), spec.label);
      button.type = "button";
      button.disabled = Boolean(spec.disabled);
      button.addEventListener("click", () => finish(spec.value));
      made.set(spec.value, button);
      foot.append(button);
    }
    dialog.append(head, body, foot);

    let settle;
    const closed = new Promise((resolve) => (settle = resolve));
    function finish(value) {
      if (dialog.open) dialog.close();
      dialog.remove();
      settle(value);
    }
    close.addEventListener("click", () => finish(undefined));
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault(); // Esc: close it ourselves so the answer is "dismissed"
      finish(undefined);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) finish(undefined); // a click on the dimmed area
    });
    document.body.append(dialog);
    dialog.showModal();
    return { closed, close: finish, button: (value) => made.get(value) };
  }

  return { open };
})();