/**
 * Windows 11 Native 3-Zone Desktop Explorer View Component
 *
 * Features:
 * - Windows 11 Chrome: Tabs bar with sessionStorage isolation, Navigation row (Back/Forward/Up/Refresh/Interactive Breadcrumbs/Omni-Search), Fluent Command Ribbon.
 * - Zone 1 (Tree Sidebar): Quick Access, Project Categories with live counts, Mounted Windows Drives, Studio Tools (Storage & Settings).
 * - Zone 2 (Center Canvas):
 *     1. Large Icons Grid View (with stripped date prefix & high-res image previews)
 *     2. Details Table View (sortable columns: Name, Date modified, Type, Size)
 *     3. Dual-Pane External RAID Bridge (1-click Ingest via /api/fs/transfer)
 *     4. 4K Media Scrubber & Waveform Player hooked to /api/fs/raw
 * - Zone 3 (Right Details Inspector): File specifications + live Markdown & Code preview + Media sync + 2-Column Action Deck + Clickable Location Copy.
 * - Right-Click Native Context Menu: Open, Copy Path, Export Folder, Shuttle Travel, Reclaim Cache, Properties.
 * - Per-Folder View Mode Memory: Each folder remembers its view mode, and new folders inherit the last active view mode.
 * - Back Navigation Selection Memory: Automatically re-highlights and scrolls to the previous subfolder when going back.
 */

import { api, formatBytes } from "../api.js";
import { getCategoryIconSvg, getFileIconSvg, icons } from "../icons.js";
import { showToast } from "../components/toast.js";
import { toggleTheme } from "../theme.js";
import { openNewProjectModal } from "../components/newProjectModal.js";
import { openBulkReclaimModal, openReclaimModal } from "../components/reclaimModal.js";
import { openLiveSyncModal, openProjectInspector, openConfirmModal } from "../components/modal.js";
import { setUiMode } from "../router.js";
import { renderStorage } from "./storageView.js";
import { renderSettings } from "./settingsView.js";

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatGridItemName(name, isDir = false) {
  if (!name || !isDir) return name || "";
  // Strip date prefixes like YYYY-MM-DD_ from folder names only
  const stripped = name.replace(/^\d{4}-\d{2}-\d{2}[-_]/i, "");
  return stripped || name;
}

let activeExplorerController = null;

export function disposeDesktopExplorer() {
  activeExplorerController?.abort();
  activeExplorerController = null;
  document.getElementById("win11-fullscreen-overlay")?.remove();
}

function renderMarkdownSafe(rawText) {
  if (!rawText) return '<p style="color: var(--text-muted); font-style: italic;">Empty document</p>';

  let html = escapeHtml(rawText);

  // Code blocks: ```code```
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="win11-code-block font-mono"><code>${code}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code class="win11-inline-code font-mono">$1</code>');

  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3 class="win11-md-h3">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 class="win11-md-h2">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 class="win11-md-h1">$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Blockquotes
  html = html.replace(/^\> (.*$)/gim, '<blockquote class="win11-blockquote">$1</blockquote>');

  // Bullet lists
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul class="win11-md-list">$1</ul>');

  // Paragraphs
  html = html.split('\n\n').map(p => {
    p = p.trim();
    if (!p) return '';
    if (p.startsWith('<h') || p.startsWith('<pre') || p.startsWith('<ul') || p.startsWith('<blockquote')) {
      return p;
    }
    return `<p class="win11-md-p">${p.replace(/\n/g, '<br>')}</p>`;
  }).join('');

  return html;
}

export async function renderDesktopExplorer(container, initialPath = "") {
  disposeDesktopExplorer();
  const explorerController = new AbortController();
  const { signal } = explorerController;
  activeExplorerController = explorerController;

  // Parse initial path from URL query or argument
  let startPath = initialPath;
  if (!startPath) {
    const params = new URLSearchParams(window.location.hash.split("?")[1] || "");
    startPath = params.get("path") || "";
  }

  // Restore tabs from sessionStorage (isolated per browser window/tab)
  let savedTabs = null;
  try {
    savedTabs = JSON.parse(sessionStorage.getItem("cos_win11_tabs_session") || "null");
  } catch {}

  let tabs = savedTabs && Array.isArray(savedTabs) && savedTabs.length > 0 ? savedTabs : [
    {
      id: 1,
      title: startPath ? startPath.split(/[\\/]/).filter(Boolean).pop() || "Explorer" : "01_Projects",
      path: startPath || "",
      history: [startPath || ""],
      historyIndex: 0,
    }
  ];

  let activeTabId = Number(sessionStorage.getItem("cos_win11_active_tab_id")) || tabs[0]?.id || 1;
  if (!tabs.some(t => t.id === activeTabId)) {
    activeTabId = tabs[0]?.id || 1;
  }

  // Per-Folder View Mode Memory & Inheritance
  let folderViewMap = {};
  try {
    folderViewMap = JSON.parse(localStorage.getItem("cos_folder_view_map") || "{}");
  } catch {}
  let lastGlobalView = localStorage.getItem("cos_last_global_view") || "grid";
  let viewMode = folderViewMap[startPath] || lastGlobalView;

  let sortField = localStorage.getItem("cos_win11_sort_field") || "name";
  let sortDir = localStorage.getItem("cos_win11_sort_dir") || "asc";
  let showZone3 = localStorage.getItem("cos_win11_show_inspector") !== "false";
  let isInspectorWide = localStorage.getItem("cos_win11_inspector_wide") === "true";
  let selectedItem = null;
  let lastSelectedInFolder = {};
  let currentEntries = [];
  let currentParentPath = null;
  let projectsList = [];
  let storageData = null;
  let configData = null;
  let categoriesData = {};
  let directoryLoadId = 0;

  // Dual Pane Ingest State (View 3)
  let dualLeftPath = localStorage.getItem("cos_dual_left_path") || "Downloads";
  let dualRightPath = localStorage.getItem("cos_dual_right_path") || "";
  if (dualRightPath === "01_Projects") dualRightPath = "";
  let dualLeftEntries = [];
  let dualRightEntries = [];
  let dualLeftSelected = [];
  let dualMoveMode = false;
  let dualOverwrite = false;

  // Media Player State (View 4)
  let activeMediaFile = null;

  // Global media playback sync
  let isMediaMuted = localStorage.getItem("cos_media_muted") !== "false";
  let shouldPlayMedia = localStorage.getItem("cos_media_playback") !== "paused";

  function setupMediaSync(mediaEl) {
    if (!mediaEl) return;
    mediaEl.muted = isMediaMuted;
    if (shouldPlayMedia) {
      mediaEl.play().catch(() => {});
    } else {
      mediaEl.pause();
    }
    mediaEl.addEventListener("play", () => {
      shouldPlayMedia = true;
      localStorage.setItem("cos_media_playback", "playing");
    });
    mediaEl.addEventListener("pause", () => {
      if (mediaEl.currentTime < (mediaEl.duration || 1) - 0.15) {
        shouldPlayMedia = false;
        localStorage.setItem("cos_media_playback", "paused");
      }
    });
    mediaEl.addEventListener("volumechange", () => {
      isMediaMuted = mediaEl.muted;
      localStorage.setItem("cos_media_muted", isMediaMuted ? "true" : "false");
    });
  }

  // Load Initial Data in Parallel
  try {
    const [projs, storage, conf, cats] = await Promise.all([
      api.getProjectsSWR((fresh) => { projectsList = fresh; updateSidebarBadges(); }),
      api.getStorageSWR((fresh) => { storageData = fresh; }),
      api.getConfigSWR((fresh) => { configData = fresh; }),
      api.getCategoriesSWR((fresh) => { categoriesData = fresh.categories || {}; renderSidebarCategories(); }),
    ]);
    projectsList = projs || [];
    storageData = storage || null;
    configData = conf || null;
    categoriesData = cats?.categories || {};
    const projectsRoot = configData?.paths?.projects_path?.path || configData?.config?.projects_path || "";
    if (projectsRoot && !/^(?:[A-Za-z]:[\\/]|\\\\|\/)/.test(dualRightPath)) {
      const relativeTarget = dualRightPath.replace(/^01_Projects[\\/]?/, "");
      const separator = projectsRoot.includes("\\") ? "\\" : "/";
      dualRightPath = relativeTarget
        ? `${projectsRoot.replace(/[\\/]$/, "")}${separator}${relativeTarget}`
        : projectsRoot;
      localStorage.setItem("cos_dual_right_path", dualRightPath);
    }
  } catch (e) {
    console.warn("[Explorer SWR]", e);
  }
  if (signal.aborted) return;

  function getActiveTab() {
    return tabs.find(t => t.id === activeTabId) || tabs[0];
  }

  function saveTabsSession() {
    try {
      sessionStorage.setItem("cos_win11_tabs_session", JSON.stringify(tabs));
      sessionStorage.setItem("cos_win11_active_tab_id", String(activeTabId));
    } catch {}
  }

  function updateActiveTabPath(newPath, recordHistory = true) {
    const tab = getActiveTab();
    if (!tab) return;

    if (tab.path) {
      const segs = newPath.split(/[\\/]/).filter(Boolean);
      const prevName = segs[segs.length - 1];
      if (prevName) {
        lastSelectedInFolder[tab.path] = prevName;
      }
    }

    tab.path = newPath;
    if (newPath === "storage") {
      tab.title = "Storage Inventory";
    } else if (newPath === "settings") {
      tab.title = "Studio Settings";
    } else if (newPath === "archive") {
      tab.title = "Cold Archive";
    } else {
      tab.title = newPath ? newPath.split(/[\\/]/).filter(Boolean).pop() || "Folder" : "01_Projects";
    }

    if (recordHistory) {
      if (tab.historyIndex < tab.history.length - 1) {
        tab.history = tab.history.slice(0, tab.historyIndex + 1);
      }
      tab.history.push(newPath);
      tab.historyIndex = tab.history.length - 1;
    }

    saveTabsSession();

    // Update URL hash with query param
    const currentHash = (window.location.hash || "#explorer").split("?")[0];
    window.history.replaceState(null, "", `${currentHash}?path=${encodeURIComponent(newPath)}`);

    renderTabsBar();
    loadCurrentDirectory();
  }

  // Render Skeleton Shell
  container.innerHTML = `
    <div class="win11-explorer-root" id="win11-explorer-root">
      <!-- Windows 11 Chrome: Tab Bar -->
      <div class="win11-chrome-tabs-bar" id="win11-tabs-bar">
        <!-- Rendered by renderTabsBar() -->
      </div>

      <!-- Navigation & Address Row -->
      <div class="win11-nav-row">
        <div class="win11-nav-buttons">
          <button class="win11-nav-btn" id="win11-nav-back" title="Back (Alt+Left)" disabled>${icons.arrowLeft}</button>
          <button class="win11-nav-btn" id="win11-nav-forward" title="Forward (Alt+Right)" disabled>${icons.arrowRight}</button>
          <button class="win11-nav-btn" id="win11-nav-up" title="Up to Parent Directory (Alt+Up)" disabled>${icons.arrowUp}</button>
          <button class="win11-nav-btn" id="win11-nav-refresh" title="Refresh (F5)">${icons.refresh}</button>
        </div>

        <!-- Interactive Breadcrumbs Bar -->
        <div class="win11-address-bar" id="win11-address-bar">
          <div class="win11-address-icon">${icons.folder}</div>
          <div class="win11-breadcrumbs-list" id="win11-breadcrumbs-list"></div>
          <input type="text" class="win11-address-input font-mono" id="win11-address-input" style="display: none;" />
          <button class="win11-address-action-btn" id="win11-copy-address-btn" title="Copy Path">${icons.copy}</button>
        </div>

        <!-- Search Box with Omni-Search -->
        <div class="win11-search-box" style="position: relative;">
          <span class="win11-search-icon">${icons.search}</span>
          <input type="text" class="win11-search-input" id="win11-search-input" placeholder="Search / Filter..." autocomplete="off" />
        </div>
      </div>

      <!-- Fluent Command Ribbon -->
      <div class="win11-command-ribbon" id="win11-ribbon">
        <div class="win11-ribbon-left">
          <button class="win11-ribbon-btn primary" id="win11-btn-new-project">
            ${icons.plus}
            <span>New</span>
          </button>
          
          <div class="win11-ribbon-sep"></div>

          <!-- View Mode Toggle -->
          <button class="win11-ribbon-btn" id="win11-btn-view-toggle" title="Switch between Large Icons Grid and Details Table">
            <span id="win11-view-toggle-icon">${viewMode === 'grid' ? icons.table : icons.grid}</span>
            <span id="win11-view-toggle-text">${viewMode === 'grid' ? 'Details' : 'Large Icons'}</span>
          </button>

          <button class="win11-ribbon-btn ${viewMode === 'split' ? 'active' : ''}" id="win11-btn-view-split" title="Dual-Pane Ingest Bridge">
            ${icons.columns}
            <span>RAID Ingest</span>
          </button>

          <div class="win11-ribbon-sep"></div>

          <!-- Active Project Context Actions -->
          <button class="win11-ribbon-btn" id="win11-btn-export-folder" title="Open or generate Project Export Folder in a new tab">
            ${icons.exportFolder}
            <span>Export Folder</span>
          </button>
          <button class="win11-ribbon-btn" id="win11-btn-reclaim-cache" title="Reclaim project render caches or bulk clean">
            ${icons.zap}
            <span>Reclaim Cache</span>
          </button>
          <button class="win11-ribbon-btn" id="win11-btn-sync-vault" title="Sync project notes with Obsidian Vault">
            ${icons.sync}
            <span>Sync Vault</span>
          </button>
          <button class="win11-ribbon-btn" id="win11-btn-shuttle-travel" title="Sync project to Shuttle External Drive">
            ${icons.travel}
            <span>Shuttle</span>
          </button>
        </div>

        <div class="win11-ribbon-right">
          <button class="win11-ribbon-btn icon-only" id="win11-btn-theme-toggle" title="Toggle Light/Dark Theme">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
          </button>
          <button class="win11-ribbon-btn ${showZone3 ? 'active' : ''}" id="win11-btn-toggle-inspector" title="Toggle Details Inspector Pane">
            ${icons.info}
            <span>Details</span>
          </button>
          <button class="win11-ribbon-btn studio-classic-pill" id="win11-btn-switch-classic" title="Switch to Studio Dashboard">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            <span>Studio Classic</span>
          </button>
        </div>
      </div>

      <!-- Main 3-Zone Workspace Layout -->
      <div class="win11-workspace-layout ${showZone3 ? 'with-inspector' : ''} ${isInspectorWide ? 'inspector-is-wide' : ''}" id="win11-workspace-layout">
        <!-- Zone 1: Fluent Navigation Tree Sidebar -->
        <aside class="win11-zone1-sidebar" id="win11-sidebar">
          <div class="win11-sidebar-scroll">
            <!-- Quick Access / Pinned -->
            <div class="win11-sidebar-section">
              <div class="win11-section-header">
                <span>QUICK ACCESS</span>
              </div>
              <ul class="win11-nav-tree">
                <li class="win11-tree-item" data-path="" title="CreativeOS Projects Workspace">
                  <span class="win11-tree-icon" style="color: var(--color-primary);">${icons.folder}</span>
                  <span class="win11-tree-label">Projects Root</span>
                </li>
                <li class="win11-tree-item" data-path="00_Notes" title="Obsidian Brain Vault (Project-Aware)">
                  <span class="win11-tree-icon" style="color: var(--color-success);">${icons.notes}</span>
                  <span class="win11-tree-label">00_Notes (Vault)</span>
                </li>
                <li class="win11-tree-item" data-path="02_Exports" title="Render Exports (Project-Aware)">
                  <span class="win11-tree-icon" style="color: var(--color-accent-cyan);">${icons.exportFolder}</span>
                  <span class="win11-tree-label">02_Exports</span>
                </li>
                <li class="win11-tree-item" data-path="Downloads" title="User Downloads Folder">
                  <span class="win11-tree-icon" style="color: #3b82f6;">${icons.download}</span>
                  <span class="win11-tree-label">Downloads</span>
                </li>
                <li class="win11-tree-item" data-path="Desktop" title="User Desktop">
                  <span class="win11-tree-icon" style="color: #6366f1;">${icons.desktop}</span>
                  <span class="win11-tree-label">Desktop</span>
                </li>
              </ul>
            </div>

            <!-- Project Categories -->
            <div class="win11-sidebar-section">
              <div class="win11-section-header">
                <span>CATEGORIES</span>
              </div>
              <ul class="win11-nav-tree" id="win11-categories-tree">
                <!-- Dynamically rendered from /api/categories -->
              </ul>
            </div>

            <!-- Mounted Windows Drives & Cold Storage -->
            <div class="win11-sidebar-section">
              <div class="win11-section-header">
                <span>THIS PC &amp; DRIVES</span>
              </div>
              <ul class="win11-nav-tree" id="win11-drives-tree">
                <!-- Dynamically rendered from /api/config/drives -->
              </ul>
            </div>

            <!-- Studio Tools -->
            <div class="win11-sidebar-section">
              <div class="win11-section-header">
                <span>STUDIO TOOLS</span>
              </div>
              <ul class="win11-nav-tree">
                <li class="win11-tree-item" data-action="storage-inventory" data-path="storage" title="Studio Storage Visualizer & Project Analytics">
                  <span class="win11-tree-icon" style="color: var(--color-warning);">${icons.zap}</span>
                  <span class="win11-tree-label">Storage Inventory</span>
                </li>
                <li class="win11-tree-item" data-action="cold-archive" data-path="archive" title="Browse and resurrect projects in cold secondary storage">
                  <span class="win11-tree-icon" style="color: var(--color-primary);">${icons.archive}</span>
                  <span class="win11-tree-label">Cold Archive</span>
                </li>
                <li class="win11-tree-item" data-action="clean-downloads" title="Organize loose downloads into categorized subfolders">
                  <span class="win11-tree-icon" style="color: #3b82f6;">${icons.download}</span>
                  <span class="win11-tree-label">Clean Downloads</span>
                </li>
                <li class="win11-tree-item" data-action="sort-inbox" title="Sort unfiled renders into monthly export folders">
                  <span class="win11-tree-icon" style="color: var(--color-accent-cyan);">${icons.exportFolder}</span>
                  <span class="win11-tree-label">Sort Inbox</span>
                </li>
                <li class="win11-tree-item" data-action="bulk-reclaim" title="Scan and reclaim storage studio-wide">
                  <span class="win11-tree-icon" style="color: var(--color-danger);">${icons.zap}</span>
                  <span class="win11-tree-label">Bulk Reclaim</span>
                </li>
                <li class="win11-tree-item" data-action="studio-settings" data-path="settings" title="CreativeOS Configuration & Settings">
                  <span class="win11-tree-icon" style="color: var(--text-muted);">${icons.settings || icons.externalLink}</span>
                  <span class="win11-tree-label">Studio Settings</span>
                </li>
              </ul>
            </div>
          </div>
        </aside>

        <!-- Zone 2: Center Canvas (Dynamic View Engines) -->
        <main class="win11-zone2-canvas" id="win11-canvas">
          <div class="win11-canvas-loading">
            <div class="spinner"></div>
            <p>Loading files...</p>
          </div>
        </main>

        <!-- Zone 3: Right Details Inspector & Action Deck -->
        <aside class="win11-zone3-inspector" id="win11-inspector" style="${showZone3 ? '' : 'display: none;'}">
          <!-- Rendered by renderInspector() -->
        </aside>
      </div>

      <!-- Windows 11 Status Bar -->
      <footer class="win11-status-bar" id="win11-status-bar">
        <div class="win11-status-left">
          <span id="win11-status-count">0 items</span>
          <span class="win11-status-sep">|</span>
          <span id="win11-status-selection">No item selected</span>
        </div>
        <div class="win11-status-right">
          <button class="win11-status-view-btn ${viewMode === 'details' ? 'active' : ''}" id="status-btn-view-details" title="Details Table View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
          </button>
          <button class="win11-status-view-btn ${viewMode === 'grid' ? 'active' : ''}" id="status-btn-view-grid" title="Large Icons Grid View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          </button>
        </div>
      </footer>

      <!-- Windows 11 Floating Context Menu -->
      <div class="win11-context-menu" id="win11-context-menu" style="display: none;"></div>
    </div>
  `;

  // DOM Elements References
  const tabsBarEl = document.getElementById("win11-tabs-bar");
  const breadcrumbsListEl = document.getElementById("win11-breadcrumbs-list");
  const addressInputEl = document.getElementById("win11-address-input");
  const addressBarEl = document.getElementById("win11-address-bar");
  const canvasEl = document.getElementById("win11-canvas");
  const inspectorEl = document.getElementById("win11-inspector");
  const searchInputEl = document.getElementById("win11-search-input");
  const navBackBtn = document.getElementById("win11-nav-back");
  const navForwardBtn = document.getElementById("win11-nav-forward");
  const navUpBtn = document.getElementById("win11-nav-up");
  const navRefreshBtn = document.getElementById("win11-nav-refresh");
  const copyAddressBtn = document.getElementById("win11-copy-address-btn");
  const statusCountEl = document.getElementById("win11-status-count");
  const statusSelectionEl = document.getElementById("win11-status-selection");
  const workspaceLayoutEl = document.getElementById("win11-workspace-layout");

  // ──────────────────────────────────────────────────────────────────────────
  // Tab Bar Management
  // ──────────────────────────────────────────────────────────────────────────
  function renderTabsBar() {
    if (!tabsBarEl) return;

    tabsBarEl.innerHTML = `
      <div class="win11-tabs-list">
        ${tabs.map(tab => {
          const isActive = tab.id === activeTabId;
          let tabIcon = icons.folder;
          if (tab.path === "storage") tabIcon = `<span style="color: var(--color-warning);">${icons.zap}</span>`;
          else if (tab.path === "settings") tabIcon = `<span style="color: var(--text-muted);">${icons.settings || icons.externalLink}</span>`;
          else if (tab.path === "archive") tabIcon = `<span style="color: var(--color-primary);">${icons.archive}</span>`;
          else if (tab.path === "02_Exports") tabIcon = `<span style="color: var(--color-accent-cyan);">${icons.exportFolder}</span>`;
          else if (tab.path === "Downloads") tabIcon = `<span style="color: #3b82f6;">${icons.download}</span>`;

          return `
            <div class="win11-tab-item ${isActive ? 'active' : ''}" data-tab-id="${tab.id}" role="tab" tabindex="0" aria-selected="${isActive}">
              <span class="win11-tab-icon">${tabIcon}</span>
              <span class="win11-tab-title font-mono" title="${tab.title}">${escapeHtml(tab.title)}</span>
              ${tabs.length > 1 ? `
                <button class="win11-tab-close-btn" data-close-tab="${tab.id}" title="Close tab">
                  ${icons.x}
                </button>
              ` : ''}
            </div>
          `;
        }).join("")}
        <button class="win11-tab-add-btn" id="win11-tab-add-btn" title="New Tab (Ctrl+T)">
          ${icons.plus}
        </button>
      </div>
    `;

    tabsBarEl.querySelectorAll(".win11-tab-item").forEach(item => {
      item.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          item.click();
        }
      });
      item.addEventListener("click", (e) => {
        if (e.target.closest(".win11-tab-close-btn")) return;
        const id = Number(item.getAttribute("data-tab-id"));
        if (id !== activeTabId) {
          activeTabId = id;
          saveTabsSession();
          renderTabsBar();
          loadCurrentDirectory();
        }
      });
    });

    tabsBarEl.querySelectorAll(".win11-tab-close-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = Number(btn.getAttribute("data-close-tab"));
        tabs = tabs.filter(t => t.id !== id);
        if (activeTabId === id) {
          activeTabId = tabs[tabs.length - 1].id;
        }
        saveTabsSession();
        renderTabsBar();
        loadCurrentDirectory();
      });
    });

    document.getElementById("win11-tab-add-btn")?.addEventListener("click", () => {
      const newId = Date.now();
      tabs.push({
        id: newId,
        title: "01_Projects",
        path: "",
        history: [""],
        historyIndex: 0,
      });
      activeTabId = newId;
      saveTabsSession();
      renderTabsBar();
      loadCurrentDirectory();
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Breadcrumbs & Address Bar
  // ──────────────────────────────────────────────────────────────────────────
  function renderBreadcrumbs(fullPath, relDisplay) {
    if (!breadcrumbsListEl) return;

    const currentP = getActiveTab().path;
    const norm = (fullPath || currentP || "01_Projects").replace(/\\/g, "/");
    const segments = norm.split("/").filter(Boolean);

    let accum = "";
    const crumbs = segments.map((seg, idx) => {
      if (idx === 0 && seg.endsWith(":")) {
        accum = seg;
      } else {
        accum = accum ? `${accum}/${seg}` : seg;
      }
      const isLast = idx === segments.length - 1;
      const targetP = accum === "01_Projects" ? "" : accum;

      return `
        <button class="win11-breadcrumb-btn ${isLast ? 'active' : ''}" data-path="${targetP}" title="${accum}">
          ${seg}
        </button>
        ${!isLast ? `<button class="win11-breadcrumb-sep-btn" data-parent-path="${targetP}" title="List folders in ${seg}">&rsaquo;</button>` : ''}
      `;
    });

    breadcrumbsListEl.innerHTML = crumbs.join("");

    // Wire breadcrumb button clicks
    breadcrumbsListEl.querySelectorAll(".win11-breadcrumb-btn:not(.active)").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = btn.getAttribute("data-path");
        updateActiveTabPath(p);
      });
    });

    // Wire breadcrumb chevron dropdowns
    breadcrumbsListEl.querySelectorAll(".win11-breadcrumb-sep-btn").forEach(sepBtn => {
      sepBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const pPath = sepBtn.getAttribute("data-parent-path");
        document.querySelectorAll(".win11-breadcrumb-dropdown").forEach(d => d.remove());

        try {
          const res = await api.listFiles(pPath);
          const folders = (res.entries || []).filter(e => e.is_dir);
          if (!folders.length) return;

          const dropEl = document.createElement("div");
          dropEl.className = "win11-breadcrumb-dropdown";
          dropEl.innerHTML = folders.map(f => `
            <div class="win11-breadcrumb-menu-item" data-path="${f.path}">
              <span style="color: var(--color-primary);">${icons.folder}</span>
              <span>${escapeHtml(f.name)}</span>
            </div>
          `).join("");

          sepBtn.parentElement.style.position = "relative";
          sepBtn.parentElement.appendChild(dropEl);

          dropEl.querySelectorAll(".win11-breadcrumb-menu-item").forEach(itemEl => {
            itemEl.addEventListener("click", () => {
              const target = itemEl.getAttribute("data-path");
              dropEl.remove();
              updateActiveTabPath(target);
            });
          });

          const closeHandler = () => {
            dropEl.remove();
            document.removeEventListener("click", closeHandler);
          };
          setTimeout(() => {
            if (!signal.aborted) document.addEventListener("click", closeHandler, { signal });
          }, 10);
        } catch {}
      });
    });
  }

  // Global Address Bar Omni-Search Dropdown
  const addressOmniDropdownEl = document.createElement("div");
  addressOmniDropdownEl.className = "win11-omni-dropdown";
  addressOmniDropdownEl.id = "win11-address-omni-dropdown";
  addressOmniDropdownEl.style.display = "none";
  addressBarEl?.appendChild(addressOmniDropdownEl);

  // Address Bar Click to Edit Direct Path
  addressBarEl?.addEventListener("click", (e) => {
    if (e.target.closest(".win11-breadcrumb-btn") || e.target.closest(".win11-breadcrumb-sep-btn") || e.target.closest("#win11-copy-address-btn") || e.target.closest(".win11-omni-dropdown")) return;
    if (addressInputEl && breadcrumbsListEl && addressInputEl.style.display !== "block") {
      breadcrumbsListEl.style.display = "none";
      addressInputEl.value = getActiveTab().path || "01_Projects";
      addressInputEl.placeholder = "Type directory path, category, or project name to jump...";
      addressInputEl.style.display = "block";
      addressInputEl.focus();
      addressInputEl.select();
    }
  });

  addressInputEl?.addEventListener("input", () => {
    const q = (addressInputEl.value || "").toLowerCase().trim();
    if (!q || q.length < 1) {
      addressOmniDropdownEl.style.display = "none";
      return;
    }

    const matchedProjects = (projectsList || []).filter(p => {
      const name = (p.name || p.slug || "").toLowerCase();
      const client = (p.client || "").toLowerCase();
      const type = (p.type || p.category || "").toLowerCase();
      const path = (p.path || "").toLowerCase();
      return name.includes(q) || client.includes(q) || type.includes(q) || path.includes(q);
    }).slice(0, 6);

    const commonPaths = [
      { name: "01_Projects Root", path: "", type: "Workspace" },
      { name: "00_Notes (Vault)", path: "00_Notes", type: "Vault" },
      { name: "02_Exports (Inbox)", path: "02_Exports", type: "Exports" },
      { name: "Downloads", path: "Downloads", type: "User Folder" },
      { name: "Desktop", path: "Desktop", type: "User Folder" },
      { name: "Video Category", path: "Video", type: "Category" },
      { name: "Code Category", path: "Code", type: "Category" },
      { name: "Audio & Music", path: "Audio", type: "Category" },
      { name: "Clients", path: "Clients", type: "Category" },
      { name: "Storage Drive (D:)", path: "D:\\", type: "Drive" },
      { name: "Media RAID (E:)", path: "E:\\", type: "Drive" }
    ].filter(cp => cp.name.toLowerCase().includes(q) || cp.path.toLowerCase().includes(q)).slice(0, 4);

    if (matchedProjects.length > 0 || commonPaths.length > 0) {
      addressOmniDropdownEl.innerHTML = `
        <div style="font-family: var(--font-mono); font-size: 0.65rem; font-weight: 700; color: var(--text-muted); padding: 0.25rem 0.5rem; letter-spacing: 0.05em;">GLOBAL STUDIO JUMP / SEARCH</div>
        ${matchedProjects.map(m => `
          <div class="win11-omni-item" data-path="${m.path}">
            <div style="display: flex; align-items: center; gap: 0.45rem;">
              <span style="color: var(--color-primary);">${icons.folder}</span>
              <span style="font-weight: 600;">${escapeHtml(m.name || m.slug)}</span>
            </div>
            <span class="win11-omni-meta">${m.type || 'Project'} &bull; ${m.client || 'Internal'}</span>
          </div>
        `).join("")}
        ${commonPaths.map(cp => `
          <div class="win11-omni-item" data-path="${cp.path}">
            <div style="display: flex; align-items: center; gap: 0.45rem;">
              <span style="color: var(--color-accent-cyan);">${icons.drive}</span>
              <span style="font-weight: 600;">${escapeHtml(cp.name)}</span>
            </div>
            <span class="win11-omni-meta">${cp.type}</span>
          </div>
        `).join("")}
      `;
      addressOmniDropdownEl.style.display = "block";

      addressOmniDropdownEl.querySelectorAll(".win11-omni-item").forEach(itemEl => {
        itemEl.addEventListener("click", (e) => {
          e.stopPropagation();
          const p = itemEl.getAttribute("data-path");
          addressOmniDropdownEl.style.display = "none";
          addressInputEl.style.display = "none";
          breadcrumbsListEl.style.display = "flex";
          updateActiveTabPath(p);
        });
      });
    } else {
      addressOmniDropdownEl.style.display = "none";
    }
  });

  addressInputEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const q = addressInputEl.value.trim();
      addressOmniDropdownEl.style.display = "none";
      addressInputEl.style.display = "none";
      breadcrumbsListEl.style.display = "flex";

      if (!q || q === "01_Projects") {
        updateActiveTabPath("");
        return;
      }

      // Check if direct exact path or starts with drive/CreativeOS
      const directPaths = ["00_Notes", "02_Exports", "Downloads", "Desktop", "Video", "Code", "Audio", "AI", "Design", "Photo", "Clients"];
      if (directPaths.includes(q) || q.includes(":\\") || q.includes(":/") || q.startsWith("01_Projects") || q.startsWith("02_Exports")) {
        updateActiveTabPath(q);
        return;
      }

      // Match best project by name or slug
      const qLower = q.toLowerCase();
      const exactMatch = (projectsList || []).find(p => (p.name || "").toLowerCase() === qLower || (p.slug || "").toLowerCase() === qLower);
      if (exactMatch) {
        updateActiveTabPath(exactMatch.path);
        return;
      }

      const partialMatch = (projectsList || []).find(p => (p.name || "").toLowerCase().includes(qLower) || (p.slug || "").toLowerCase().includes(qLower) || (p.client || "").toLowerCase().includes(qLower));
      if (partialMatch) {
        showToast(`Jumped to project: ${partialMatch.name}`, "info", 1500);
        updateActiveTabPath(partialMatch.path);
        return;
      }

      // Fallback: try navigating directly to typed path
      updateActiveTabPath(q);
    } else if (e.key === "Escape") {
      addressOmniDropdownEl.style.display = "none";
      addressInputEl.style.display = "none";
      breadcrumbsListEl.style.display = "flex";
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".win11-address-bar")) {
      addressOmniDropdownEl.style.display = "none";
      if (addressInputEl && addressInputEl.style.display === "block") {
        addressInputEl.style.display = "none";
        if (breadcrumbsListEl) breadcrumbsListEl.style.display = "flex";
      }
    }
  }, { signal });

  function updateRibbonProjectExportButton() {
    const exportBtn = document.getElementById("win11-btn-export-folder");
    if (!exportBtn) return;

    const tab = getActiveTab();
    const p = tab ? (tab.path || "").replace(/\//g, "\\") : "";

    // Check if we are inside 02_Exports/.../<project_name>
    if (p.includes("02_Exports")) {
      const segments = p.split(/[\\/]/).filter(Boolean);
      const matched = (projectsList || []).find(proj => {
        const projName = proj.slug || proj.name;
        return segments.includes(projName) || segments.includes(proj.name);
      });

      if (matched) {
        exportBtn.innerHTML = `
          ${icons.folder}
          <span>Go to Project</span>
        `;
        exportBtn.title = `Jump directly to ${matched.name} root directory in 01_Projects`;
        exportBtn.setAttribute("data-target-project-path", matched.path);
        return;
      }
    }

    // Normal Project Export mode
    exportBtn.innerHTML = `
      ${icons.exportFolder}
      <span>Export Folder</span>
    `;
    exportBtn.title = "Open or generate Project Export Folder in a new tab";
    exportBtn.removeAttribute("data-target-project-path");
  }

  function renderSidebarCategories() {
    const catsTree = document.getElementById("win11-categories-tree");
    if (!catsTree) return;

    const cats = Object.keys(categoriesData).length ? Object.entries(categoriesData).filter(([, cat]) => cat.enabled !== false) : [
      ["Video", { name: "Video", icon: "video", physical_folder: "Video" }],
      ["Code", { name: "Code", icon: "code", physical_folder: "Code" }],
      ["Audio", { name: "Audio", icon: "audio", physical_folder: "Audio" }],
      ["AI", { name: "AI", icon: "ai", physical_folder: "AI" }],
      ["Design", { name: "Design", icon: "design", physical_folder: "Design" }],
      ["Photo", { name: "Photo", icon: "photo", physical_folder: "Photo" }]
    ];

    catsTree.innerHTML = `
      ${cats.map(([key, cat]) => {
        const catIcon = getCategoryIconSvg(cat.icon || key);
        const folderPath = cat.physical_folder || key;
        const displayName = cat.display_name || key;
        return `
          <li class="win11-tree-item" data-path="${escapeHtml(folderPath)}" data-category="${escapeHtml(key)}" title="${escapeHtml(cat.description || displayName)}">
            <span class="win11-tree-icon">${catIcon}</span>
            <span class="win11-tree-label">${escapeHtml(displayName)}</span>
            <span class="win11-tree-badge" id="badge-cat-${escapeHtml(key)}">0</span>
          </li>
        `;
      }).join("")}
      <li class="win11-tree-item" data-path="Clients" data-category="Clients" title="Client-tagged projects">
        <span class="win11-tree-icon">${icons.client}</span>
        <span class="win11-tree-label">Clients</span>
        <span class="win11-tree-badge" id="badge-cat-Clients">0</span>
      </li>
    `;

    updateSidebarBadges();
  }

  async function renderSidebarDrives() {
    const drivesTree = document.getElementById("win11-drives-tree");
    if (!drivesTree) return;

    let drivesList = [
      { name: "Projects Root (C:)", path: "" },
      { name: "Storage (D:)", path: "D:\\" },
      { name: "Media RAID (E:)", path: "E:\\" }
    ];

    try {
      const res = await api.getDrives();
      if (res && Array.isArray(res.drives) && res.drives.length > 0) {
        drivesList = [
          { name: "Projects Root (C:)", path: "" },
          ...res.drives.filter(d => !d.is_system).map(d => ({ name: d.name, path: d.path })),
          ...(res.external_mounts || []).map(m => ({ name: m.name, path: m.path }))
        ];
      }
    } catch (e) {
      console.warn("Could not fetch drives dynamically:", e);
    }

    const seen = new Set();
    const deduped = drivesList.filter(d => {
      if (seen.has(d.path)) return false;
      seen.add(d.path);
      return true;
    });

    drivesTree.innerHTML = deduped.map(d => `
      <li class="win11-tree-item" data-path="${escapeHtml(d.path)}" title="${escapeHtml(d.name)}">
        <span class="win11-tree-icon" style="color: var(--color-primary);">${icons.drive}</span>
        <span class="win11-tree-label">${escapeHtml(d.name)}</span>
      </li>
    `).join("");
  }

  function updateSidebarBadges() {
    if (!projectsList || !Array.isArray(projectsList)) return;
    const catCounts = { Clients: 0 };
    const clientSet = new Set();

    const cats = Object.keys(categoriesData).length ? Object.keys(categoriesData).filter(c => categoriesData[c].enabled !== false) : ["Video", "Code", "Audio", "AI", "Design", "Photo"];
    cats.forEach(c => { catCounts[c] = 0; });

    projectsList.forEach(p => {
      const cl = p.client && p.client !== "None" && p.client !== "internal" ? p.client : null;
      if (cl) clientSet.add(cl);

      let c = (p.type || p.category || "").toLowerCase();
      if (!c && p.path) {
        const norm = p.path.replace(/\\/g, "/");
        for (const catName of cats) {
          if (norm.toLowerCase().includes(`/${catName.toLowerCase()}/`)) {
            c = catName.toLowerCase();
            break;
          }
        }
      }

      let matched = false;
      for (const catName of cats) {
        if (c.includes(catName.toLowerCase())) {
          catCounts[catName] = (catCounts[catName] || 0) + 1;
          matched = true;
          break;
        }
      }
      if (!matched && cats.length > 0) {
        catCounts[cats[0]] = (catCounts[cats[0]] || 0) + 1;
      }
    });

    catCounts.Clients = clientSet.size || projectsList.filter(p => p.client && p.client !== "None").length;

    Object.entries(catCounts).forEach(([cat, count]) => {
      const el = document.getElementById(`badge-cat-${cat}`);
      if (el) el.textContent = String(count);
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Cold Archive View Renderer
  // ──────────────────────────────────────────────────────────────────────────
  async function renderArchiveView(container) {
    container.innerHTML = `
      <div class="win11-native-view-wrapper" style="padding: 1.25rem 1.5rem; height: 100%; overflow-y: auto;">
        <div class="page-header" style="margin-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
          <div>
            <div class="page-eyebrow">
              <span class="studio-status-indicator" style="background-color: var(--color-primary);"></span>
              <span>COLD STORAGE</span>
            </div>
            <h1 class="page-title">Cold Storage Archive</h1>
            <p class="page-description">Browse and resurrect inactive projects archived to secondary drive</p>
          </div>
          <button class="btn btn-secondary" id="win11-refresh-archive-btn">
            ${icons.refresh} Rescan Archive
          </button>
        </div>

        <div id="win11-archive-list-container">
          <div class="win11-canvas-loading">
            <div class="spinner"></div>
            <p>Loading archived projects...</p>
          </div>
        </div>
      </div>
    `;

    document.getElementById("win11-refresh-archive-btn")?.addEventListener("click", () => {
      loadArchiveData();
    });

    async function loadArchiveData() {
      const listContainer = document.getElementById("win11-archive-list-container");
      if (!listContainer) return;

      try {
        const archived = await api.getArchivedProjects();
        if (!archived || archived.length === 0) {
          listContainer.innerHTML = `
            <div class="win11-empty-canvas" style="padding: 3rem 1.5rem;">
              <div class="win11-empty-icon" style="color: var(--text-muted);">${icons.archive}</div>
              <h3>Cold Archive is Empty</h3>
              <p>No archived projects found in secondary storage.</p>
            </div>
          `;
          return;
        }

        listContainer.innerHTML = `
          <div class="win11-details-table-wrap" style="background: var(--surface-bg-card); border-radius: var(--radius-md); border: 1px solid var(--border-subtle); overflow: hidden;">
            <table class="win11-details-table font-mono" style="width: 100%; border-collapse: collapse;">
              <thead>
                <tr>
                  <th style="width: 35%; text-align: left; padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border-subtle);">Project Name</th>
                  <th style="width: 15%; text-align: left; padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border-subtle);">Category</th>
                  <th style="width: 15%; text-align: left; padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border-subtle);">Client</th>
                  <th style="width: 15%; text-align: left; padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border-subtle);">Archived Date</th>
                  <th style="width: 20%; text-align: right; padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border-subtle);">Action</th>
                </tr>
              </thead>
              <tbody>
                ${archived.map(p => `
                  <tr class="win11-table-row" style="border-bottom: 1px solid var(--border-subtle);">
                    <td style="padding: 0.6rem 0.85rem;">
                      <div class="win11-details-cell-name" style="display: flex; align-items: center; gap: 0.5rem;">
                        <span class="win11-file-icon">${getCategoryIconSvg(p.type || "Video")}</span>
                        <div style="display: flex; flex-direction: column;">
                          <span style="font-weight: 600; color: var(--text-primary);">${escapeHtml(p.name)}</span>
                          <span style="font-size: 0.7rem; color: var(--text-muted);">${escapeHtml(p.relative_path || p.path)}</span>
                        </div>
                      </div>
                    </td>
                    <td style="padding: 0.6rem 0.85rem;">
                      <span class="badge font-mono">${escapeHtml(p.type || "Video")}</span>
                    </td>
                    <td style="padding: 0.6rem 0.85rem;">
                      <span>${escapeHtml(p.client || "—")}</span>
                    </td>
                    <td style="padding: 0.6rem 0.85rem;">
                      <span style="font-size: 0.75rem; color: var(--text-muted);">${p.created || '—'}</span>
                    </td>
                    <td style="padding: 0.6rem 0.85rem; text-align: right;">
                      <button class="btn btn-primary btn-resurrect-proj" data-proj-name="${escapeHtml(p.name)}" style="font-size: 0.75rem; padding: 0.25rem 0.65rem;">
                        ${icons.refresh} Resurrect
                      </button>
                    </td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;

        listContainer.querySelectorAll(".btn-resurrect-proj").forEach(btn => {
          btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const projName = btn.getAttribute("data-proj-name");
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px;"></span> Resurrecting...`;

            try {
              await api.resurrectProject(projName);
              showToast(`Project '${projName}' resurrected to active workspace!`, "success");
              loadArchiveData();
            } catch (err) {
              showToast(`Resurrect failed: ${err.message}`, "error");
              btn.disabled = false;
              btn.innerHTML = `${icons.refresh} Resurrect`;
            }
          });
        });
      } catch (err) {
        listContainer.innerHTML = `
          <div class="win11-empty-canvas">
            <div class="win11-empty-icon" style="color: var(--color-danger);">${icons.warning}</div>
            <h3>Unable to Read Cold Archive</h3>
            <p>${escapeHtml(err.message)}</p>
          </div>
        `;
      }
    }

    loadArchiveData();
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Main Directory Loader
  // ──────────────────────────────────────────────────────────────────────────
  async function loadCurrentDirectory() {
    const loadId = ++directoryLoadId;
    const tab = getActiveTab();
    if (!tab) return;
    selectedItem = null;
    const tabId = tab.id;
    const targetPath = tab.path || "";
    const isStaleLoad = () => {
      const activeTab = getActiveTab();
      return signal.aborted || loadId !== directoryLoadId || !activeTab || activeTab.id !== tabId || activeTab.path !== targetPath;
    };

    // Handle in-app Studio Tools views directly inside Windows 11 Explorer canvas
    if (targetPath === "storage" || targetPath === "sys://storage") {
      renderBreadcrumbs("01_Projects/Storage_Inventory", "Storage Inventory");
      if (statusCountEl) statusCountEl.textContent = "Storage Analytics & Inventory";
      if (statusSelectionEl) statusSelectionEl.textContent = "Visualizer Ready";
      if (searchInputEl) searchInputEl.placeholder = "Filter storage...";
      canvasEl.innerHTML = `<div class="win11-native-view-wrapper" style="padding: 1.25rem 1.5rem; height: 100%; overflow-y: auto;"></div>`;
      await renderStorage(canvasEl.querySelector(".win11-native-view-wrapper"));
      return;
    }

    if (targetPath === "settings" || targetPath === "sys://settings") {
      renderBreadcrumbs("01_Projects/Studio_Settings", "Settings & Configuration");
      if (statusCountEl) statusCountEl.textContent = "Configuration";
      if (statusSelectionEl) statusSelectionEl.textContent = "Preferences & Sync";
      if (searchInputEl) searchInputEl.placeholder = "Search settings...";
      canvasEl.innerHTML = `<div class="win11-native-view-wrapper" style="padding: 1.25rem 1.5rem; height: 100%; overflow-y: auto;"></div>`;
      await renderSettings(canvasEl.querySelector(".win11-native-view-wrapper"));
      return;
    }

    if (targetPath === "archive" || targetPath === "sys://archive") {
      renderBreadcrumbs("01_Projects/Cold_Archive", "Archive");
      if (statusCountEl) statusCountEl.textContent = "Cold Storage";
      if (statusSelectionEl) statusSelectionEl.textContent = "Inactive Projects";
      if (searchInputEl) searchInputEl.placeholder = "Search archived projects...";
      await renderArchiveView(canvasEl);
      return;
    }

    // Check per-folder view mode memory
    if (viewMode !== "split" && viewMode !== "media") {
      viewMode = folderViewMap[targetPath] || lastGlobalView;
      updateViewButtons();
    }

    // Update navigation button states
    if (navBackBtn) navBackBtn.disabled = tab.historyIndex <= 0;
    if (navForwardBtn) navForwardBtn.disabled = tab.historyIndex >= tab.history.length - 1;

    // Highlight active sidebar item
    document.querySelectorAll(".win11-tree-item").forEach(item => {
      const p = item.getAttribute("data-path");
      if (p === targetPath || (p === "" && !targetPath)) {
        item.classList.add("active");
      } else {
        item.classList.remove("active");
      }
    });

    if (viewMode === "split") {
      renderDualPaneView();
      return;
    }

    if (viewMode === "media") {
      renderMediaScrubberView();
      return;
    }

    if (canvasEl) {
      canvasEl.innerHTML = `
        <div class="win11-canvas-loading">
          <div class="spinner"></div>
          <p>Scanning directory contents...</p>
        </div>
      `;
    }

    try {
      const res = await api.listFiles(targetPath);
      if (isStaleLoad()) return;
      currentEntries = res.entries || [];
      currentParentPath = res.parent_path || null;

      if (navUpBtn) navUpBtn.disabled = !currentParentPath;

      renderBreadcrumbs(res.current_path, res.relative_display);
      renderCanvasEntries();
      updateRibbonProjectExportButton();

      const folderName = tab.title || (res.current_path ? res.current_path.split(/[\\/]/).filter(Boolean).pop() : 'Folder');
      if (searchInputEl) {
        searchInputEl.placeholder = `Search ${folderName || 'Folder'}...`;
      }

      if (statusCountEl) {
        statusCountEl.textContent = `${currentEntries.length} item${currentEntries.length === 1 ? '' : 's'}`;
      }

      // Automatically select previous selected item in this folder if remembered, else first item
      let itemToSelect = null;
      if (lastSelectedInFolder[targetPath]) {
        itemToSelect = currentEntries.find(e => e.name === lastSelectedInFolder[targetPath]);
      }
      if (!itemToSelect && currentEntries.length > 0) {
        itemToSelect = currentEntries[0];
      }

      selectCanvasItem(itemToSelect);

      if (itemToSelect) {
        setTimeout(() => {
          const el = canvasEl.querySelector(`[data-path="${CSS.escape(itemToSelect.path)}"]`);
          el?.scrollIntoView({ block: "nearest" });
        }, 50);
      }
    } catch (err) {
      if (isStaleLoad()) return;
      if (canvasEl) {
        canvasEl.innerHTML = `
          <div class="win11-empty-canvas">
            <div class="win11-empty-icon" style="color: var(--color-danger);">${icons.warning}</div>
            <h3>Unable to Access Directory</h3>
            <p>${escapeHtml(err.message)}</p>
            <button class="btn btn-secondary" id="win11-btn-reset-root">Return to Projects Root</button>
          </div>
        `;
        document.getElementById("win11-btn-reset-root")?.addEventListener("click", () => {
          updateActiveTabPath("");
        });
      }
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Zone 2 Canvas Renderers: View 1 (Grid) & View 2 (Details)
  // ──────────────────────────────────────────────────────────────────────────
  function sortEntries(entries) {
    return [...entries].sort((a, b) => {
      if (a.is_dir && !b.is_dir) return -1;
      if (!a.is_dir && b.is_dir) return 1;

      let comp = 0;
      if (sortField === "name") {
        comp = (a.name || "").localeCompare(b.name || "", undefined, { numeric: true, sensitivity: "base" });
      } else if (sortField === "type") {
        const typeA = a.is_dir ? "Folder" : (a.type || a.extension || "");
        const typeB = b.is_dir ? "Folder" : (b.type || b.extension || "");
        comp = typeA.localeCompare(typeB, undefined, { numeric: true, sensitivity: "base" });
      } else if (sortField === "size") {
        comp = (a.size || 0) - (b.size || 0);
      } else if (sortField === "modified") {
        const dA = a.modified ? new Date(a.modified).getTime() : 0;
        const dB = b.modified ? new Date(b.modified).getTime() : 0;
        comp = dA - dB;
      }
      return sortDir === "desc" ? -comp : comp;
    });
  }

  function renderCanvasEntries() {
    if (!canvasEl) return;

    const query = (searchInputEl?.value || "").toLowerCase().trim();
    let filtered = currentEntries.filter(e => {
      if (!query) return true;
      return e.name.toLowerCase().includes(query) || (e.type && e.type.toLowerCase().includes(query));
    });

    filtered = sortEntries(filtered);

    if (filtered.length === 0) {
      canvasEl.innerHTML = `
        <div class="win11-empty-canvas">
          <div class="win11-empty-icon">${icons.folder}</div>
          <h3>${query ? 'No matching items found' : 'This folder is empty'}</h3>
          <p>${query ? `No files matching "${escapeHtml(query)}" in this directory` : 'Create a new project or drop assets into this folder'}</p>
        </div>
      `;
      return;
    }

    if (viewMode === "grid") {
      canvasEl.innerHTML = `
        <div class="win11-grid-view">
          ${filtered.map(entry => {
            const isDir = entry.is_dir;
            const isSel = selectedItem && selectedItem.path === entry.path;
            const ext = (entry.extension || "").toLowerCase().replace(/^\./, "");
            const isImg = ["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(ext);

            let previewHtml = "";
            if (isDir) {
              previewHtml = icons.folderLarge;
            } else if (isImg) {
              previewHtml = `<img src="${api.getRawFileUrl(entry.path)}" class="win11-tile-img-thumb" loading="lazy" alt="" />`;
            } else {
              previewHtml = `<div class="win11-tile-icon-wrap">${getFileIconSvg(entry.extension, false)}</div>`;
            }

            return `
              <div class="win11-file-tile ${isDir ? 'is-folder' : 'is-file'} ${isSel ? 'is-selected' : ''}" data-path="${entry.path}" data-isdir="${isDir}" tabindex="0" role="button" title="${escapeHtml(entry.name)}">
                <div class="win11-tile-preview">
                  ${previewHtml}
                </div>
                <div class="win11-tile-name">${escapeHtml(formatGridItemName(entry.name, isDir))}</div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    } else {
      // Details Table View
      canvasEl.innerHTML = `
        <div class="win11-table-wrapper">
          <table class="win11-details-table">
            <thead>
              <tr>
                <th class="col-sortable col-name ${sortField === 'name' ? 'sorted' : ''}" data-sort="name">
                  <span>Name</span>
                  ${sortField === 'name' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="col-sortable col-date ${sortField === 'modified' ? 'sorted' : ''}" data-sort="modified">
                  <span>Date modified</span>
                  ${sortField === 'modified' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="col-sortable col-type ${sortField === 'type' ? 'sorted' : ''}" data-sort="type">
                  <span>Type</span>
                  ${sortField === 'type' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="col-sortable col-size ${sortField === 'size' ? 'sorted' : ''}" data-sort="size">
                  <span>Size</span>
                  ${sortField === 'size' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              </tr>
            </thead>
            <tbody>
              ${filtered.map(entry => {
                const isDir = entry.is_dir;
                const iconSvg = getFileIconSvg(entry.extension, isDir);
                const isSel = selectedItem && selectedItem.path === entry.path;
                const sizeStr = isDir ? "" : formatBytes(entry.size);
                const modDate = entry.modified ? entry.modified.substring(0, 19).replace("T", " ") : "—";
                const typeStr = isDir ? "File folder" : (entry.type ? `${entry.type.toUpperCase()} file` : "File");

                return `
                  <tr class="win11-table-row ${isDir ? 'is-folder' : 'is-file'} ${isSel ? 'is-selected' : ''}" data-path="${entry.path}" data-isdir="${isDir}" tabindex="0" role="button">
                    <td class="col-name">
                      <div class="win11-name-cell">
                        <span class="win11-cell-icon">${iconSvg}</span>
                        <span class="win11-cell-text font-mono" title="${entry.name}">${escapeHtml(entry.name)}</span>
                      </div>
                    </td>
                    <td class="col-date font-mono">${modDate}</td>
                    <td class="col-type font-mono">${typeStr}</td>
                    <td class="col-size font-mono">${sizeStr}</td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      `;

      // Header sorting handlers
      canvasEl.querySelectorAll("th.col-sortable").forEach(th => {
        th.addEventListener("click", () => {
          const field = th.getAttribute("data-sort");
          if (sortField === field) {
            sortDir = sortDir === "asc" ? "desc" : "asc";
          } else {
            sortField = field;
            sortDir = (field === "size" || field === "modified") ? "desc" : "asc";
          }
          localStorage.setItem("cos_win11_sort_field", sortField);
          localStorage.setItem("cos_win11_sort_dir", sortDir);
          renderCanvasEntries();
        });
      });
    }

    // Attach Selection & Navigation handlers to tiles / rows
    canvasEl.querySelectorAll(".win11-file-tile, .win11-table-row").forEach(el => {
      const p = el.getAttribute("data-path");
      const isDir = el.getAttribute("data-isdir") === "true";
      const entry = currentEntries.find(e => e.path === p);

      el.addEventListener("click", () => {
        if (entry) selectCanvasItem(entry);
      });

      el.addEventListener("dblclick", () => {
        if (isDir) {
          updateActiveTabPath(p);
        } else {
          api.openPath(p).catch(err => showToast(`Cannot open: ${err.message}`, "error"));
        }
      });

      el.addEventListener("contextmenu", (e) => {
        if (entry) showContextMenu(e, entry);
      });

      el.addEventListener("keydown", (e) => {
        if (e.key === " ") {
          e.preventDefault();
          if (entry) selectCanvasItem(entry);
        } else if (e.key === "Enter") {
          e.preventDefault();
          if (isDir) updateActiveTabPath(p);
          else api.openPath(p).catch(err => showToast(`Cannot open: ${err.message}`, "error"));
        }
      });
    });
  }

  function selectCanvasItem(entry) {
    selectedItem = entry;

    canvasEl.querySelectorAll(".win11-file-tile, .win11-table-row").forEach(el => {
      if (entry && el.getAttribute("data-path") === entry.path) {
        el.classList.add("is-selected");
      } else {
        el.classList.remove("is-selected");
      }
    });

    if (statusSelectionEl) {
      if (entry) {
        statusSelectionEl.textContent = `Selected: ${entry.name} (${entry.is_dir ? 'Folder' : formatBytes(entry.size)})`;
      } else {
        statusSelectionEl.textContent = "No item selected";
      }
    }

    if (showZone3) {
      renderInspector(entry);
    }
  }

  // Windows 11 Native Context Menu Handler
  function showContextMenu(e, item) {
    e.preventDefault();
    const menuEl = document.getElementById("win11-context-menu");
    if (!menuEl) return;

    selectCanvasItem(item);

    const isDir = item.is_dir;
    const isProj = projectsList.find(p => p.path === item.path || p.name === item.name || p.slug === item.name);

    menuEl.innerHTML = `
      <div class="win11-context-item" data-action="open">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        <span>${isDir ? 'Open Folder' : 'Open in Native OS'}</span>
      </div>
      ${isDir ? `
        <div class="win11-context-item" data-action="open-new-tab">
          ${icons.folder}
          <span>Open in New Tab</span>
        </div>
      ` : ''}
      <div class="win11-context-item" data-action="open-native">
        ${icons.externalLink}
        <span>${isDir ? 'Reveal in File Explorer' : 'Open in Default Application'}</span>
      </div>
      <div class="win11-context-item" data-action="copy-path">
        ${icons.copy}
        <span>Copy Full Path</span>
      </div>
      <div class="win11-context-divider"></div>
      ${isProj ? `
        <div class="win11-context-item" data-action="export-folder">
          ${icons.exportFolder}
          <span>Export Folder</span>
        </div>
        <div class="win11-context-item" data-action="shuttle">
          ${icons.travel}
          <span>Shuttle Travel</span>
        </div>
        <div class="win11-context-item" data-action="reclaim">
          ${icons.zap}
          <span>Reclaim Project Cache</span>
        </div>
        <div class="win11-context-item" data-action="sync">
          ${icons.sync}
          <span>Live Vault Sync</span>
        </div>
        <div class="win11-context-item danger" data-action="archive">
          ${icons.archive}
          <span>Move to Cold Archive</span>
        </div>
      ` : `
        <div class="win11-context-item" data-action="bulk-reclaim">
          ${icons.zap}
          <span>Bulk Reclaim Cache</span>
        </div>
      `}
      <div class="win11-context-divider"></div>
      <div class="win11-context-item danger" data-action="delete" style="color: var(--color-danger);">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
        <span>Delete</span>
        <span class="win11-context-shortcut font-mono" style="margin-left: auto; font-size: 0.7rem; color: var(--text-muted); opacity: 0.8;">Del</span>
      </div>
      <div class="win11-context-divider"></div>
      <div class="win11-context-item" data-action="details">
        ${icons.info}
        <span>Properties / Inspect</span>
      </div>
    `;

    const x = Math.min(e.clientX, window.innerWidth - 220);
    const y = Math.min(e.clientY, window.innerHeight - 300);
    menuEl.style.left = `${x}px`;
    menuEl.style.top = `${y}px`;
    menuEl.style.display = "block";

    menuEl.querySelectorAll(".win11-context-item").forEach(el => {
      el.addEventListener("click", () => {
        const action = el.getAttribute("data-action");
        menuEl.style.display = "none";
        if (action === "open") {
          if (isDir) updateActiveTabPath(item.path);
          else api.openPath(item.path);
        } else if (action === "open-new-tab") {
          createNewTab(item.path);
        } else if (action === "open-native") {
          api.openPath(item.path);
          showToast(`Opened in default Windows application`, "info", 1200);
        } else if (action === "copy-path") {
          navigator.clipboard.writeText(item.path);
          showToast("Copied path to clipboard!", "success", 1200);
        } else if (action === "export-folder") {
          showToast(`Generating export folder for ${isProj.name}...`, "info", 1200);
          api.createExportFolder(isProj.slug || isProj.name).then(res => {
            showToast(`Export folder ready at ${res.export_path}`, "success", 2000);
            if (res.export_path) {
              createNewTab(res.export_path);
            }
          }).catch(err => showToast(`Failed: ${err.message}`, "error"));
        } else if (action === "shuttle") {
          openConfirmModal({
            title: "Export to Shuttle Drive",
            message: `Sync project '${isProj.name}' to your connected external Shuttle Drive?`,
            confirmText: "Launch Travel",
            variant: "info",
            onConfirm: async () => {
              const res = await api.travelProject(isProj.slug || isProj.name);
              showToast(`Exported to Shuttle: ${res.dest_path}`, "success");
            }
          });
        } else if (action === "reclaim") {
          openReclaimModal(isProj, () => loadCurrentDirectory());
        } else if (action === "sync") {
          openLiveSyncModal(() => loadCurrentDirectory());
        } else if (action === "archive") {
          openConfirmModal({
            title: "Move to Cold Archive",
            message: `Move '${item.name}' out of active studio into Cold Storage?`,
            confirmText: "Archive",
            variant: "danger",
            onConfirm: async () => {
              const res = await api.archiveProject(isProj.slug || item.name);
              showToast(`Archived to ${res.archive_path}`, "success");
              loadCurrentDirectory();
            }
          });
        } else if (action === "bulk-reclaim") {
          openBulkReclaimModal(storageData || { projects: projectsList }, () => loadCurrentDirectory());
        } else if (action === "delete") {
          const itemType = isProj ? "Project" : (isDir ? "Folder" : "File");
          openConfirmModal({
            title: `Delete ${itemType}`,
            message: `Are you sure you want to delete "${item.name}"?`,
            subtext: "This will move the item to the Windows Recycle Bin.",
            confirmText: "Delete",
            variant: "danger",
            onConfirm: async () => {
              try {
                await api.deletePath(item.path);
                showToast(`Moved '${item.name}' to Recycle Bin`, "info", 2000);
                loadCurrentDirectory();
                updateSidebarBadges();
              } catch (err) {
                showToast(`Failed to delete: ${err.message}`, "error");
              }
            }
          });
        } else if (action === "details") {
          if (isProj) {
            openProjectInspector(isProj, categoriesData, () => loadCurrentDirectory());
          } else {
            showZone3 = true;
            localStorage.setItem("cos_win11_show_inspector", "true");
            if (inspectorEl) inspectorEl.style.display = "block";
            workspaceLayoutEl?.classList.add("with-inspector");
            document.getElementById("win11-btn-toggle-inspector")?.classList.add("active");
            renderInspector(item);
          }
        }
      });
    });
  }

  document.addEventListener("click", () => {
    const menuEl = document.getElementById("win11-context-menu");
    if (menuEl) menuEl.style.display = "none";
  }, { signal });

  // ──────────────────────────────────────────────────────────────────────────
  // View 3: Dual-Pane External RAID Bridge (Side-by-side Ingest)
  // ──────────────────────────────────────────────────────────────────────────
  function renderDualPaneView() {
    if (!canvasEl) return;

    const tab = getActiveTab();
    if (tab.path) {
      dualRightPath = tab.path;
      localStorage.setItem("cos_dual_right_path", dualRightPath);
    }

    const sourcePresets = [
      { name: "Downloads", path: "Downloads" },
      { name: "Desktop", path: "Desktop" },
      { name: "Documents", path: "Documents" },
      ...(configData?.external_mounts?.map(m => ({ name: m.name, path: m.path })) || [
        { name: "Drive (D:)", path: "D:\\" },
        { name: "Drive (E:)", path: "E:\\" }
      ])
    ];

    const projectsRoot = configData?.paths?.projects_path?.path || configData?.config?.projects_path || "";
    const projectDestination = (folder = "") => {
      if (!folder) return projectsRoot;
      const separator = projectsRoot.includes("\\") ? "\\" : "/";
      return projectsRoot ? `${projectsRoot.replace(/[\\/]$/, "")}${separator}${folder}` : folder;
    };
    const targetPresets = [
      { name: "Projects Root", path: projectDestination() },
      ...(Object.keys(categoriesData).length ? Object.entries(categoriesData).filter(([, c]) => c.enabled !== false).map(([k, c]) => ({
        name: c.display_name || k,
        path: projectDestination(c.physical_folder || k)
      })) : [
        { name: "Video", path: projectDestination("Video") },
        { name: "Code", path: projectDestination("Code") }
      ]),
      { name: "02_Exports", path: "02_Exports" }
    ];

    canvasEl.innerHTML = `
      <div class="win11-dual-pane-container">
        <!-- Dual Pane Control Bar -->
        <div class="win11-dual-top-bar">
          <div class="win11-dual-status">
            <div class="win11-dual-tag">
              ${icons.columns}
              <span>DUAL-PANE RAID INGEST BRIDGE</span>
            </div>
            <div class="win11-dual-desc">
              Select footage from Source Drive (left) to transfer directly into your active workspace project (right).
            </div>
          </div>
          <div class="win11-dual-controls">
            <label class="win11-dual-opt">
              <input type="checkbox" id="dual-mode-move" ${dualMoveMode ? 'checked' : ''} />
              <span>Move (cut) instead of copy</span>
            </label>
            <label class="win11-dual-opt">
              <input type="checkbox" id="dual-mode-overwrite" ${dualOverwrite ? 'checked' : ''} />
              <span>Overwrite existing</span>
            </label>
            <button class="btn btn-primary" id="dual-execute-ingest-btn" disabled>
              ${icons.zap}
              <span id="dual-ingest-btn-text">Ingest Selected</span>
            </button>
            <button class="btn btn-secondary" id="win11-exit-dual-btn" title="Exit Split View">
              ${icons.x}
              <span>Exit</span>
            </button>
          </div>
        </div>

        <!-- Side-by-Side Dual Panes -->
        <div class="win11-dual-panes-split">
          <!-- Left Pane (Source Drive) -->
          <div class="win11-dual-pane source-pane" id="win11-dual-left-pane">
            <div class="win11-pane-header">
              <div class="win11-pane-title">
                <span style="color: var(--color-primary);">${icons.drive}</span>
                <span>Source Drive / Ingest Media</span>
              </div>
              <div class="win11-pane-path-bar">
                <button class="win11-nav-btn" id="dual-left-up-btn" title="Up to Parent">${icons.arrowUp}</button>
                <input type="text" class="win11-pane-input font-mono" id="dual-left-path-inp" value="${escapeHtml(dualLeftPath)}" placeholder="Downloads, D:\\, E:\\..." />
                <button class="win11-nav-btn" id="dual-left-refresh-btn" title="Refresh Source">${icons.refresh}</button>
              </div>
            </div>
            <div class="win11-pane-presets">
              <span style="font-size: 0.65rem; font-weight: 700; color: var(--text-muted); margin-right: 0.25rem;">SOURCES:</span>
              ${sourcePresets.slice(0, 5).map(sp => `
                <button class="win11-pane-preset-btn" data-set-left="${escapeHtml(sp.path)}">${escapeHtml(sp.name)}</button>
              `).join("")}
            </div>
            <div class="win11-pane-body" id="dual-left-body">
              <div class="spinner"></div>
            </div>
          </div>

          <!-- Right Pane (Destination Project Workspace) -->
          <div class="win11-dual-pane" id="win11-dual-right-pane">
            <div class="win11-pane-header">
              <div class="win11-pane-title">
                <span style="color: var(--color-success);">${icons.folder}</span>
                <span>Destination Workspace Project</span>
              </div>
              <div class="win11-pane-path-bar">
                <button class="win11-nav-btn" id="dual-right-up-btn" title="Up to Parent">${icons.arrowUp}</button>
                <input type="text" class="win11-pane-input font-mono" id="dual-right-path-inp" value="${escapeHtml(dualRightPath)}" placeholder="01_Projects\\Video\\..." />
                <button class="win11-nav-btn" id="dual-right-refresh-btn" title="Refresh Destination">${icons.refresh}</button>
              </div>
            </div>
            <div class="win11-pane-presets">
              <span style="font-size: 0.65rem; font-weight: 700; color: var(--text-muted); margin-right: 0.25rem;">TARGETS:</span>
              ${targetPresets.slice(0, 5).map(tp => `
                <button class="win11-pane-preset-btn" data-set-right="${escapeHtml(tp.path)}">${escapeHtml(tp.name)}</button>
              `).join("")}
            </div>
            <div class="win11-pane-body" id="dual-right-body">
              <div class="spinner"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Attach Dual Pane Handlers
    const leftInp = document.getElementById("dual-left-path-inp");
    const rightInp = document.getElementById("dual-right-path-inp");
    const leftRefresh = document.getElementById("dual-left-refresh-btn");
    const rightRefresh = document.getElementById("dual-right-refresh-btn");
    const leftUp = document.getElementById("dual-left-up-btn");
    const rightUp = document.getElementById("dual-right-up-btn");
    const ingestBtn = document.getElementById("dual-execute-ingest-btn");
    const exitBtn = document.getElementById("win11-exit-dual-btn");
    const moveCheck = document.getElementById("dual-mode-move");
    const overCheck = document.getElementById("dual-mode-overwrite");

    let leftParentPath = null;
    let rightParentPath = null;

    exitBtn?.addEventListener("click", () => {
      setViewMode(lastGlobalView === "split" ? "grid" : (lastGlobalView || "grid"));
    });

    moveCheck?.addEventListener("change", () => { dualMoveMode = moveCheck.checked; });
    overCheck?.addEventListener("change", () => { dualOverwrite = overCheck.checked; });

    leftInp?.addEventListener("change", () => {
      dualLeftPath = leftInp.value.trim();
      localStorage.setItem("cos_dual_left_path", dualLeftPath);
      loadDualLeft();
    });

    rightInp?.addEventListener("change", () => {
      dualRightPath = rightInp.value.trim();
      localStorage.setItem("cos_dual_right_path", dualRightPath);
      syncTargetTabPath(dualRightPath);
      loadDualRight();
    });

    leftRefresh?.addEventListener("click", loadDualLeft);
    rightRefresh?.addEventListener("click", loadDualRight);

    leftUp?.addEventListener("click", () => {
      if (leftParentPath) {
        dualLeftPath = leftParentPath;
        if (leftInp) leftInp.value = dualLeftPath;
        localStorage.setItem("cos_dual_left_path", dualLeftPath);
        loadDualLeft();
      }
    });

    rightUp?.addEventListener("click", () => {
      if (rightParentPath) {
        dualRightPath = rightParentPath;
        if (rightInp) rightInp.value = dualRightPath;
        localStorage.setItem("cos_dual_right_path", dualRightPath);
        syncTargetTabPath(dualRightPath);
        loadDualRight();
      }
    });

    // Preset Buttons
    document.querySelectorAll("[data-set-left]").forEach(btn => {
      btn.addEventListener("click", () => {
        const val = btn.getAttribute("data-set-left");
        dualLeftPath = val;
        if (leftInp) leftInp.value = dualLeftPath;
        localStorage.setItem("cos_dual_left_path", dualLeftPath);
        loadDualLeft();
      });
    });

    document.querySelectorAll("[data-set-right]").forEach(btn => {
      btn.addEventListener("click", () => {
        const val = btn.getAttribute("data-set-right");
        dualRightPath = val;
        if (rightInp) rightInp.value = dualRightPath;
        localStorage.setItem("cos_dual_right_path", dualRightPath);
        syncTargetTabPath(dualRightPath);
        loadDualRight();
      });
    });

    function syncTargetTabPath(targetP) {
      const activeTab = getActiveTab();
      if (activeTab) {
        activeTab.path = targetP || "";
        activeTab.title = targetP ? targetP.split(/[\\/]/).filter(Boolean).pop() || "Folder" : "01_Projects";
        saveTabsSession();
        renderTabsBar();
        renderBreadcrumbs(targetP);
      }
    }

    async function loadDualLeft() {
      const body = document.getElementById("dual-left-body");
      if (!body) return;
      body.innerHTML = `<div class="win11-canvas-loading"><div class="spinner"></div></div>`;
      try {
        const res = await api.listFiles(dualLeftPath);
        dualLeftEntries = res.entries || [];
        leftParentPath = res.parent_path || null;
        if (leftUp) leftUp.disabled = !leftParentPath;
        dualLeftSelected = [];
        updateIngestBtn();

        body.innerHTML = `
          <div class="win11-pane-table-wrapper">
            <table class="win11-details-table">
              <thead>
                <tr>
                  <th style="width: 32px;"><input type="checkbox" id="dual-left-select-all" /></th>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                ${dualLeftEntries.map(e => `
                  <tr class="win11-dual-row ${e.is_dir ? 'is-folder' : 'is-file'}" data-path="${e.path}" data-isdir="${e.is_dir}">
                    <td style="width: 32px;"><input type="checkbox" class="dual-left-item-cb" data-path="${e.path}" /></td>
                    <td>
                      <div class="win11-name-cell">
                        <span class="win11-cell-icon">${getFileIconSvg(e.extension, e.is_dir)}</span>
                        <span class="win11-cell-text font-mono" title="${escapeHtml(e.name)}">${escapeHtml(e.name)}</span>
                      </div>
                    </td>
                    <td class="font-mono">${e.is_dir ? '—' : formatBytes(e.size)}</td>
                    <td class="font-mono">${e.is_dir ? 'Folder' : (e.type || 'File')}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;

        const selectAll = document.getElementById("dual-left-select-all");
        selectAll?.addEventListener("change", () => {
          body.querySelectorAll(".dual-left-item-cb").forEach(cb => {
            cb.checked = selectAll.checked;
          });
          dualLeftSelected = selectAll.checked ? dualLeftEntries.map(e => e.path) : [];
          updateIngestBtn();
        });

        body.querySelectorAll(".dual-left-item-cb").forEach(cb => {
          cb.addEventListener("change", (e) => {
            e.stopPropagation();
            const p = cb.getAttribute("data-path");
            if (cb.checked) {
              dualLeftSelected.push(p);
            } else {
              dualLeftSelected = dualLeftSelected.filter(item => item !== p);
            }
            updateIngestBtn();
          });
        });

        // Folder click in Left Pane
        body.querySelectorAll(".win11-dual-row").forEach(row => {
          row.addEventListener("click", (e) => {
            if (e.target.closest(".dual-left-item-cb")) return;
            const isDir = row.getAttribute("data-isdir") === "true";
            const p = row.getAttribute("data-path");
            if (isDir && p) {
              dualLeftPath = p;
              if (leftInp) leftInp.value = dualLeftPath;
              localStorage.setItem("cos_dual_left_path", dualLeftPath);
              loadDualLeft();
            }
          });
        });
      } catch (e) {
        body.innerHTML = `<div class="win11-empty-canvas"><p style="color: var(--color-danger);">${escapeHtml(e.message)}</p></div>`;
      }
    }

    async function loadDualRight() {
      const body = document.getElementById("dual-right-body");
      if (!body) return;
      body.innerHTML = `<div class="win11-canvas-loading"><div class="spinner"></div></div>`;
      try {
        const res = await api.listFiles(dualRightPath);
        dualRightEntries = res.entries || [];
        rightParentPath = res.parent_path || null;
        if (rightUp) rightUp.disabled = !rightParentPath;

        body.innerHTML = `
          <div class="win11-pane-table-wrapper">
            <table class="win11-details-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Date Modified</th>
                </tr>
              </thead>
              <tbody>
                ${dualRightEntries.map(e => `
                  <tr class="win11-dual-row ${e.is_dir ? 'is-folder' : 'is-file'}" data-path="${e.path}" data-isdir="${e.is_dir}">
                    <td>
                      <div class="win11-name-cell">
                        <span class="win11-cell-icon">${getFileIconSvg(e.extension, e.is_dir)}</span>
                        <span class="win11-cell-text font-mono" title="${escapeHtml(e.name)}">${escapeHtml(e.name)}</span>
                      </div>
                    </td>
                    <td class="font-mono">${e.is_dir ? '—' : formatBytes(e.size)}</td>
                    <td class="font-mono">${e.modified ? e.modified.substring(0, 10) : '—'}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;

        // Folder click in Right Pane
        body.querySelectorAll(".win11-dual-row").forEach(row => {
          row.addEventListener("click", () => {
            const isDir = row.getAttribute("data-isdir") === "true";
            const p = row.getAttribute("data-path");
            if (isDir && p) {
              dualRightPath = p;
              if (rightInp) rightInp.value = dualRightPath;
              localStorage.setItem("cos_dual_right_path", dualRightPath);
              syncTargetTabPath(dualRightPath);
              loadDualRight();
            }
          });
        });
      } catch (e) {
        body.innerHTML = `<div class="win11-empty-canvas"><p style="color: var(--color-danger);">${escapeHtml(e.message)}</p></div>`;
      }
    }

    function updateIngestBtn() {
      if (!ingestBtn) return;
      const count = dualLeftSelected.length;
      ingestBtn.disabled = count === 0;
      ingestBtn.innerHTML = `
        ${icons.download}
        <span>Ingest ${count} Selected Item${count === 1 ? '' : 's'}</span>
      `;
    }

    ingestBtn?.addEventListener("click", async () => {
      if (dualLeftSelected.length === 0) return;
      if (!dualRightPath || !dualRightPath.trim()) {
        showToast("Please enter or select a destination project folder in the right pane.", "warning");
        return;
      }
      ingestBtn.disabled = true;
      ingestBtn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Ingesting...`;

      let transferredCount = 0;
      for (const src of dualLeftSelected) {
        try {
          await api.transferFiles({
            source: src,
            destination: dualRightPath || "",
            move: dualMoveMode,
            overwrite: dualOverwrite,
          });
          transferredCount++;
        } catch (err) {
          showToast(`Ingest failed for ${src}: ${err.message}`, "error");
        }
      }

      showToast(`Successfully ingested ${transferredCount} item(s)!`, "success");
      loadDualLeft();
      loadDualRight();
    });

    loadDualLeft();
    loadDualRight();
  }

  // ──────────────────────────────────────────────────────────────────────────
  // View 4: 4K Media Scrubber & Waveform Player
  // ──────────────────────────────────────────────────────────────────────────
  async function renderMediaScrubberView() {
    if (!canvasEl) return;

    const tab = getActiveTab();
    canvasEl.innerHTML = `
      <div class="win11-media-player-view">
        <div class="win11-media-sidebar">
          <div class="win11-section-header"><span>MEDIA ASSETS IN FOLDER</span></div>
          <div class="win11-media-list" id="win11-media-assets-list">
            <div class="spinner"></div>
          </div>
        </div>
        <div class="win11-media-stage" id="win11-media-stage">
          <div class="win11-empty-canvas">
            <div class="win11-empty-icon" style="color: var(--color-accent-cyan);">${icons.video}</div>
            <h3>Select a media asset from the playlist</h3>
          </div>
        </div>
      </div>
    `;

    try {
      const res = await api.listFiles(tab.path);
      const mediaList = (res.entries || []).filter(e => {
        const ext = (e.extension || "").toLowerCase();
        return [".mp4", ".mov", ".mkv", ".webm", ".avi", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".png", ".jpg", ".jpeg", ".webp"].includes(ext);
      });

      const listEl = document.getElementById("win11-media-assets-list");
      if (listEl) {
        if (mediaList.length === 0) {
          listEl.innerHTML = `<p style="padding: 0.85rem; font-size: 0.75rem; color: var(--text-muted);">No media assets found in this folder</p>`;
        } else {
          listEl.innerHTML = mediaList.map((m, idx) => `
            <div class="win11-media-item ${idx === 0 ? 'active' : ''}" data-path="${m.path}">
              <span class="win11-media-item-icon">${getFileIconSvg(m.extension, false)}</span>
              <div class="win11-media-item-info">
                <span class="win11-media-item-name font-mono">${escapeHtml(m.name)}</span>
                <span class="win11-media-item-size font-mono">${formatBytes(m.size)}</span>
              </div>
            </div>
          `).join("");

          listEl.querySelectorAll(".win11-media-item").forEach(itemEl => {
            itemEl.addEventListener("click", () => {
              listEl.querySelectorAll(".win11-media-item").forEach(x => x.classList.remove("active"));
              itemEl.classList.add("active");
              const p = itemEl.getAttribute("data-path");
              const f = mediaList.find(x => x.path === p);
              if (f) playMediaAsset(f);
            });
          });

          if (mediaList.length > 0) {
            playMediaAsset(mediaList[0]);
          }
        }
      }
    } catch {}
  }

  function playMediaAsset(item) {
    const stage = document.getElementById("win11-media-stage");
    if (!stage) return;

    const rawUrl = api.getRawFileUrl(item.path);
    const ext = (item.extension || "").toLowerCase();
    const isVideo = [".mp4", ".mov", ".mkv", ".webm", ".avi"].includes(ext);
    const isAudio = [".mp3", ".wav", ".aac", ".flac", ".ogg"].includes(ext);
    const isImg = [".png", ".jpg", ".jpeg", ".webp", ".gif"].includes(ext);

    if (isVideo) {
      stage.innerHTML = `
        <div class="win11-player-container">
          <video src="${rawUrl}" controls autoplay playsinline class="win11-stage-video" id="win11-stage-video"></video>
          <div class="win11-stage-meta font-mono">
            <span class="font-bold">${escapeHtml(item.name)}</span>
            <span>${formatBytes(item.size)}</span>
          </div>
        </div>
      `;
      setupMediaSync(document.getElementById("win11-stage-video"));
    } else if (isAudio) {
      stage.innerHTML = `
        <div class="win11-player-container audio-stage">
          <div class="win11-stage-audio-icon">${icons.audio}</div>
          <audio src="${rawUrl}" controls autoplay class="win11-stage-audio" id="win11-stage-audio"></audio>
          <div class="win11-stage-meta font-mono">
            <span class="font-bold">${escapeHtml(item.name)}</span>
            <span>${formatBytes(item.size)}</span>
          </div>
        </div>
      `;
      setupMediaSync(document.getElementById("win11-stage-audio"));
    } else if (isImg) {
      stage.innerHTML = `
        <div class="win11-player-container">
          <img src="${rawUrl}" class="win11-stage-image" alt="${escapeHtml(item.name)}" />
          <div class="win11-stage-meta font-mono">
            <span class="font-bold">${escapeHtml(item.name)}</span>
            <span>${formatBytes(item.size)}</span>
          </div>
        </div>
      `;
    }
  }

  function openFullscreenQuickLook(item) {
    if (!item) return;
    const rawUrl = api.getRawFileUrl(item.path);
    const ext = (item.extension || "").toLowerCase();
    const isVideo = [".mp4", ".mov", ".mkv", ".webm", ".avi"].includes(ext);
    const isImage = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"].includes(ext);

    if (!isVideo && !isImage) return;

    const overlay = document.createElement("div");
    overlay.className = "win11-media-fullscreen-overlay";
    overlay.id = "win11-fullscreen-overlay";
    overlay.innerHTML = `
      <button class="win11-fullscreen-close" id="win11-fs-close" title="Close (Esc)">${icons.x}</button>
      <div class="win11-fullscreen-media-container">
        ${isVideo ? `
          <video src="${rawUrl}" controls autoplay playsinline class="win11-fullscreen-video" id="win11-fs-video"></video>
        ` : `
          <img src="${rawUrl}" class="win11-fullscreen-img" alt="${escapeHtml(item.name)}" />
        `}
        <div class="win11-fullscreen-caption font-mono">
          <span>${escapeHtml(item.name)}</span>
          <span style="color: var(--text-muted); margin-left: 8px;">(${formatBytes(item.size)})</span>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    const closeOverlay = () => {
      const vid = document.getElementById("win11-fs-video");
      if (vid) vid.pause();
      overlay.remove();
      document.removeEventListener("keydown", keyHandler);
    };

    const keyHandler = (e) => {
      if (e.key === "Escape" || e.code === "Space") {
        e.preventDefault();
        closeOverlay();
      }
    };

    document.getElementById("win11-fs-close")?.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeOverlay();
    });
    document.addEventListener("keydown", keyHandler, { signal });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Zone 3: Right Details Inspector & CreativeOS Action Deck
  // ──────────────────────────────────────────────────────────────────────────
  function renderInspector(item) {
    if (!inspectorEl) return;

    if (!item) {
      inspectorEl.innerHTML = `
        <div class="win11-inspector-header">
          <span class="font-bold">Details</span>
          <button class="win11-inspector-btn" id="win11-inspector-close-btn" title="Close Details">${icons.x}</button>
        </div>
        <div class="win11-inspector-empty" style="padding: 2rem 1rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
          <p>Select an item to see its details.</p>
        </div>
      `;
      document.getElementById("win11-inspector-close-btn")?.addEventListener("click", () => {
        showZone3 = false;
        localStorage.setItem("cos_win11_show_inspector", "false");
        inspectorEl.style.display = "none";
        workspaceLayoutEl?.classList.remove("with-inspector");
        document.getElementById("win11-btn-toggle-inspector")?.classList.remove("active");
      });
      return;
    }

    const isDir = item.is_dir;
    const rawUrl = api.getRawFileUrl(item.path);
    const ext = (item.extension || "").toLowerCase();
    const isImage = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"].includes(ext);
    const isVideo = [".mp4", ".mov", ".mkv", ".webm", ".avi"].includes(ext);
    const isAudio = [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"].includes(ext);
    const isDoc = [".md", ".markdown", ".txt", ".json", ".csv", ".log", ".py", ".js", ".css", ".html", ".yaml", ".yml", ".ts", ".jsx", ".tsx", ".sh", ".bat", ".toml", ".ini", ".rs", ".go"].includes(ext);

    // Check if this directory corresponds to a known project
    const matchedProject = projectsList.find(p => p.path === item.path || p.name === item.name || p.slug === item.name);

    let stageHtml = "";
    if (isVideo) {
      stageHtml = `
        <div class="win11-native-preview-stage">
          <video src="${rawUrl}" controls preload="metadata" class="win11-native-video" id="win11-inspector-video"></video>
        </div>
      `;
    } else if (isAudio) {
      stageHtml = `
        <div class="win11-native-preview-stage">
          <div class="win11-native-audio-wrap">
            <div style="color: var(--color-accent-cyan);">${icons.audio}</div>
            <audio src="${rawUrl}" controls preload="metadata" class="win11-native-audio" id="win11-inspector-audio"></audio>
          </div>
        </div>
      `;
    } else if (isImage) {
      stageHtml = `
        <div class="win11-native-preview-stage">
          <img src="${rawUrl}" class="win11-native-image" alt="${escapeHtml(item.name)}" />
        </div>
      `;
    } else if (isDoc) {
      stageHtml = `
        <div class="win11-native-preview-stage" style="background: var(--bg-surface);">
          <div class="win11-native-doc-wrap" id="win11-inspector-doc-content">
            <div style="display: flex; align-items: center; justify-content: center; gap: 0.5rem; color: var(--text-muted); padding: 1rem 0;">
              <div class="spinner" style="width: 14px; height: 14px; border-width: 2px;"></div>
              <span>Loading preview...</span>
            </div>
          </div>
        </div>
      `;
    } else if (isDir) {
      stageHtml = `
        <div class="win11-native-preview-stage">
          <div class="win11-native-icon-hero">
            ${icons.folderLarge}
          </div>
        </div>
      `;
    } else {
      stageHtml = `
        <div class="win11-native-preview-stage">
          <div class="win11-native-icon-hero">
            ${getFileIconSvg(item.extension, false)}
          </div>
        </div>
      `;
    }

    const typeDesc = isDir ? (matchedProject ? `${matchedProject.type || 'Project'} Folder` : 'File folder') : (
      isVideo ? 'MP4 Video' : (
        isAudio ? 'Audio Track' : (
          isImage ? `${ext.replace('.', '').toUpperCase()} Image` : (
            isDoc ? `${ext.replace('.', '').toUpperCase()} Document` : `${ext.replace('.', '').toUpperCase()} File`
          )
        )
      )
    );

    const modDate = item.modified ? item.modified.substring(0, 19).replace('T', ' ') : '—';

    inspectorEl.innerHTML = `
      <div class="win11-inspector-header">
        <span class="font-bold">Details</span>
        <div class="win11-inspector-actions">
          <button class="win11-inspector-btn ${isInspectorWide ? 'active' : ''}" id="win11-inspector-expand-btn" title="${isInspectorWide ? 'Compact Inspector (340px)' : 'Expand to Wide (50% Split)'}">
            ${isInspectorWide ? `
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14h6m0 0v6m0-6L3 21m17-7h-6m0 0v6m0-6l7 7M10 4v6m0 0H4m6 0L3 3m10 7h6m0 0V4m0 6l7-7"/></svg>
            ` : `
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
            `}
          </button>
          <button class="win11-inspector-btn" id="win11-inspector-inspect-btn" title="View Full Properties &amp; Blueprint Inspector Dialog">
            ${icons.info}
          </button>
          ${(isVideo || isImage) ? `
            <button class="win11-inspector-btn" id="win11-inspector-fullscreen-btn" title="Fullscreen QuickLook (Space)">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
            </button>
          ` : ''}
          <button class="win11-inspector-btn" id="win11-inspector-open-btn" title="Open in OS">
            ${icons.externalLink}
          </button>
          <button class="win11-inspector-btn" id="win11-inspector-copy-btn" title="Copy Path">
            ${icons.copy}
          </button>
          <button class="win11-inspector-btn" id="win11-inspector-close-btn" title="Close Details">
            ${icons.x}
          </button>
        </div>
      </div>

      <div class="win11-inspector-scroll">
        <!-- Top Preview Stage (Full Width, Flush) -->
        <div title="Preview: ${escapeHtml(item.name)}">
          ${stageHtml}
        </div>

        <!-- File Identity (Clean, No Redundant Bottom Buttons) -->
        <div class="win11-native-identity" style="padding: 0.75rem 0.85rem 0.5rem 0.85rem;" title="File name: ${escapeHtml(item.name)}">
          <div class="win11-native-filename font-mono" title="${escapeHtml(item.name)}" style="font-weight: 700; font-size: 0.85rem; word-break: break-all;">${escapeHtml(item.name)}</div>
        </div>

        <!-- Details Section (Authentic 2-Column Key-Value with Rich Tooltips) -->
        <div class="win11-native-details-section">
          <div class="win11-native-section-heading" title="File specifications and metadata">Details</div>
          <div class="win11-native-kv-list font-mono">
            <div class="win11-native-k" title="File classification / MIME format">Type</div>
            <div class="win11-native-v" title="Type: ${typeDesc}">${typeDesc}</div>

            <div class="win11-native-k" title="Disk space used on filesystem">Size</div>
            <div class="win11-native-v" title="Size: ${isDir ? (matchedProject ? formatBytes(matchedProject.total_size) : '—') : formatBytes(item.size)}">${isDir ? (matchedProject ? formatBytes(matchedProject.total_size) : '—') : formatBytes(item.size)}</div>

            <div class="win11-native-k" title="Full filesystem path on drive">File location</div>
            <div class="win11-native-v copyable" id="win11-copy-spec-location" title="Click to copy path: ${escapeHtml(item.path)}">
              ${escapeHtml(item.path)}
              ${icons.copy}
            </div>

            <div class="win11-native-k" title="Last modification timestamp">Date modified</div>
            <div class="win11-native-v" title="Modified: ${modDate}">${modDate}</div>

            ${matchedProject && matchedProject.client ? `
              <div class="win11-native-k" title="Client name">Client</div>
              <div class="win11-native-v" title="Client: ${escapeHtml(matchedProject.client)}">${escapeHtml(matchedProject.client)}</div>
            ` : ''}

            ${matchedProject && matchedProject.status ? `
              <div class="win11-native-k" title="Project stage / status">Status</div>
              <div class="win11-native-v" title="Status: ${escapeHtml(matchedProject.status)}">${escapeHtml(matchedProject.status)}</div>
            ` : ''}
          </div>
        </div>
      </div>
    `;

    document.getElementById("win11-inspector-close-btn")?.addEventListener("click", () => {
      showZone3 = false;
      localStorage.setItem("cos_win11_show_inspector", "false");
      inspectorEl.style.display = "none";
      workspaceLayoutEl?.classList.remove("with-inspector");
      document.getElementById("win11-btn-toggle-inspector")?.classList.remove("active");
    });

    // Expand / Compact Inspector Button
    document.getElementById("win11-inspector-expand-btn")?.addEventListener("click", () => {
      isInspectorWide = !isInspectorWide;
      localStorage.setItem("cos_win11_inspector_wide", isInspectorWide ? "true" : "false");
      workspaceLayoutEl?.classList.toggle("inspector-is-wide", isInspectorWide);
      renderInspector(item);
    });

    // Properties / Inspector Dialog Button
    document.getElementById("win11-inspector-inspect-btn")?.addEventListener("click", () => {
      const activeProj = matchedProject || getActiveProject();
      if (activeProj) {
        openProjectInspector(activeProj, categoriesData, () => loadCurrentDirectory());
      } else {
        showToast(`Properties for ${item.name}: ${typeDesc}, ${formatBytes(item.size)}`, "info", 2000);
      }
    });

    // Fullscreen QuickLook Button
    document.getElementById("win11-inspector-fullscreen-btn")?.addEventListener("click", () => {
      openFullscreenQuickLook(item);
    });

    // Open in OS Button
    document.getElementById("win11-inspector-open-btn")?.addEventListener("click", async () => {
      try {
        await api.openPath(item.path);
        showToast(`Opened ${item.name} natively in Windows`, "info", 1500);
      } catch (e) {
        showToast(`Failed: ${e.message}`, "error");
      }
    });

    // Copy Path Button
    document.getElementById("win11-inspector-copy-btn")?.addEventListener("click", () => {
      navigator.clipboard.writeText(item.path);
      showToast("Copied path to clipboard!", "success", 1200);
    });

    // Async Fetch Document Content
    if (isDoc) {
      fetch(rawUrl)
        .then(r => {
          if (!r.ok) throw new Error("Status " + r.status);
          return r.text();
        })
        .then(text => {
          const docEl = document.getElementById("win11-inspector-doc-content");
          if (docEl) {
            if (ext === ".md" || ext === ".markdown" || ext === ".txt") {
              docEl.innerHTML = renderMarkdownSafe(text);
            } else {
              docEl.innerHTML = `<pre class="win11-code-block font-mono"><code>${escapeHtml(text.slice(0, 10000))}</code></pre>`;
            }
          }
        })
        .catch(err => {
          const docEl = document.getElementById("win11-inspector-doc-content");
          if (docEl) docEl.innerHTML = `<p style="color: var(--color-danger); font-size: 0.725rem;">Preview unavailable: ${escapeHtml(err.message)}</p>`;
        });
    }

    if (isVideo) {
      setupMediaSync(document.getElementById("win11-inspector-video"));
    }
    if (isAudio) {
      setupMediaSync(document.getElementById("win11-inspector-audio"));
    }

    // Wire Location Copy
    document.getElementById("win11-copy-spec-location")?.addEventListener("click", () => {
      navigator.clipboard.writeText(item.path);
      showToast("Copied path to clipboard!", "success", 1200);
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Top Chrome & Ribbon Event Handlers
  // ──────────────────────────────────────────────────────────────────────────
  function getActiveProject() {
    const tab = getActiveTab();
    const currentPath = tab ? (tab.path || "").replace(/\//g, "\\") : "";

    // 1. If currently inside a project folder
    if (currentPath) {
      const p = projectsList.find(proj => {
        const projPath = (proj.path || "").replace(/\//g, "\\");
        return currentPath === projPath || currentPath.startsWith(projPath + "\\");
      });
      if (p) return p;
    }

    // 2. If a project folder or project file is selected
    if (selectedItem) {
      const selPath = (selectedItem.path || "").replace(/\//g, "\\");
      const p = projectsList.find(proj => {
        const projPath = (proj.path || "").replace(/\//g, "\\");
        return selPath === projPath || proj.name === selectedItem.name || proj.slug === selectedItem.name || selPath.startsWith(projPath + "\\");
      });
      if (p) return p;
    }

    return null;
  }

  function createNewTab(targetPath) {
    const title = targetPath ? targetPath.split(/[\\/]/).filter(Boolean).pop() || "Folder" : "01_Projects";
    const newId = Date.now();
    const newTab = {
      id: newId,
      title: title,
      path: targetPath || "",
      history: [targetPath || ""],
      historyIndex: 0
    };
    tabs.push(newTab);
    activeTabId = newId;
    sessionStorage.setItem("cos_win11_active_tab_id", String(activeTabId));
    saveTabsSession();
    renderTabsBar();
    loadCurrentDirectory();
  }

  navBackBtn?.addEventListener("click", () => {
    const tab = getActiveTab();
    if (tab.historyIndex > 0) {
      tab.historyIndex--;
      tab.path = tab.history[tab.historyIndex];
      tab.title = tab.path ? tab.path.split(/[\\/]/).filter(Boolean).pop() || "Folder" : "01_Projects";
      saveTabsSession();
      renderTabsBar();
      loadCurrentDirectory();
    }
  });

  navForwardBtn?.addEventListener("click", () => {
    const tab = getActiveTab();
    if (tab.historyIndex < tab.history.length - 1) {
      tab.historyIndex++;
      tab.path = tab.history[tab.historyIndex];
      tab.title = tab.path ? tab.path.split(/[\\/]/).filter(Boolean).pop() || "Folder" : "01_Projects";
      saveTabsSession();
      renderTabsBar();
      loadCurrentDirectory();
    }
  });

  navUpBtn?.addEventListener("click", () => {
    if (currentParentPath) {
      updateActiveTabPath(currentParentPath);
    }
  });

  navRefreshBtn?.addEventListener("click", () => {
    loadCurrentDirectory();
    showToast("Refreshed", "info", 800);
  });

  copyAddressBtn?.addEventListener("click", async () => {
    const p = getActiveTab().path || "01_Projects";
    try {
      await navigator.clipboard.writeText(p);
      showToast("Copied path to clipboard", "info", 1500);
    } catch {}
  });

  // Ribbon Actions
  document.getElementById("win11-btn-new-project")?.addEventListener("click", () => {
    openNewProjectModal(async () => {
      try {
        projectsList = await api.getProjects();
        updateSidebarBadges();
      } catch (err) {
        console.warn("Could not refresh projects after creation:", err);
      }
      loadCurrentDirectory();
    });
  });

  function updateViewButtons() {
    const isGrid = viewMode === "grid";
    const toggleIcon = document.getElementById("win11-view-toggle-icon");
    const toggleText = document.getElementById("win11-view-toggle-text");
    if (toggleIcon && toggleText) {
      toggleIcon.innerHTML = isGrid ? icons.table : icons.grid;
      toggleText.textContent = isGrid ? 'Details' : 'Large Icons';
    }
    document.getElementById("win11-btn-view-split")?.classList.toggle("active", viewMode === "split");
    document.getElementById("status-btn-view-details")?.classList.toggle("active", viewMode === "details");
    document.getElementById("status-btn-view-grid")?.classList.toggle("active", viewMode === "grid");
  }

  function setViewMode(newMode) {
    const wasSplit = viewMode === "split";
    if (newMode !== "split" && newMode !== "media") {
      lastGlobalView = newMode;
      localStorage.setItem("cos_last_global_view", lastGlobalView);
    }
    viewMode = newMode;
    const tab = getActiveTab();
    if (tab && newMode !== "split" && newMode !== "media") {
      folderViewMap[tab.path] = newMode;
      localStorage.setItem("cos_folder_view_map", JSON.stringify(folderViewMap));
    }
    updateViewButtons();
    if (newMode === "split") renderDualPaneView();
    else if (newMode === "media") renderMediaScrubberView();
    else if (wasSplit) loadCurrentDirectory();
    else renderCanvasEntries();
  }

  document.getElementById("win11-btn-view-toggle")?.addEventListener("click", () => {
    setViewMode(viewMode === "grid" ? "details" : "grid");
  });

  document.getElementById("status-btn-view-details")?.addEventListener("click", () => {
    setViewMode("details");
  });

  document.getElementById("status-btn-view-grid")?.addEventListener("click", () => {
    setViewMode("grid");
  });

  document.getElementById("win11-btn-view-split")?.addEventListener("click", () => {
    const prev = lastGlobalView === "split" ? "grid" : (lastGlobalView || "grid");
    const target = folderViewMap[getActiveTab().path];
    setViewMode(viewMode === "split" ? (target && target !== "split" ? target : prev) : "split");
  });

  // Ribbon Active Project Action Handlers
  document.getElementById("win11-btn-export-folder")?.addEventListener("click", async () => {
    const btn = document.getElementById("win11-btn-export-folder");
    const targetProjPath = btn?.getAttribute("data-target-project-path");
    if (targetProjPath) {
      updateActiveTabPath(targetProjPath);
      return;
    }

    const activeProj = getActiveProject();
    if (activeProj) {
      try {
        showToast(`Generating export folder for ${activeProj.name}...`, "info", 1200);
        const res = await api.createExportFolder(activeProj.slug || activeProj.name);
        showToast(`Export folder ready at ${res.export_path}`, "success", 2000);
        if (res.export_path) {
          createNewTab(res.export_path);
        }
      } catch (e) {
        showToast(`Export folder failed: ${e.message}`, "error");
      }
    } else {
      createNewTab("02_Exports");
    }
  });

  document.getElementById("win11-btn-reclaim-cache")?.addEventListener("click", () => {
    const activeProj = getActiveProject();
    if (activeProj) {
      openReclaimModal(activeProj, () => loadCurrentDirectory());
    } else {
      openBulkReclaimModal(storageData || { projects: projectsList }, () => loadCurrentDirectory());
    }
  });

  document.getElementById("win11-btn-sync-vault")?.addEventListener("click", () => {
    openLiveSyncModal(() => loadCurrentDirectory());
  });

  document.getElementById("win11-btn-shuttle-travel")?.addEventListener("click", () => {
    const activeProj = getActiveProject();
    if (activeProj) {
      openConfirmModal({
        title: "Export to Shuttle Drive",
        message: `Sync project '${activeProj.name}' to your connected external Shuttle Drive?`,
        confirmText: "Launch Travel",
        variant: "info",
        onConfirm: async () => {
          const res = await api.travelProject(activeProj.slug || activeProj.name);
          showToast(`Exported to Shuttle: ${res.dest_path}`, "success");
        }
      });
    } else {
      showToast("Please select or navigate inside a project to sync with Shuttle Drive.", "warning");
    }
  });

  document.getElementById("win11-btn-theme-toggle")?.addEventListener("click", () => {
    const t = toggleTheme();
    showToast(`Switched to ${t} theme`, "info", 1000);
  });

  document.getElementById("win11-btn-toggle-inspector")?.addEventListener("click", () => {
    showZone3 = !showZone3;
    localStorage.setItem("cos_win11_show_inspector", showZone3 ? "true" : "false");
    document.getElementById("win11-btn-toggle-inspector")?.classList.toggle("active", showZone3);
    if (inspectorEl) inspectorEl.style.display = showZone3 ? "block" : "none";
    workspaceLayoutEl?.classList.toggle("with-inspector", showZone3);
    if (showZone3) {
      renderInspector(selectedItem);
    }
  });

  // Delegated Sidebar Tree Item Click Handlers
  document.getElementById("win11-sidebar")?.addEventListener("click", async (e) => {
    const item = e.target.closest(".win11-tree-item");
    if (!item) return;

    const action = item.getAttribute("data-action");
    if (action === "clean-downloads") {
      openConfirmModal({
        title: "Organize Downloads",
        message: "Move loose files in Downloads into automatically selected subfolders?",
        subtext: "Existing folders are left in place. Name collisions may be renamed.",
        confirmText: "Organize Files",
        variant: "warning",
        onConfirm: async () => {
          const res = await api.cleanDownloads();
          showToast(`Cleaned Downloads: ${res.moved_count} files organized!`, "success");
          updateActiveTabPath("Downloads");
        },
      });
      return;
    }
    if (action === "sort-inbox") {
      openConfirmModal({
        title: "Sort Export Inbox",
        message: "Move unfiled renders into date-based folders under 02_Exports?",
        subtext: "Existing folders are left in place. Name collisions may be renamed.",
        confirmText: "Sort Renders",
        variant: "warning",
        onConfirm: async () => {
          const res = await api.sortExportsInbox();
          showToast(`Sorted ${res.moved_count} renders into 02_Exports/!`, "success");
          updateActiveTabPath("02_Exports");
        },
      });
      return;
    }
    if (action === "bulk-reclaim") {
      openBulkReclaimModal(storageData || { projects: projectsList }, () => loadCurrentDirectory());
      return;
    }
    if (action === "storage-inventory") {
      updateActiveTabPath("storage");
      return;
    }
    if (action === "cold-archive") {
      updateActiveTabPath("archive");
      return;
    }
    if (action === "studio-settings") {
      updateActiveTabPath("settings");
      return;
    }

    const route = item.getAttribute("data-route");
    if (route) {
      setUiMode("classic");
      window.location.hash = route;
      return;
    }

    const p = item.getAttribute("data-path");
    if (p === "00_Notes") {
      const activeProj = getActiveProject();
      if (activeProj) {
        updateActiveTabPath(`${activeProj.path}\\00_Notes`);
      } else {
        updateActiveTabPath("00_Notes");
      }
      return;
    }

    if (p === "02_Exports") {
      const activeProj = getActiveProject();
      if (activeProj) {
        try {
          showToast(`Opening export folder for ${activeProj.name}...`, "info", 1000);
          const res = await api.createExportFolder(activeProj.slug || activeProj.name);
          if (res.export_path) {
            createNewTab(res.export_path);
          }
        } catch (err) {
          showToast(`Export folder: ${err.message}`, "error");
        }
      } else {
        updateActiveTabPath("02_Exports");
      }
      return;
    }

    if (p !== null && p !== undefined) {
      updateActiveTabPath(p);
    }
  });

  // Keyboard Shortcuts (Delete Key for Selected File/Folder)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Delete" && selectedItem && !e.target.closest("input, textarea, [contenteditable]")) {
      if (viewMode !== "grid" && viewMode !== "details") return;
      const item = selectedItem;
      if (!currentEntries.some(entry => entry.path === item.path)) return;
      const activeModal = document.querySelector(".modal-backdrop.is-open, #resurrect-modal-backdrop, #bulk-reclaim-modal-container");
      if (activeModal) return;
      e.preventDefault();
      const isDir = item.is_dir;
      const isProj = projectsList.find(p => p.path === item.path || p.name === item.name || p.slug === item.name);
      const itemType = isProj ? "Project" : (isDir ? "Folder" : "File");
      openConfirmModal({
        title: `Delete ${itemType}`,
        message: `Are you sure you want to delete "${item.name}"?`,
        subtext: "This will move the item to the Windows Recycle Bin.",
        confirmText: "Delete",
        variant: "danger",
        onConfirm: async () => {
          try {
            await api.deletePath(item.path);
            showToast(`Moved '${item.name}' to Recycle Bin`, "info", 2000);
            loadCurrentDirectory();
            updateSidebarBadges();
          } catch (err) {
            showToast(`Failed to delete: ${err.message}`, "error");
          }
        }
      });
    }
  }, { signal });

  // Current Folder Live Filter
  searchInputEl?.addEventListener("input", () => {
    if (viewMode !== "grid" && viewMode !== "details") return;
    const path = getActiveTab()?.path;
    if (["storage", "settings", "archive", "sys://storage", "sys://settings", "sys://archive"].includes(path)) return;
    selectedItem = null;
    renderCanvasEntries();
  });

  document.getElementById("win11-btn-switch-classic")?.addEventListener("click", () => {
    setUiMode("classic");
  });

  // Kickoff
  renderTabsBar();
  renderSidebarCategories();
  renderSidebarDrives();
  container.querySelectorAll(".win11-tree-item").forEach(item => {
    item.tabIndex = 0;
    item.setAttribute("role", "button");
  });
  document.getElementById("win11-sidebar")?.addEventListener("keydown", (e) => {
    const item = e.target.closest(".win11-tree-item");
    if (item && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      item.click();
    }
  });
  updateSidebarBadges();
  loadCurrentDirectory();
}
