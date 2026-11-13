"use strict";
/* The documents waiting to be sent with the next message: pick, show as chips, remove. */
window.Brigade = window.Brigade || {};

Brigade.attachments = (function () {
  const { $, el, icon } = Brigade.dom;
  const ACCEPT = [".txt", ".md", ".docx", ".pdf"];
  const MAX_FILES = 5;
  const MAX_BYTES = 10 * 1024 * 1024;
  let files = []; // File objects waiting to be sent

  function render() {
    const box = $("attached");
    box.replaceChildren();
    files.forEach((file, n) => {
      const chip = Brigade.thread.fileChip({ name: file.name });
      const remove = el("button", "chip-remove");
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove " + file.name);
      remove.append(icon("x"));
      remove.addEventListener("click", () => {
        files.splice(n, 1);
        render();
      });
      chip.append(remove);
      box.append(chip);
    });
    box.hidden = files.length === 0;
  }

  function pick(event, onProblems) {
    const problems = [];
    for (const file of event.target.files) {
      const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPT.includes(suffix)) problems.push(file.name + ": only " + ACCEPT.join(", ") + " files.");
      else if (file.size > MAX_BYTES) problems.push(file.name + " is larger than 10 MB.");
      else if (files.length >= MAX_FILES) problems.push("At most " + MAX_FILES + " files per message.");
      else files.push(file);
    }
    event.target.value = "";
    render();
    if (problems.length) {
      onProblems(problems);
    }
  }

  const waiting = () => files.slice();
  function clear() {
    files = [];
    render();
  }

  return { pick, render, waiting, clear };
})();
