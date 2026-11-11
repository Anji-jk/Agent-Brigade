"use strict";
/*
 * A small, safe Markdown renderer for chat answers: paragraphs, "- " lists (indented ones
 * nested by their spaces), "#" headings, **bold**, *italic* and `code`.
 * It builds DOM nodes and never uses innerHTML, so text from the agent or from Jira cannot
 * inject HTML into the page.
 */
window.Brigade = window.Brigade || {};

Brigade.markdown = (function () {
  const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;

  function inline(parent, text) {
    let last = 0;
    for (const match of text.matchAll(INLINE)) {
      if (match.index > last) parent.append(text.slice(last, match.index));
      const token = match[0];
      let node;
      if (token.startsWith("**")) {
        node = document.createElement("strong");
        node.textContent = token.slice(2, -2);
      } else if (token.startsWith("`")) {
        node = document.createElement("code");
        node.textContent = token.slice(1, -1);
      } else {
        node = document.createElement("em");
        node.textContent = token.slice(1, -1);
      }
      parent.append(node);
      last = match.index + token.length;
    }
    if (last < text.length) parent.append(text.slice(last));
    return parent;
  }

  function render(text) {
    const root = document.createElement("div");
    root.className = "md";
    let paragraph = null;
    let lists = []; // [{depth, element}]

    const closeParagraph = () => (paragraph = null);
    const closeLists = () => (lists = []);

    for (const raw of String(text || "").split("\n")) {
      const line = raw.replace(/\s+$/, "");
      const item = /^(\s*)[-*]\s+(.*)$/.exec(line);
      const heading = /^#{1,6}\s+(.*)$/.exec(line);
      if (!line.trim()) {
        closeParagraph();
        closeLists();
      } else if (item) {
        closeParagraph();
        const depth = item[1].replace(/\t/g, "  ").length;
        while (lists.length && lists[lists.length - 1].depth > depth) lists.pop();
        let list = lists[lists.length - 1];
        if (!list || list.depth < depth) {
          const element = document.createElement("ul");
          const parent = list ? list.element.lastElementChild || list.element : root;
          parent.append(element);
          list = { depth, element };
          lists.push(list);
        }
        list.element.append(inline(document.createElement("li"), item[2]));
      } else if (heading) {
        closeParagraph();
        closeLists();
        root.append(inline(document.createElement("h3"), heading[1]));
      } else {
        closeLists();
        if (paragraph) {
          paragraph.append(document.createElement("br"));
        } else {
          paragraph = document.createElement("p");
          root.append(paragraph);
        }
        inline(paragraph, line.trim());
      }
    }
    return root;
  }

  return { render };
})();
