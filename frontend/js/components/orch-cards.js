"use strict";
/* The Overview's top cards and the slim row of facts under them. */
window.Brigade = window.Brigade || {};

Brigade.overviewCards = (function () {
  const { el, icon } = Brigade.dom;
  const model = Brigade.overviewModel;

  function card(one) {
    const box = el("div", "ov-card");
    const head = el("div", "ov-card-head");
    head.append(icon(one.icon), el("span", "muted small", one.title));
    box.append(head, el("b", "ov-value", one.value), el("span", "muted small", one.sub));
    if (one.note) box.append(el("span", "ov-note", one.note));
    return box;
  }

  function render(cardsBox, factsBox, data) {
    cardsBox.replaceChildren(...model.cards(data).map(card));
    factsBox.replaceChildren(
      ...model.facts(data).map(([name, text]) => {
        const item = el("span", "ov-fact");
        item.append(el("b", "", name + ": "), document.createTextNode(text));
        return item;
      }),
    );
  }

  return { render };
})();