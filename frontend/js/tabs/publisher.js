"use strict";
/*
 * The Publisher tab: the chat, the plan tree with Confirm, file uploads and Previous Chats.
 * Talks to /api/publisher (backend/api/publisher.py). An agent turn takes 20 to 60 seconds, so
 * the page shows a working indicator and refuses a second message until the answer is in.
 */
window.Brigade = window.Brigade || {};

Brigade.publisher = (function () {
  const API = "/api/publisher/sessions";
  const ACCEPT = [".txt", ".md", ".docx", ".pdf"];
  const MAX_FILES = 5;
  const MAX_BYTES = 10 * 1024 * 1024;

  const state = {
    chatId: null,
    displayId: null,
    busy: false,
    files: [], // File objects waiting to be sent
    initials: "?",
    jiraSite: "",
  };

  const $ = (id) => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const icon = (name) => Brigade.planTree.icon(name);

  function when(timestamp) {
    const date = timestamp ? new Date(timestamp) : new Date();
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  async function api(method, url, body) {
    const response = await fetch(url, { method, body });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
      throw new Error(detail || "The server answered HTTP " + response.status + ".");
    }
    return data;
  }

  // ---------- thread ----------

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
    row.append(bubble, el("span", "avatar small", state.initials));
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

  /** A plan inside a Publisher bubble, with Confirm while it is the open proposal. */
  function showPlan(bubble, time, plan, options) {
    const tree = Brigade.planTree.render(plan, options.keys || null, state.jiraSite);
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
    button.addEventListener("click", () => confirm(bubble, time, plan, bar, tree));
  }

  function linkItem(key) {
    return { key, url: state.jiraSite ? state.jiraSite + "/browse/" + key : "#" };
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

  // ---------- sending ----------

  function setBusy(busy) {
    state.busy = busy;
    $("send").disabled = busy;
    $("attach").disabled = busy;
    $("message").disabled = busy;
    for (const button of document.querySelectorAll(".confirm")) button.disabled = busy;
  }

  function setChat(chatId, displayId) {
    state.chatId = chatId;
    state.displayId = displayId;
    $("chat-id").textContent = displayId || "new chat";
    $("copy-chat-id").disabled = !displayId;
  }

  function withdrawProposals() {
    for (const bar of document.querySelectorAll(".confirm-bar")) {
      bar.replaceChildren(el("span", "muted", "Withdrawn: a new message was sent after this proposal."));
    }
  }

  async function send(event) {
    event.preventDefault();
    if (state.busy) return;
    const text = $("message").value.trim();
    const files = state.files.slice();
    if (!text && !files.length) return;

    const form = new FormData();
    form.append("text", text);
    files.forEach((file) => form.append("files", file));
    const url = state.chatId ? API + "/" + state.chatId + "/messages" : API;

    withdrawProposals();
    userBubble(text, files.map((f) => ({ name: f.name })));
    $("message").value = "";
    autoGrow();
    state.files = [];
    renderAttached();
    const indicator = working();
    setBusy(true);
    try {
      const turn = await api("POST", url, form);
      indicator.remove();
      setChat(turn.chat_id, turn.display_id);
      const { bubble, time } = publisherBubble(turn.reply);
      if (turn.plan) showPlan(bubble, time, turn.plan, { open: true });
      if (turn.problems && turn.problems.length) {
        notice(bubble, "error", ["This plan cannot be confirmed:", ...turn.problems], time);
      }
      loadChats();
    } catch (error) {
      indicator.remove();
      const { bubble, time } = publisherBubble("");
      notice(bubble, "error", [error.message], time);
    } finally {
      setBusy(false);
      scrollDown();
      $("message").focus();
    }
  }

  async function confirm(bubble, time, plan, bar, tree) {
    if (state.busy) return;
    setBusy(true);
    bar.replaceChildren(el("span", "dots"), el("span", "muted", "Creating in Jira..."));
    try {
      const result = await api("POST", API + "/" + state.chatId + "/confirm");
      bar.remove();
      if (result.created.length) {
        const keys = result.created.map((c) => c.key);
        tree.replaceWith(Brigade.planTree.render(plan, keys, state.jiraSite));
        notice(bubble, result.ok ? "ok" : "error", [createdLinks(result.created)], time);
      }
      if (result.error) notice(bubble, "error", [result.error], time);
      if (result.mismatches.length) notice(bubble, "error", result.mismatches, time);
      loadChats();
    } catch (error) {
      bar.replaceChildren(el("span", "muted", error.message));
    } finally {
      setBusy(false);
    }
  }

  // ---------- files ----------

  function renderAttached() {
    const box = $("attached");
    box.replaceChildren();
    state.files.forEach((file, n) => {
      const chip = fileChip({ name: file.name });
      const remove = el("button", "chip-remove");
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove " + file.name);
      remove.append(icon("x"));
      remove.addEventListener("click", () => {
        state.files.splice(n, 1);
        renderAttached();
      });
      chip.append(remove);
      box.append(chip);
    });
    box.hidden = state.files.length === 0;
  }

  function pickFiles(event) {
    const problems = [];
    for (const file of event.target.files) {
      const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPT.includes(suffix)) problems.push(file.name + ": only " + ACCEPT.join(", ") + " files.");
      else if (file.size > MAX_BYTES) problems.push(file.name + " is larger than 10 MB.");
      else if (state.files.length >= MAX_FILES) problems.push("At most " + MAX_FILES + " files per message.");
      else state.files.push(file);
    }
    event.target.value = "";
    renderAttached();
    if (problems.length) {
      const { bubble, time } = publisherBubble("");
      notice(bubble, "error", problems, time);
    }
  }

  // ---------- previous chats ----------

  async function loadChats() {
    let chats = [];
    try {
      chats = await api("GET", API);
    } catch (error) {
      return; // the project notice already says when the backend is unreachable
    }
    const list = $("chat-list");
    list.replaceChildren();
    for (const chat of chats) {
      const item = el("li");
      const button = el("button", "chat-item" + (chat.chat_id === state.chatId ? " current" : ""));
      button.type = "button";
      button.append(
        el("b", "", chat.display_id),
        el("span", "chat-title", chat.title || "Conversation removed by Claude Code"),
        el("span", "muted", when(chat.created_at) + (chat.created_keys.length ? " · " + chat.created_keys.length + " created" : "")),
      );
      button.addEventListener("click", () => openChat(chat.chat_id));
      item.append(button);
      list.append(item);
    }
    $("chat-list-empty").hidden = chats.length > 0;
  }

  async function openChat(chatId) {
    if (state.busy) return;
    let chat;
    try {
      chat = await api("GET", API + "/" + chatId);
    } catch (error) {
      const { bubble, time } = publisherBubble("");
      notice(bubble, "error", [error.message], time);
      return;
    }
    clearThread();
    setChat(chat.chat_id, chat.display_id);
    loadChats();

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
        showPlan(shown.bubble, shown.time, match.record.plan, { keys: match.record.created_keys });
      } else {
        lastPlanBubble = { shown, plan: bubble.plan, sig };
      }
    }
    if (lastPlanBubble) {
      const { shown, plan, sig } = lastPlanBubble;
      showPlan(shown.bubble, shown.time, plan, { open: sig === openSig });
    }
    if (!chat.transcript_available) {
      const { bubble, time } = publisherBubble(
        "Claude Code has removed this conversation's messages (it keeps them for 30 days by default). What was created is kept by Brigade:",
      );
      for (const record of chat.records) {
        showPlan(bubble, time, record.plan, { keys: record.created_keys });
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
          showPlan(bubble, time, record.record.plan, { keys: record.record.created_keys });
        }
      }
    }
    toggleDrawer(false);
  }

  function newChat() {
    if (state.busy) return;
    setChat(null, null);
    clearThread();
    loadChats();
    toggleDrawer(false);
    $("message").focus();
  }

  function toggleDrawer(open) {
    const drawer = $("chat-drawer");
    const show = typeof open === "boolean" ? open : drawer.hidden;
    drawer.hidden = !show;
    $("rail-toggle").setAttribute("aria-expanded", String(show));
    if (show) loadChats();
  }

  // ---------- composer ----------

  function autoGrow() {
    const box = $("message");
    box.style.height = "auto";
    box.style.height = Math.min(box.scrollHeight, 200) + "px";
  }

  function init(context) {
    state.initials = context.initials || "?";
    state.jiraSite = context.jiraSite || "";
    $("composer").addEventListener("submit", send);
    $("message").addEventListener("input", autoGrow);
    $("message").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) send(event);
    });
    $("attach").addEventListener("click", () => $("file-input").click());
    $("file-input").addEventListener("change", pickFiles);
    $("rail-toggle").addEventListener("click", () => toggleDrawer());
    $("new-chat").addEventListener("click", newChat);
    $("copy-chat-id").addEventListener("click", () => {
      if (state.displayId && navigator.clipboard) navigator.clipboard.writeText(state.displayId);
    });
    loadChats();
  }

  return { init };
})();
