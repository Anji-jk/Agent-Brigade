"use strict";
/*
* The "JIRA Plan" tree of a proposal: Epic > Story > Sub-task, with type badges.
* Before Confirm every Story and Sub-task carries a "New" badge; after Confirm the real Jira keys
* replace them, as links. Keys come in creation order: each Story, then its Sub-tasks.
*/
window.Brigade = window.Brigade || {};
 
Brigade.planTree = (function () {
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
 
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-" + name);
    svg.append(use);
    return svg;
  }
 
  function badge(kind, label, iconName) {
    const node = el("span", "badge badge-" + kind);
    node.append(icon(iconName), label);
    return node;
  }
 
  /** The first plain sentence of a description, without its "Business context:" style label. */
  function gist(description) {
    const first = String(description || "")
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line && !/^acceptance criteria:?$/i.test(line));
    if (!first) return "";
    const text = first.replace(/^[A-Za-z ]{3,30}:\s*/, "");
    return text.length > 180 ? text.slice(0, 177) + "..." : text;
  }
 
  function keyLabel(key, jiraSite) {
    if (!key) return el("span", "new", "New");
    if (!jiraSite) return el("span", "key", key);
    const link = el("a", "key", key);
    link.href = jiraSite + "/browse/" + key;
    link.target = "_blank";
    link.rel = "noopener";
    return link;
  }
 
  function details(description) {
    const box = el("details", "item-details");
    box.append(el("summary", "", "Description and acceptance criteria"));
    box.append(el("pre", "", description || ""));
    return box;
  }
 
  /** plan: {stories: [...]}; keys: created keys in creation order, or null before Confirm. */
  function render(plan, keys, jiraSite) {
    const root = el("div", "plan");
    const head = el("div", "plan-head");
    head.append(icon("diamond"), "JIRA Plan");
    root.append(head);
 
    const remaining = (keys || []).slice();
    const byEpic = new Map();
    for (const story of (plan && plan.stories) || []) {
      const epic = String(story.epic || "").toUpperCase();
      if (!byEpic.has(epic)) byEpic.set(epic, []);
      const storyKey = remaining.shift() || null;
      const subKeys = (story.subtasks || []).map(() => remaining.shift() || null);
      byEpic.get(epic).push({ story, storyKey, subKeys });
    }
 
    for (const [epic, items] of byEpic) {
      const epicRow = el("div", "plan-epic");
      epicRow.append(badge("epic", "Epic", "bolt"));
      const title = el("div", "plan-title");
      title.append(keyLabel(epic, jiraSite), el("span", "muted", " existing epic"));
      epicRow.append(title);
      root.append(epicRow);
 
      const stories = el("div", "plan-stories");
      for (const { story, storyKey, subKeys } of items) {
        const box = el("div", "plan-story");
        const row = el("div", "plan-story-row");
        row.append(badge("story", "Story", "book"));
        const text = el("div", "plan-title");
        const name = el("b");
        name.append(keyLabel(storyKey, jiraSite), " " + (story.summary || ""));
        text.append(name, el("div", "muted", gist(story.description)));
        row.append(text);
        box.append(row, details(story.description));
 
        const list = el("ul", "plan-subtasks");
        (story.subtasks || []).forEach((subtask, n) => {
          const li = el("li");
          li.append(icon("check"), keyLabel(subKeys[n], jiraSite), " " + (subtask.summary || ""));
          for (const label of subtask.labels || []) li.append(el("span", "label", label));
          li.append(details(subtask.description));
          list.append(li);
        });
        box.append(list);
        stories.append(box);
      }
      root.append(stories);
    }
    return root;
  }
 
  function counts(plan) {
    const stories = (plan && plan.stories) || [];
    const subtasks = stories.reduce((n, s) => n + (s.subtasks || []).length, 0);
    const word = (n, one, many) => n + " " + (n === 1 ? one : many);
    return word(stories.length, "Story", "Stories") + ", " + word(subtasks, "Sub-task", "Sub-tasks");
  }
 
  /** The same plan, whatever extra fields or casing it was stored with. */
  function signature(plan) {
    return JSON.stringify(
      ((plan && plan.stories) || []).map((s) => [
        String(s.epic || "").toUpperCase(),
        s.summary,
        (s.subtasks || []).map((t) => t.summary),
      ]),
    );
  }
 
  return { render, counts, signature, icon };
})();