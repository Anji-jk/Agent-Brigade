"use strict";
/* The left pane (the project and its epics) and the header of the chosen epic. */
window.Brigade = window.Brigade || {};

Brigade.epicList = (function () {
  const { el, icon } = Brigade.dom;
  const plural = (count, word) => count + " " + word + (count === 1 ? "" : "s");

  function epicButton(epic, current, onPick) {
    const node = el("button", "pl-epic" + (epic.key === current ? " current" : ""));
    node.type = "button";
    const mark = el("span", "pl-mark purple");
    mark.append(icon("bolt"));
    const text = el("span", "pl-epic-text");
    text.append(el("b", "", epic.key ? epic.key + ": " + epic.summary : epic.summary));
    node.append(mark, text, el("span", "pl-count", epic.stories.length + (epic.stories.length === 1 ? " Story" : " Stories")));
    node.addEventListener("click", () => onPick(epic.key));
    return node;
  }

  /** The slim strip that stays when the pane is collapsed. */
  function rail(onToggle) {
    const button = el("button", "rail-btn pl-rail");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Show JIRA Projects");
    const chevron = el("span", "pl-rail-chevron");
    chevron.append(icon("chevron"));
    button.append(chevron, el("span", "rail-label", "JIRA Projects"));
    button.addEventListener("click", onToggle);
    return button;
  }

  /** The pane: "JIRA Projects" with the space, then "Epics (n)". `fold` = { collapsed, onToggle }. */
  function render(space, epics, current, onPick, fold) {
    if (fold.collapsed) return rail(fold.onToggle);
    const pane = el("div", "pl-left-inner");
    const head = el("div", "pl-left-head");
    const board = el("span", "pl-mark blue");
    board.append(icon("diamond"));
    const hide = el("button", "icon-btn small pl-fold");
    hide.type = "button";
    hide.setAttribute("aria-expanded", "true");
    hide.setAttribute("aria-label", "Hide JIRA Projects");
    hide.append(icon("chevron"));
    hide.addEventListener("click", fold.onToggle);
    head.append(board, el("b", "pl-left-title", "JIRA Projects"), hide);
    const project = el("div", "pl-project");
    project.append(icon("folder"), el("b", "", space), el("span", "pl-count", plural(epics.length, "Epic")));
    pane.append(head, project, el("h3", "pl-subhead", "Epics (" + epics.length + ")"));
    for (const epic of epics) pane.append(epicButton(epic, current, onPick));
    return pane;
  }

  /** Title, status and the two counts of the chosen epic. */
  function header(epic) {
    const box = el("section", "pl-epic-head");
    const mark = el("span", "pl-mark purple big");
    mark.append(icon("bolt"));
    const title = el("div", "pl-epic-title");
    title.append(el("h2", "", epic.key ? epic.key + ": " + epic.summary : epic.summary));
    const counts = el("div", "pl-chips");
    const subtasks = epic.stories.reduce((n, s) => n + s.subtasks.length, 0);
    for (const text of ["Stories: " + epic.stories.length, "Subtasks: " + subtasks]) {
      counts.append(el("span", "pl-chip idle", text));
    }
    title.append(counts);
    box.append(mark, title);
    if (epic.status) box.append(el("span", "pl-count", epic.status));
    return box;
  }

  return { render, header };
})();