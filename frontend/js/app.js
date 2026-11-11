"use strict";

const TABS = ["publisher", "planning", "orchestrator"];

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    /* private mode or blocked storage: the choice just is not remembered */
  }
}

function recall(key) {
  try {
    return localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function showTab() {
  const wanted = location.hash.slice(1);
  const current = TABS.includes(wanted) ? wanted : TABS[0];
  for (const name of TABS) {
    document.getElementById(name).hidden = name !== current;
  }
  for (const link of document.querySelectorAll("#tabs a")) {
    link.classList.toggle("active", link.dataset.tab === current);
  }
}

function toggleDrawer() {
  const drawer = document.getElementById("chat-drawer");
  const button = document.getElementById("rail-toggle");
  drawer.hidden = !drawer.hidden;
  button.setAttribute("aria-expanded", String(!drawer.hidden));
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(url + " answered HTTP " + response.status);
  return response.json();
}

async function loadProjects() {
  const select = document.getElementById("project-select");
  const notice = document.getElementById("notice");
  try {
    const projects = await getJson("/api/projects");
    select.replaceChildren(
      ...projects.map((p) => {
        const option = document.createElement("option");
        option.value = p.id;
        option.textContent = p.name;
        option.title = p.local_path;
        return option;
      }),
    );
    const saved = recall("brigade.project");
    if (saved && projects.some((p) => String(p.id) === saved)) select.value = saved;
    if (projects.length === 0) {
      notice.textContent =
        "No project yet. Set BRIGADE_PROJECT_PATH (and BRIGADE_REPOSITORY) in .env and restart.";
      notice.hidden = false;
    }
  } catch (error) {
    notice.textContent = "Cannot reach the backend: " + error.message;
    notice.hidden = false;
  }
}

async function loadUser() {
  try {
    const health = await getJson("/api/health");
    document.getElementById("avatar").textContent = health.user_initials;
  } catch (error) {
    /* the project notice already reports an unreachable backend */
  }
}

document.getElementById("project-select").addEventListener("change", (event) => {
  remember("brigade.project", event.target.value);
});
document.getElementById("rail-toggle").addEventListener("click", toggleDrawer);
window.addEventListener("hashchange", showTab);

showTab();
loadProjects();
loadUser();
