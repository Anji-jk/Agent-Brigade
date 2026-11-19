"use strict";
/*
 * "← Older  Runs 1-12 of 30, newest first  Newer →": the page buttons under the Overview's chart
 * and table, the same pager as the Agent Lab dashboard. Page 0 is the newest. The chart reads
 * oldest-left, so there Older is on the left; the table reads newest-top, so there Older is on the
 * right. Nothing is drawn when there is only one page. A button that disables itself under the
 * pointer hands the focus to its partner, so the keyboard is not lost.
 */
window.Brigade = window.Brigade || {};

Brigade.overviewPager = (function () {
  const { el } = Brigade.dom;

  /** `info` is the server's page: { total, page, pages, size, items }. */
  const label = (info) => {
    const first = info.page * info.size + 1;
    return "Runs " + first + "–" + (first + info.items.length - 1) + " of " + info.total + ", newest first · page " + (info.page + 1) + " of " + info.pages;
  };

  function render(host, info, olderOnRight, go) {
    if (info.pages < 2) {
      host.replaceChildren();
      return;
    }
    const older = el("button", "orch-view", olderOnRight ? "Older →" : "← Older");
    const newer = el("button", "orch-view", olderOnRight ? "← Newer" : "Newer →");
    for (const button of [older, newer]) button.type = "button";
    older.disabled = info.page >= info.pages - 1;
    newer.disabled = info.page === 0;
    older.addEventListener("click", () => go(info.page + 1, older.disabled ? null : "older"));
    newer.addEventListener("click", () => go(info.page - 1, newer.disabled ? null : "newer"));
    older.dataset.key = "older";
    newer.dataset.key = "newer";
    const text = el("span", "muted small", label(info));
    host.replaceChildren(...(olderOnRight ? [newer, text, older] : [older, text, newer]));
  }

  /** After a click and a repaint: keep the focus on the same button, or move it to the other. */
  function refocus(host, key) {
    const same = host.querySelector('[data-key="' + key + '"]');
    const other = host.querySelector('[data-key="' + (key === "older" ? "newer" : "older") + '"]');
    (same && !same.disabled ? same : other)?.focus();
  }

  return { render, refocus, label };
})();