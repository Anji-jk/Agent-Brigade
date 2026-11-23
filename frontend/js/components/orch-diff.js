"use strict";
/*
 * An Edit's before/after text as a red and green diff, like a code review. The feed sends the
 * text as "--- before ... +++ after ..." (one block per edit for MultiEdit). Line numbers count
 * from the start of the edit, because the call carries no position in the file.
 */
window.Brigade = window.Brigade || {};

Brigade.orchDiff = (function () {
  const { el } = Brigade.dom;
  const BLOCK = /^--- (?:edit \d+, )?before\n([\s\S]*?)\n\+\+\+ (?:edit \d+, )?after\n?([\s\S]*)$/;
  const GAP = /^\.\.\. \d+ (lines|characters) hidden \.\.\.$/;
  const MAX_CELLS = 1000000; // beyond this a line-by-line match is too slow: show plain before and after

  const lines = (text) => (text === "" ? [] : text.split("\n"));

  /** [{ old: [...], now: [...] }] for each edit, or null when the text is not an edit. */
  function parse(detail) {
    const blocks = String(detail || "").split(/\n\n(?=--- (?:edit \d+, )?before\n)/);
    const edits = [];
    for (const block of blocks) {
      const m = BLOCK.exec(block);
      if (!m) return null;
      edits.push({ old: lines(m[1]), now: lines(m[2]) });
    }
    return edits;
  }

  /** Rows of one edit: { op: "same" | "del" | "add" | "gap", text }. */
  function compare(old, now) {
    if (old.length * now.length > MAX_CELLS) {
      return [...old.map((text) => ({ op: "del", text })), ...now.map((text) => ({ op: "add", text }))];
    }
    const n = old.length;
    const m = now.length;
    const run = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1)); // run[i][j]: common lines of old[i:] and now[j:]
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        run[i][j] = old[i] === now[j] ? run[i + 1][j + 1] + 1 : Math.max(run[i + 1][j], run[i][j + 1]);
      }
    }
    const rows = [];
    let i = 0;
    let j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && old[i] === now[j]) rows.push({ op: GAP.test(old[i++]) ? "gap" : "same", text: now[j++] });
      else if (j < m && (i === n || run[i][j + 1] > run[i + 1][j])) rows.push({ op: "add", text: now[j++] });
      else rows.push({ op: "del", text: old[i++] });
    }
    return rows;
  }

  /** Marks the middle of a changed pair: the start and end the two lines share are left plain. */
  function pairs(rows) {
    for (let k = 0; k < rows.length; k++) {
      if (rows[k].op !== "del") continue;
      let d = k;
      while (rows[d] && rows[d].op === "del") d++;
      let a = d;
      while (rows[a] && rows[a].op === "add") a++;
      for (let x = 0; k + x < d && d + x < a; x++) mark(rows[k + x], rows[d + x]);
      k = a - 1;
    }
  }

  function mark(del, add) {
    const a = del.text;
    const b = add.text;
    let head = 0;
    while (head < a.length && head < b.length && a[head] === b[head]) head++;
    let tail = 0;
    while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
    del.cut = [head, a.length - tail];
    add.cut = [head, b.length - tail];
  }

  function line(row, number) {
    if (GAP.test(row.text)) row = { op: "gap", text: row.text }; // a cut-out stretch is a note, not a change
    const sign = { del: "−", add: "+", same: "", gap: "" }[row.op];
    const node = el("div", "orch-dl orch-dl-" + row.op);
    const code = el("span", "orch-dl-code");
    if (row.cut && row.cut[1] > row.cut[0]) {
      code.append(row.text.slice(0, row.cut[0]), el("mark", "", row.text.slice(row.cut[0], row.cut[1])), row.text.slice(row.cut[1]));
    } else code.textContent = row.text === "" ? " " : row.text;
    node.append(el("span", "orch-dl-n", row.op === "gap" ? "" : String(number)), el("span", "orch-dl-s", sign), code);
    return node;
  }

  /** render(detail) -> { node, added, removed }, or null when `detail` is not a before/after text. */
  function render(detail) {
    const edits = parse(detail);
    if (!edits) return null;
    const node = el("div", "orch-diff");
    let added = 0;
    let removed = 0;
    edits.forEach((edit, index) => {
      const rows = compare(edit.old, edit.now);
      pairs(rows);
      if (edits.length > 1) node.append(el("div", "orch-dl-hunk", "Edit " + (index + 1) + " of " + edits.length));
      let was = 0;
      let is = 0;
      for (const row of rows) {
        if (row.op !== "add") was++;
        if (row.op !== "del") is++;
        const real = !GAP.test(row.text);
        if (row.op === "add" && real) added++;
        if (row.op === "del" && real) removed++;
        node.append(line(row, row.op === "del" ? was : is));
      }
    });
    return { node, added, removed };
  }

  return { render, parse, compare };
})();