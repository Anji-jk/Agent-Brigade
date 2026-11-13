"use strict";
/* Small helpers every tab uses: look up an element, make one, an icon, a date, a JSON call. */
window.Brigade = window.Brigade || {};

Brigade.dom = (function () {
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
    const options = { method };
    if (body instanceof FormData) options.body = body;
    else if (body !== undefined) {
      options.body = JSON.stringify(body);
      options.headers = { "Content-Type": "application/json" };
    }
    const response = await fetch(url, options);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
      throw new Error(detail || "The server answered HTTP " + response.status + ".");
    }
    return data;
  }

  return { $, el, icon, when, api };
})();