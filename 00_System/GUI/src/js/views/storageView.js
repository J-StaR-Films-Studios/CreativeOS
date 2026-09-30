/**
 * Storage Overview View — Visual Analytics & Inventory
 */

import { api, formatBytes, cacheStore } from "../api.js";
import { renderStorageTable } from "../components/storageTable.js";
import { renderWindowsCleanup } from "../components/windowsCleanup.js";
import { openProjectInspector } from "../components/modal.js";
import { openReclaimModal, openBulkReclaimModal } from "../components/reclaimModal.js";
import { icons } from "../icons.js";
import { showToast } from "../components/toast.js";

export async function renderStorage(container, options = {}) {
  const targetProject = options.project ? decodeURIComponent(options.project).trim() : "";
  const cachedStorage = cacheStore.get("storage");
  const cachedCats = cacheStore.get("categories");
  const hasCache = Boolean(cachedStorage && cachedStorage.projects);

  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-eyebrow">
          <span class="studio-status-indicator" style="background-color: var(--color-accent-cyan);"></span>
          <span>STORAGE ANALYTICS</span>
        </div>
        <h1 class="page-title">Storage Inventory</h1>
        <p class="page-description">Inspect disk consumption, media assets, and cache directories</p>
      </div>
      <div class="header-action-group" id="storage-header-actions">
        <button id="bulk-reclaim-btn" class="btn btn-danger" style="display: none; align-items: center; gap: 0.4rem;">
          ${icons.zap}
          <span id="bulk-reclaim-header-label">Reclaim Space</span>
        </button>
        <button id="rescan-storage-btn" class="btn btn-secondary">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          Rescan
        </button>
      </div>
    </div>

    <!-- Storage Visual Multi-segment Bar & Stats -->
    <div id="storage-summary-container"></div>
    <section id="windows-cleanup-container" class="windows-cleanup-panel" aria-label="Windows cleanup locations"></section>

    <div class="studio-toolbar" style="display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap;">
      <div class="search-box" style="flex: 1; min-width: 260px;">
        <span class="search-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </span>
        <input type="text" id="storage-search-input" class="search-input" placeholder="Search projects by name, category, or path..." />
      </div>
      <div class="storage-filter-tabs" id="storage-filter-tabs">
        <button type="button" class="storage-filter-tab is-active" data-filter="all" id="tab-filter-all">
          <span>All Projects</span>
          <span class="badge font-mono" id="filter-count-all">0</span>
        </button>
        <button type="button" class="storage-filter-tab" data-filter="stale" id="tab-filter-stale">
          <span class="cell-status-dot dot-stale" style="width: 6px; height: 6px;"></span>
          <span>Stale (&gt;90d)</span>
          <span class="badge font-mono" id="filter-count-stale">0</span>
        </button>
        <button type="button" class="storage-filter-tab" data-filter="reclaimable" id="tab-filter-reclaimable">
          <span style="color: var(--color-warning);">${icons.zap}</span>
          <span>Reclaimable</span>
          <span class="badge font-mono" id="filter-count-reclaimable">0</span>
        </button>
      </div>
    </div>

    <div id="storage-table-container">
      ${hasCache ? '' : `
        <div class="loading-state">
          <div class="spinner"></div>
          <p>Scanning storage footprint...</p>
        </div>
      `}
    </div>
  `;

  let latestStorage = cachedStorage;
  let windowsCleanup = cachedStorage?.windows_cleanup || null;
  const windowsPanel = renderWindowsCleanup(container.querySelector("#windows-cleanup-container"), (snapshot) => {
    windowsCleanup = snapshot;
    if (latestStorage) updateSummary(latestStorage);
  });

  let currentSort = { key: "total_size", asc: false };
  let activeFilter = "all"; // "all" | "stale" | "reclaimable"
  let allProjects = [];
  let categoriesConfig = {};
  const cutoff = Date.now() - (90 * 24 * 60 * 60 * 1000);

  function updateSummary(data) {
    const summaryContainer = document.getElementById("storage-summary-container");
    if (!summaryContainer) return;

    const projectTotal = data.total_size || 0;
    const media = data.media_size || 0;
    const reclaimable = data.reclaimable_size || 0;
    const other = Math.max(0, projectTotal - media - reclaimable);
    const windowsSize = windowsCleanup?.locations?.reduce((sum, item) => sum + (item.size_bytes || 0), 0) || 0;
    const windowsIncomplete = windowsCleanup?.locations?.some(item => item.status === "partial" || item.status === "inaccessible");
    const total = projectTotal + windowsSize;

    const mediaPct = total > 0 ? ((media / total) * 100).toFixed(1) : 0;
    const reclaimablePct = total > 0 ? ((reclaimable / total) * 100).toFixed(1) : 0;
    const otherPct = total > 0 ? ((other / total) * 100).toFixed(1) : 0;
    const windowsPct = total > 0 ? ((windowsSize / total) * 100).toFixed(1) : 0;

    // Update filter tab counts and stale reclaimable
    const pList = data.projects || allProjects || [];
    const staleProjectsList = pList.filter(p => {
      if (p.is_stale || p.status === "stale") return true;
      const raw = p.last_meaningful_update || p.created;
      return raw ? new Date(raw.replace(" ", "T")).getTime() < cutoff : true;
    });
    const staleCount = staleProjectsList.length;
    const staleReclaimable = staleProjectsList.reduce((sum, p) => sum + (p.reclaimable_size || 0), 0);
    const reclaimableCount = pList.filter(p => (p.reclaimable_size || 0) > 0).length;

    // Header Bulk Reclaim Button update
    const bulkReclaimBtn = document.getElementById("bulk-reclaim-btn");
    const bulkReclaimLabel = document.getElementById("bulk-reclaim-header-label");
    if (bulkReclaimBtn) {
      if (reclaimable > 0) {
        bulkReclaimBtn.style.display = "inline-flex";
        if (bulkReclaimLabel) {
          if (activeFilter === "stale" && staleReclaimable > 0) {
            bulkReclaimLabel.textContent = `Clean Stale Caches (${formatBytes(staleReclaimable)})`;
          } else {
            bulkReclaimLabel.textContent = `Reclaim All Caches (${formatBytes(reclaimable)})`;
          }
        }
      } else {
        bulkReclaimBtn.style.display = "none";
      }
    }

    // Top 3 heaviest projects
    const topProjects = [...(data.projects || [])]
      .sort((a, b) => (b.total_size || 0) - (a.total_size || 0))
      .slice(0, 3);

    const elAll = document.getElementById("filter-count-all");
    const elStale = document.getElementById("filter-count-stale");
    const elRec = document.getElementById("filter-count-reclaimable");
    if (elAll) elAll.textContent = pList.length;
    if (elStale) elStale.textContent = staleCount;
    if (elRec) elRec.textContent = reclaimableCount;

    summaryContainer.innerHTML = `
      <!-- Flattened Storage Overview Strip -->
      <div class="storage-overview-strip">
        <div class="storage-bar-header">
          <div>
            <span class="storage-bar-title">Disk Allocation</span>
            <span class="storage-bar-sub font-mono" title="Indexed projects plus measured Windows caches, not whole-drive capacity">${windowsIncomplete ? '≥ ' : ''}${formatBytes(total)} measured</span>
          </div>
          <div class="storage-legend">
            <span class="legend-item"><span class="legend-dot" style="background-color: var(--color-accent-cyan);"></span> Media (${mediaPct}%)</span>
            <span class="legend-item"><span class="legend-dot" style="background-color: var(--color-warning);"></span> Reclaimable (${reclaimablePct}%)</span>
            <span class="legend-item"><span class="legend-dot" style="background-color: var(--text-primary);"></span> Workspace (${otherPct}%)</span>
            <span class="legend-item"><span class="legend-dot" style="background-color: var(--color-primary);"></span> Windows caches (${windowsCleanup?.scanned_at ? `${windowsPct}%` : 'not scanned'})</span>
          </div>
        </div>

        <div class="multi-segment-bar">
          <div class="segment-media" style="width: ${mediaPct}%;" title="Media: ${formatBytes(media)} (${mediaPct}%)"></div>
          <div class="segment-reclaimable" style="width: ${reclaimablePct}%;" title="Reclaimable: ${formatBytes(reclaimable)} (${reclaimablePct}%)"></div>
          <div class="segment-other" style="width: ${otherPct}%;" title="Workspace: ${formatBytes(other)} (${otherPct}%)"></div>
          <div class="segment-windows" style="width: ${windowsPct}%;" title="Windows caches: ${formatBytes(windowsSize)} (${windowsPct}%)"></div>
        </div>

        <div class="storage-insights">
          <div class="storage-insight-cell">
            <span class="insight-label">Measured Total</span>
            <span class="insight-val font-mono">${windowsIncomplete ? '≥ ' : ''}${formatBytes(total)}</span>
            <span class="insight-sub">${data.project_count || 0} projects${windowsCleanup?.scanned_at ? ' + Windows caches' : ' only'}</span>
          </div>
          <div class="storage-insight-cell">
            <span class="insight-label">Media Assets</span>
            <span class="insight-val font-mono" style="color: var(--color-accent-cyan);">${formatBytes(media)}</span>
            <span class="insight-sub">RAW &amp; Audio</span>
          </div>
          <div class="storage-insight-cell is-clickable" id="insight-reclaimable-card" title="Click to filter to projects with reclaimable cache">
            <span class="insight-label">Reclaimable</span>
            <span class="insight-val font-mono" style="color: var(--color-warning);">${formatBytes(reclaimable)}</span>
            <span class="insight-sub" style="color: var(--color-warning);">${reclaimableCount} with cache &rarr;</span>
          </div>
          <div class="storage-insight-cell is-clickable" id="insight-windows-card" title="Jump to Windows cleanup locations">
            <span class="insight-label">Windows Caches</span>
            <span class="insight-val font-mono" style="color: var(--color-primary);">${windowsCleanup?.scanned_at ? `${windowsIncomplete ? '≥ ' : ''}${formatBytes(windowsSize)}` : '—'}</span>
            <span class="insight-sub">${windowsCleanup?.scanned_at ? `Updated ${new Date(windowsCleanup.scanned_at).toLocaleDateString()}` : 'Not scanned'} &rarr;</span>
          </div>
          <div class="storage-insight-cell is-clickable" id="insight-stale-card" title="Click to filter to Stale projects (>90d inactive)">
            <span class="insight-label">Last Indexed</span>
            <span class="insight-val font-mono" style="font-size: 0.95rem; margin-top: 0.15rem;">${data.scanned_at ? data.scanned_at.substring(0, 10) : 'Live'}</span>
            <span class="insight-sub" style="color: var(--color-warning); font-weight: 600;">${staleCount} stale (&gt;90d) &rarr;</span>
          </div>
        </div>
      </div>

      <!-- Top Consumers Spotlight -->
      ${topProjects.length > 0 ? `
        <div class="top-consumers-panel">
          <span class="top-consumers-title">Top Space Consumers</span>
          <div class="top-consumers-grid">
            ${topProjects.map((p, idx) => `
              <div class="top-consumer-card" data-slug="${p.slug || ''}" data-name="${p.name || ''}" data-path="${p.path || ''}" tabindex="0" role="button" aria-label="Inspect ${p.name}">
                <div class="consumer-rank font-mono">#${idx + 1}</div>
                <div class="consumer-info">
                  <span class="consumer-name" title="${p.name}">${p.name}</span>
                  <span class="consumer-cat">${p.type || 'Video'} &bull; ${p.file_count || 0} files</span>
                </div>
                <div class="consumer-size font-mono">${formatBytes(p.total_size)}</div>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ''}
    `;

    document.getElementById("insight-windows-card")?.addEventListener("click", () => {
      container.querySelector("#windows-cleanup-container")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    // Click on stale insight card to filter
    document.getElementById("insight-stale-card")?.addEventListener("click", () => {
      setFilter("stale");
    });

    // Click on reclaimable insight card to filter
    document.getElementById("insight-reclaimable-card")?.addEventListener("click", () => {
      setFilter("reclaimable");
    });

    // Attach click handlers to top consumer cards
    summaryContainer.querySelectorAll(".top-consumer-card").forEach(card => {
      const handleInspect = () => {
        const path = card.getAttribute("data-path");
        const slug = card.getAttribute("data-slug");
        const name = card.getAttribute("data-name");
        const target = allProjects.find(p => (path && p.path === path) || (slug && p.slug === slug) || (name && p.name === name));
        if (target) {
          openProjectInspector(target, categoriesConfig, () => {
            loadData();
          });
        }
      };

      card.addEventListener("click", handleInspect);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleInspect();
        }
      });
    });
  }

  function setFilter(filter) {
    activeFilter = filter;
    document.querySelectorAll(".storage-filter-tab").forEach(tab => {
      if (tab.getAttribute("data-filter") === filter) {
        tab.classList.add("is-active");
      } else {
        tab.classList.remove("is-active");
      }
    });

    const bulkReclaimLabel = document.getElementById("bulk-reclaim-header-label");
    if (bulkReclaimLabel) {
      const staleReclaimable = allProjects.filter(p => {
        if (p.is_stale || p.status === "stale") return true;
        const raw = p.last_meaningful_update || p.created;
        return raw ? new Date(raw.replace(" ", "T")).getTime() < cutoff : true;
      }).reduce((sum, p) => sum + (p.reclaimable_size || 0), 0);
      const totalReclaimable = allProjects.reduce((sum, p) => sum + (p.reclaimable_size || 0), 0);

      if (activeFilter === "stale" && staleReclaimable > 0) {
        bulkReclaimLabel.textContent = `Clean Stale Caches (${formatBytes(staleReclaimable)})`;
      } else {
        bulkReclaimLabel.textContent = `Reclaim All Caches (${formatBytes(totalReclaimable)})`;
      }
    }

    renderTable();
  }

  function renderTable() {
    const tableContainer = document.getElementById("storage-table-container");
    const searchInput = document.getElementById("storage-search-input");
    const query = (searchInput?.value || "").toLowerCase().trim();

    const filtered = allProjects.filter(p => {
      if (activeFilter === "stale") {
        const isStale = p.is_stale || p.status === "stale" ||
          (p.last_meaningful_update && new Date(p.last_meaningful_update.replace(" ", "T")).getTime() < cutoff) ||
          (!p.last_meaningful_update && p.created && new Date(p.created.replace(" ", "T")).getTime() < cutoff);
        if (!isStale) return false;
      } else if (activeFilter === "reclaimable") {
        if ((p.reclaimable_size || 0) <= 0) return false;
      }

      if (!query) return true;
      return (p.name && p.name.toLowerCase().includes(query)) ||
             (p.type && p.type.toLowerCase().includes(query)) ||
             (p.slug && p.slug.toLowerCase().includes(query)) ||
             (p.path && p.path.toLowerCase().includes(query));
    });

    if (tableContainer) {
      tableContainer.innerHTML = renderStorageTable(filtered, currentSort);
      attachSortHandlers();
      attachRowInspectors(filtered);

      if (targetProject) {
        const rows = [...document.querySelectorAll(".storage-row")];
        const match = rows.find(r => {
          const s = r.getAttribute("data-slug") || "";
          const n = r.getAttribute("data-name") || "";
          const p = r.getAttribute("data-path") || "";
          const target = targetProject.toLowerCase();
          return s.toLowerCase() === target ||
                 n.toLowerCase() === target ||
                 p.toLowerCase() === target ||
                 p.toLowerCase().includes(target);
        });

        if (match) {
          match.classList.add("storage-row-highlighted");
          setTimeout(() => {
            match.scrollIntoView({ behavior: "smooth", block: "center" });
          }, 150);
        }
      }
    }
  }

  function attachSortHandlers() {
    const ths = document.querySelectorAll("#storage-table-container th.sortable");
    ths.forEach(th => {
      th.addEventListener("click", () => {
        const sortKey = th.getAttribute("data-sort");
        if (currentSort.key === sortKey) {
          currentSort.asc = !currentSort.asc;
        } else {
          currentSort.key = sortKey;
          currentSort.asc = false;
        }
        renderTable();
      });
    });
  }

  function attachRowInspectors(filteredList) {
    // Reclaim button triggers
    document.querySelectorAll(".row-reclaim-trigger").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const path = btn.getAttribute("data-path");
        const slug = btn.getAttribute("data-slug");
        const name = btn.getAttribute("data-name");
        const target = filteredList.find(p => (path && p.path === path) || (slug && p.slug === slug) || (name && p.name === name));
        if (target) {
          openReclaimModal(target, () => {
            loadData();
          });
        }
      });
    });

    // Row inspection triggers
    document.querySelectorAll(".storage-row").forEach(row => {
      const handleInspect = () => {
        const path = row.getAttribute("data-path");
        const slug = row.getAttribute("data-slug");
        const name = row.getAttribute("data-name");
        const target = filteredList.find(p => (path && p.path === path) || (slug && p.slug === slug) || (name && p.name === name));
        if (target) {
          openProjectInspector(target, categoriesConfig, () => {
            loadData();
          });
        }
      };

      row.addEventListener("click", handleInspect);
      row.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleInspect();
        }
      });
    });
  }

  async function loadData() {
    try {
      if (hasCache) {
        categoriesConfig = cachedCats?.categories || {};
        allProjects = cachedStorage.projects || [];
        latestStorage = cachedStorage;
        updateSummary(cachedStorage);
        renderTable();
      }

      api.getStorageSWR((freshStorage) => {
        allProjects = freshStorage.projects || [];
        latestStorage = freshStorage;
        updateSummary(freshStorage);
        renderTable();
      });

      api.getCategoriesSWR((freshCats) => {
        categoriesConfig = freshCats.categories || {};
        renderTable();
      });
    } catch (err) {
      const tableContainer = document.getElementById("storage-table-container");
      if (tableContainer && allProjects.length === 0) {
        tableContainer.innerHTML = `
          <div class="empty-state" style="border-color: var(--color-danger);">
            <h3 style="color: var(--color-danger); margin-bottom: 0.35rem; font-size: 1rem;">Failed to Index Storage</h3>
            <p style="font-size: 0.85rem;">${err.message}</p>
          </div>
        `;
      }
      showToast("Error loading storage index", "error");
    }
  }

  const bulkReclaimBtn = document.getElementById("bulk-reclaim-btn");
  bulkReclaimBtn?.addEventListener("click", () => {
    openBulkReclaimModal({ projects: allProjects }, async () => {
      await loadData();
    }, activeFilter === "stale" ? "stale" : "all");
  });

  const rescanBtn = document.getElementById("rescan-storage-btn");
  rescanBtn?.addEventListener("click", async () => {
    rescanBtn.disabled = true;
    rescanBtn.innerHTML = `
      <span class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0;"></span>
      Scanning...
    `;
    showToast("Scanning projects and Windows caches...", "info");

    try {
      const updated = await api.refreshStorage();
      allProjects = updated.projects || [];
      latestStorage = updated;
      windowsPanel.showSnapshot(updated.windows_cleanup);
      updateSummary(updated);
      renderTable();
      showToast(updated.windows_cleanup_warning || "Storage indexes refreshed", updated.windows_cleanup_warning ? "error" : "success");
    } catch (err) {
      showToast(`Rescan failed: ${err.message}`, "error");
    } finally {
      rescanBtn.disabled = false;
      rescanBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
        Rescan Index
      `;
    }
  });

  const searchInput = document.getElementById("storage-search-input");
  searchInput?.addEventListener("input", renderTable);

  document.querySelectorAll(".storage-filter-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      setFilter(tab.getAttribute("data-filter") || "all");
    });
  });

  await loadData();
}
