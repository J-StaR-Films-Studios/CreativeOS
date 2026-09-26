/**
 * Dual-Engine SPA View Router
 * Seamlessly manages transitions between:
 * 1. "win11" (Windows 11 Native 3-Zone Desktop Explorer)
 * 2. "classic" (Studio Classic Dashboard with Analytics, Storage Visualizer & Original Cards)
 */

import { renderDashboard } from "./views/dashboardView.js";
import { renderExplorer } from "./views/explorerView.js";
import { disposeDesktopExplorer, renderDesktopExplorer } from "./views/desktopExplorerView.js";
import { renderStorage } from "./views/storageView.js";
import { renderNewProject } from "./views/newProjectView.js";
import { renderSettings } from "./views/settingsView.js";

const routes = {
  "#dashboard": renderDashboard,
  "#explorer": renderExplorer,
  "#storage": renderStorage,
  "#new": renderNewProject,
  "#settings": renderSettings,
};

export function getUiMode() {
  return localStorage.getItem("cos_ui_mode") || "win11";
}

export function setUiMode(mode) {
  const cleanMode = mode === "classic" ? "classic" : "win11";
  localStorage.setItem("cos_ui_mode", cleanMode);
  document.documentElement.setAttribute("data-ui-mode", cleanMode);
  document.body?.setAttribute("data-ui-mode", cleanMode);

  const header = document.querySelector(".app-header");
  if (header) {
    header.style.display = cleanMode === "win11" ? "none" : "";
  }

  updateSwitcherPillUI(cleanMode);

  // If switching to win11, ensure we route to explorer if currently on dashboard
  if (cleanMode === "win11" && (!window.location.hash || window.location.hash === "#dashboard")) {
    window.location.hash = "#explorer";
  } else {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
}

export function updateSwitcherPillUI(mode) {
  const currentMode = mode || getUiMode();
  const btnWin11 = document.getElementById("btn-mode-win11");
  const btnClassic = document.getElementById("btn-mode-classic");

  if (btnWin11 && btnClassic) {
    const isWin11 = currentMode === "win11";
    btnWin11.classList.toggle("active", isWin11);
    btnWin11.setAttribute("aria-checked", isWin11 ? "true" : "false");
    btnClassic.classList.toggle("active", !isWin11);
    btnClassic.setAttribute("aria-checked", !isWin11 ? "true" : "false");
  }
}

export function initRouter(containerId = "app-main") {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Initialize UI mode state
  const currentMode = getUiMode();
  document.documentElement.setAttribute("data-ui-mode", currentMode);
  document.body?.setAttribute("data-ui-mode", currentMode);
  const header = document.querySelector(".app-header");
  if (header) {
    header.style.display = currentMode === "win11" ? "none" : "";
  }
  updateSwitcherPillUI(currentMode);

  // Attach Switcher Pill Event Handlers
  document.getElementById("btn-mode-win11")?.addEventListener("click", () => {
    setUiMode("win11");
  });

  document.getElementById("btn-mode-classic")?.addEventListener("click", () => {
    setUiMode("classic");
  });

  function handleRoute() {
    const uiMode = getUiMode();
    const rawHash = window.location.hash || (uiMode === "win11" ? "#explorer" : "#dashboard");
    const [baseHash, queryString] = rawHash.split("?");

    let routeKey = baseHash;
    if (!routes[routeKey]) {
      routeKey = uiMode === "win11" ? "#explorer" : "#dashboard";
    }

    // Parse query parameters
    const params = new URLSearchParams(queryString || "");
    let initialPath = params.get("path");
    if (initialPath === null && (routeKey === "#explorer" || routeKey === "#dashboard")) {
      initialPath = localStorage.getItem("cos_explorer_last_path") || "";
    } else if (initialPath === null) {
      initialPath = "";
    }

    // Update active nav link
    document.querySelectorAll(".nav-item").forEach((el) => {
      const linkHash = el.getAttribute("href");
      if (linkHash === routeKey) {
        el.classList.add("active");
      } else {
        el.classList.remove("active");
      }
    });

    const header = document.querySelector(".app-header");
    if (header) {
      const isWin11Explorer = uiMode === "win11" && (routeKey === "#explorer" || routeKey === "#dashboard");
      header.style.display = isWin11Explorer ? "none" : "";
    }

    // Render corresponding view based on active Experience Mode
    if (uiMode === "win11" && (routeKey === "#explorer" || routeKey === "#dashboard")) {
      container.classList.add("is-win11-engine");
      renderDesktopExplorer(container, initialPath);
    } else {
      disposeDesktopExplorer();
      container.classList.remove("is-win11-engine");
      const renderFn = routes[routeKey] || renderDashboard;
      if (routeKey === "#explorer") {
        renderFn(container, initialPath);
      } else if (routeKey === "#storage") {
        const targetProject = params.get("project") || "";
        renderFn(container, { project: targetProject });
      } else {
        renderFn(container);
      }
    }
  }

  window.addEventListener("hashchange", handleRoute);
  handleRoute();
}
