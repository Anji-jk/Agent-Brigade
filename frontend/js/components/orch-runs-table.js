"use strict";
/* The Overview's table of recent runs: what a chart cannot show (state, tasks n / m, attempts). */
window.Brigade = window.Brigade || {};

Brigade.overviewTable = (function () {
  const { el, when } = Brigade.dom;
  const model = Brigade.overviewModel;
  const HEAD = ["Story", "Run", "State", "Tasks", "Attempts", "Tokens in / out", "Cost", "Time", "Started"];

  function row(one, onPick) {
    const tr = el("tr", "ov-row");
    const word = model.stateWord(one.state);
    const state = el("span", "orch-chip orch-" + word.kind, word.text);
    const story = el("td");
    story.append(el("b", "", one.story_key), el("span", "muted small", " " + (one.title || "")));
    const link = el("button", "link-btn", model.tail(one.run_id));
    link.type = "button";
    link.title = "Open " + one.run_id + " in Stories";
    link.addEventListener("click", () => onPick(one));
    const run = el("td");
    run.append(link);
    const status = el("td");
    status.append(state);
    tr.append(
      story,
      run,
      status,
      el("td", "", one.tasks_merged + " / " + one.tasks_planned),
      el("td", "", String(one.attempts)),
      el("td", "", model.num(one.input_tokens) + " / " + model.num(one.output_tokens)),
      el("td", "", model.money(one.cost)),
      el("td", "", model.duration(one.wall_clock_seconds)),
      el("td", "muted", when(one.started_at)),
    );
    return tr;
  }

  function render(box, rows, onPick) {
    if (!rows.length) {
      box.replaceChildren(el("p", "empty", "No runs yet."));
      return;
    }
    const table = el("table", "ov-table");
    const head = el("tr");
    head.append(...HEAD.map((name) => el("th", "", name)));
    const thead = el("thead");
    thead.append(head);
    const body = el("tbody");
    body.append(...rows.map((one) => row(one, onPick)));
    table.append(thead, body);
    box.replaceChildren(table);
  }

  return { render };
})();