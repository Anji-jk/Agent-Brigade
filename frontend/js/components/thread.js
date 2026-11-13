"use strict";
/*
 * The conversation on the page: the user's and the Publisher's bubbles, notices, the working
 * indicator and a plan inside a bubble. It draws; the Publisher tab decides what to draw.
 */
window.Brigade = window.Brigade || {};

Brigade.thread = (function () {
  const { $, el, icon, when } = Brigade.dom;
  const context = { initials: "?", jiraSite: "" };

  function setContext(initials, jiraSite) {
    context.initials = initials || "?";
    context.jiraSite = jiraSite || "";
  }

  function scrollDown() {
    const thread = $("thread");
    thread.scrollTop = thread.scrollHeight;
  }

  function clearThread() {
    $("thread").replaceChildren($("thread-empty") || el("p"));
    $("thread-empty").hidden = false;
  }

  function add(node) {
    $("thread-empty").hidden = true;
    $("thread").append(node);
    scrollDown();
    return node;
  }

  function fileChip(file) {
    const chip = el(file.url ? "a" : "span", "file-chip");
    chip.append(icon("file"), file.name);
    if (file.url) {
      chip.href = file.url;
      chip.download = file.name;
      chip.title = "Download " + file.name;
    }
    return chip;
  }

  function userBubble(text, files, timestamp) {
    const row = el("div", "msg msg-user");
    const bubble = el("div", "bubble");
    if (text) bubble.append(el("div", "text", text));
    if (files && files.length) {
      const chips = el("div", "chips");
      files.forEach((f) => chips.append(fileChip(f)));
      bubble.append(chips);
    }
    bubble.append(el("div", "time", when(timestamp)));
    row.append(bubble, el("span", "avatar small", context.initials));
    return add(row);
  }

  function publisherBubble(text, timestamp) {
    const row = el("div", "msg msg-publisher");
    const avatar = el("span", "bot");
    avatar.append(icon("bot"));
    const bubble = el("div", "bubble");
    if (text) bubble.append(Brigade.markdown.render(text));
    const time = el("div", "time", when(timestamp));
    bubble.append(time);
    row.append(avatar, bubble);
    add(row);
    return { bubble, time };
  }

  function notice(bubble, kind, lines, before) {
    const box = el("div", "status status-" + kind);
    box.append(icon(kind === "ok" ? "check" : "x"));
    const body = el("div");
    lines.forEach((line) => body.append(typeof line === "string" ? el("div", "", line) : line));
    box.append(body);
    bubble.insertBefore(box, before || null);
    return box;
  }

  function createdLinks(created) {
    const line = el("div");
    line.append("Created in Jira: ");
    created.forEach((item, n) => {
      if (n) line.append(", ");
      const link = el("a", "", item.key);
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener";
      line.append(link);
    });
    return line;
  }

  function linkItem(key) {
    return { key, url: context.jiraSite ? context.jiraSite + "/browse/" + key : "#" };
  }

  /** A plan inside a Publisher bubble, with Confirm while it is the open proposal. */
  function showPlan(bubble, time, plan, options, onConfirm) {
    const tree = Brigade.planTree.render(plan, options.keys || null, context.jiraSite);
    bubble.insertBefore(tree, time);
    if (options.keys) {
      notice(bubble, "ok", [createdLinks(options.keys.map((key) => linkItem(key)))], time);
      return;
    }
    if (!options.open) return;
    const bar = el("div", "confirm-bar");
    const button = el("button", "confirm", "Confirm and create in Jira");
    button.type = "button";
    bar.append(el("span", "muted", Brigade.planTree.counts(plan)), button);
    bubble.insertBefore(bar, time);
    button.addEventListener("click", () => onConfirm(bubble, time, plan, bar, tree));
  }

  function working() {
    const row = el("div", "msg msg-publisher working");
    const avatar = el("span", "bot");
    avatar.append(icon("bot"));
    const bubble = el("div", "bubble");
    bubble.append(el("span", "dots"), el("span", "muted", "Publisher is working. This usually takes 20 to 60 seconds."));
    row.append(avatar, bubble);
    return add(row);
  }

  /** Draw a saved chat again: its messages, then each plan with what Confirm created. */
  function replay(chat, onConfirm) {
    clearThread();
    const records = chat.records.map((r) => ({ sig: Brigade.planTree.signature(r.plan), record: r }));
    const used = new Set();
    const openSig = chat.proposal ? Brigade.planTree.signature(chat.proposal) : null;
    let lastPlanBubble = null;

    for (const bubble of chat.bubbles) {
      if (bubble.role === "user") {
        userBubble(bubble.text, bubble.files, bubble.timestamp);
        continue;
      }
      const shown = publisherBubble(bubble.text, bubble.timestamp);
      if (!bubble.plan) continue;
      const sig = Brigade.planTree.signature(bubble.plan);
      const match = records.find((r) => r.sig === sig && !used.has(r.record.record_id));
      if (match) {
        used.add(match.record.record_id);
        showPlan(shown.bubble, shown.time, match.record.plan, { keys: match.record.created_keys }, onConfirm);
      } else {
        lastPlanBubble = { shown, plan: bubble.plan, sig };
      }
    }
    if (lastPlanBubble) {
      const { shown, plan, sig } = lastPlanBubble;
      showPlan(shown.bubble, shown.time, plan, { open: sig === openSig }, onConfirm);
    }
    if (!chat.transcript_available) {
      const { bubble, time } = publisherBubble(
        "Claude Code has removed this conversation's messages (it keeps them for 30 days by default). What was created is kept by Brigade:",
      );
      for (const record of chat.records) {
        showPlan(bubble, time, record.plan, { keys: record.created_keys }, onConfirm);
      }
      if (chat.files.length) {
        const chips = el("div", "chips");
        chat.files.forEach((f) => chips.append(fileChip(f)));
        bubble.insertBefore(chips, time);
      }
    } else {
      for (const record of records) {
        if (!used.has(record.record.record_id)) {
          const { bubble, time } = publisherBubble("Created after Confirm:", record.record.confirmed_at);
          showPlan(bubble, time, record.record.plan, { keys: record.record.created_keys }, onConfirm);
        }
      }
    }
  }

  return {
    setContext,
    clearThread,
    scrollDown,
    userBubble,
    publisherBubble,
    notice,
    createdLinks,
    showPlan,
    working,
    fileChip,
    replay,
  };
})();
