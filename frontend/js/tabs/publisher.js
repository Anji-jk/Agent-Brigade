"use strict";
/*
 * The Publisher tab: sending a message, Confirm, and Previous Chats. The conversation itself is
 * drawn by components/thread.js and the attached documents by components/attachments.js.
 * Talks to /api/publisher (backend/api/publisher.py). An agent turn takes 20 to 60 seconds, so
 * the page shows a working indicator and refuses a second message until the answer is in.
 */
window.Brigade = window.Brigade || {};

Brigade.publisher = (function () {
  const API = "/api/publisher/sessions";
  const { $, el, when, api } = Brigade.dom;
  const thread = Brigade.thread;

  const state = {
    chatId: null,
    displayId: null,
    busy: false,
    jiraSite: "",
  };

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
    const files = Brigade.attachments.waiting();
    if (!text && !files.length) return;

    const form = new FormData();
    form.append("text", text);
    files.forEach((file) => form.append("files", file));
    const url = state.chatId ? API + "/" + state.chatId + "/messages" : API;

    withdrawProposals();
    thread.userBubble(text, files.map((f) => ({ name: f.name })));
    $("message").value = "";
    autoGrow();
    Brigade.attachments.clear();
    const indicator = thread.working();
    setBusy(true);
    try {
      const turn = await api("POST", url, form);
      indicator.remove();
      setChat(turn.chat_id, turn.display_id);
      const { bubble, time } = thread.publisherBubble(turn.reply);
      if (turn.plan) thread.showPlan(bubble, time, turn.plan, { open: true }, confirm);
      if (turn.problems && turn.problems.length) {
        thread.notice(bubble, "error", ["This plan cannot be confirmed:", ...turn.problems], time);
      }
      loadChats();
    } catch (error) {
      indicator.remove();
      const { bubble, time } = thread.publisherBubble("");
      thread.notice(bubble, "error", [error.message], time);
    } finally {
      setBusy(false);
      thread.scrollDown();
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
        thread.notice(bubble, result.ok ? "ok" : "error", [thread.createdLinks(result.created)], time);
      }
      if (result.error) thread.notice(bubble, "error", [result.error], time);
      if (result.mismatches.length) thread.notice(bubble, "error", result.mismatches, time);
      loadChats();
    } catch (error) {
      bar.replaceChildren(el("span", "muted", error.message));
    } finally {
      setBusy(false);
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
      const { bubble, time } = thread.publisherBubble("");
      thread.notice(bubble, "error", [error.message], time);
      return;
    }
    thread.replay(chat, confirm);
    setChat(chat.chat_id, chat.display_id);
    loadChats();
    toggleDrawer(false);
  }

  function newChat() {
    if (state.busy) return;
    setChat(null, null);
    thread.clearThread();
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

  function reportProblems(problems) {
    const { bubble, time } = thread.publisherBubble("");
    thread.notice(bubble, "error", problems, time);
  }

  function autoGrow() {
    const box = $("message");
    box.style.height = "auto";
    box.style.height = Math.min(box.scrollHeight, 200) + "px";
  }

  function init(context) {
    state.jiraSite = context.jiraSite || "";
    thread.setContext(context.initials, context.jiraSite);
    $("composer").addEventListener("submit", send);
    $("message").addEventListener("input", autoGrow);
    $("message").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) send(event);
    });
    $("attach").addEventListener("click", () => $("file-input").click());
    $("file-input").addEventListener("change", (event) => Brigade.attachments.pick(event, reportProblems));
    $("rail-toggle").addEventListener("click", () => toggleDrawer());
    $("new-chat").addEventListener("click", newChat);
    $("copy-chat-id").addEventListener("click", () => {
      if (state.displayId && navigator.clipboard) navigator.clipboard.writeText(state.displayId);
    });
    loadChats();
  }

  return { init };
})();
