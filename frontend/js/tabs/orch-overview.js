"use strict";
/* The Orchestrator tab, Overview view: what every run of the project adds up to, from the database. */
window.Brigade = window.Brigade || {};

Brigade.orchOverview = (function () {
  const { $, el } = Brigade.dom;
  const TICK = 5000;
  const CHART_PAGE = 12, TABLE_PAGE = 10; // runs per page; the chart and the table each have their own page
  const MODES = [["both", "Both"], ["tokens", "Tokens"], ["cost", "Cost"]];
  const s = { data: null, chart: null, table: null, chartPage: 0, tablePage: 0, mode: "both" };
  let parts = {}, busy = false;

  const visible = () => Brigade.orchViews.current() === "overview" && !$("orchestrator").hidden && !document.hidden;

  function say(text) {
    parts.notice.textContent = text || "";
    parts.notice.hidden = !text;
  }

  function open(row) {
    Brigade.orchViews.show("stories");
    Brigade.orchestrator.openRun(row.story_key, row.run_id);
  }

  function paint() {
    if (!s.data) return;
    Brigade.overviewCards.render(parts.cards, parts.facts, s.data);
    drawChart();
    drawTable();
    for (const [mode, button] of Object.entries(parts.modes)) {
      button.classList.toggle("selected", mode === s.mode);
      button.setAttribute("aria-pressed", String(mode === s.mode));
    }
  }

  function drawChart() {
    if (!s.chart) return;
    Brigade.overviewChart.render(parts.chart, Brigade.overviewModel.chartRows(s.chart.items), s.mode, open);
    Brigade.overviewPager.render(parts.chartPager, s.chart, false, (page, key) => go("chart", page, key));
  }

  function drawTable() {
    if (!s.table) return;
    Brigade.overviewTable.render(parts.table, s.table.items, open);
    Brigade.overviewPager.render(parts.tablePager, s.table, true, (page, key) => go("table", page, key));
  }

  /** Turn one page (the chart's or the table's): ask the server for it, repaint only that part. */
  async function go(which, page, key) {
    s[which + "Page"] = page;
    await read();
    if (key) Brigade.overviewPager.refocus(which === "chart" ? parts.chartPager : parts.tablePager, key);
  }

  async function read() {
    if (busy) return;
    busy = true;
    try {
      const [data, chart, table] = await Promise.all([
        Brigade.orchApi.overview(),
        Brigade.orchApi.overviewRuns(s.chartPage, CHART_PAGE),
        Brigade.orchApi.overviewRuns(s.tablePage, TABLE_PAGE),
      ]);
      Object.assign(s, { data, chart, table, chartPage: chart.page, tablePage: table.page }); // the server fixes a page past the end
      say("");
      paint();
      $("orch-updated").textContent = "Last updated " + new Date().toLocaleTimeString();
    } catch (error) {
      say(error.message); // the old numbers stay on the page
    } finally {
      busy = false;
    }
  }

  function toolbar() {
    const bar = el("div", "ov-toolbar");
    const group = el("div", "ov-modes");
    parts.modes = {};
    for (const [mode, text] of MODES) {
      const button = el("button", "orch-view", text);
      button.type = "button";
      button.addEventListener("click", () => ((s.mode = mode), paint()));
      parts.modes[mode] = button;
      group.append(button);
    }
    bar.append(el("h2", "", "Token Cost by Run"), group);
    return bar;
  }

  function init() {
    const root = $("orch-overview");
    parts = { notice: el("p", "status status-error"), cards: el("div", "ov-cards"), facts: el("div", "ov-facts"), chart: el("div", "ov-chart"), chartPager: el("div", "ov-pager"), table: el("div", "ov-tablebox"), tablePager: el("div", "ov-pager") };
    parts.notice.hidden = true;
    const chartBox = el("section", "ov-panel");
    chartBox.append(toolbar(), parts.chart, parts.chartPager);
    const tableBox = el("section", "ov-panel");
    tableBox.append(el("h2", "", "Runs"), parts.table, parts.tablePager);
    root.append(parts.notice, parts.cards, parts.facts, chartBox, tableBox);
    $("orch-refresh").addEventListener("click", () => visible() && read());
    Brigade.orchViews.onChange((name) => name === "overview" && read());
    setInterval(() => visible() && read(), TICK);
    Brigade.orchViews.init();
  }

  return { init };
})();