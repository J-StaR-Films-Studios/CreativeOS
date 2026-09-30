/**
 * Settings & Obsidian Sync View — Studio Blueprint Explorer
 */

import { api, cacheStore } from "../api.js";
import { getCategoryIconSvg, icons } from "../icons.js";
import { showToast } from "../components/toast.js";

export async function renderSettings(container) {
  const cachedConfig = cacheStore.get("config");
  const cachedCats = cacheStore.get("categories");
  const hasCache = Boolean(cachedConfig && cachedCats);

  let isEditingPaths = false;
  let currentConfigData = cachedConfig || null;

  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-eyebrow">
          <span class="studio-status-indicator" style="background-color: var(--text-primary);"></span>
          <span>CONFIGURATION</span>
        </div>
        <h1 class="page-title">Settings &amp; Sync</h1>
        <p class="page-description">System storage paths, category blueprints, and Obsidian Vault sync</p>
      </div>
    </div>

    <!-- Obsidian Sync Section -->
    <div class="settings-section">
      <div class="section-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <h2 class="section-title">Obsidian Sync</h2>
          <p class="section-desc">Bidirectional notes sync between project <code>00_Notes/</code> and your Obsidian Vault</p>
        </div>
        <button id="trigger-sync-btn" class="btn btn-primary">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          Sync Vault
        </button>
      </div>

      <div id="sync-console" class="log-console" style="display: none;">
        <div class="console-top-bar">
          <span class="console-title font-mono">Sync Stream</span>
          <span id="sync-time-stamp" class="console-time font-mono">Ready</span>
        </div>
        <div id="sync-log-entries" class="console-body font-mono" style="font-size: 0.75rem;"></div>
      </div>
    </div>

    <!-- System Storage Paths -->
    <div class="settings-section">
      <div class="section-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <h2 class="section-title">Workspace Storage Paths</h2>
          <p class="section-desc">Active workspace locations from <code>00_System/Config/config.json</code></p>
        </div>
        <button id="toggle-edit-paths-btn" class="btn btn-secondary" style="font-size: 0.785rem;">
          ${icons.edit}
          <span id="edit-paths-btn-text">Edit Paths</span>
        </button>
      </div>
      <div id="paths-list-container">
        ${hasCache ? '' : `
          <div class="loading-state" style="padding: 1.5rem;">
            <div class="spinner"></div>
            <p>Loading storage paths...</p>
          </div>
        `}
      </div>
    </div>

    <!-- External Mounts & RAID Drives -->
    <div class="settings-section">
      <div class="section-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <h2 class="section-title">External Mounts &amp; Connected Drives</h2>
          <p class="section-desc">Add external RAID arrays, secondary SSDs, or custom staging folders</p>
        </div>
        <button id="btn-add-mount-toggle" class="btn btn-secondary" style="font-size: 0.785rem;">
          ${icons.plus}
          <span>Add Storage Mount</span>
        </button>
      </div>
      <div id="mounts-list-container">
        <div class="loading-state" style="padding: 1.5rem;">
          <div class="spinner"></div>
          <p>Loading external mounts...</p>
        </div>
      </div>
    </div>

    <!-- Desktop Explorer Preferences -->
    <div class="settings-section">
      <div class="section-header" style="margin-bottom: 0.85rem;">
        <h2 class="section-title">Desktop Explorer Preferences</h2>
        <p class="section-desc">Customize default view layout and interactive behaviors</p>
      </div>
      <div style="background: var(--surface-bg-card); padding: 1.25rem; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); display: flex; flex-direction: column; gap: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;">
          <div>
            <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary);">Default Directory Layout</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.15rem;">Initial view mode used when opening a new directory</div>
          </div>
          <select id="pref-default-view-select" class="form-input font-mono" style="width: auto; min-width: 160px; padding: 0.35rem 0.65rem;">
            <option value="grid">Large Icons Grid</option>
            <option value="details">Details Table</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Category Blueprints Section -->
    <div style="margin-top: 1.75rem; margin-bottom: 1.5rem;">
      <div class="section-header" style="margin-bottom: 0.85rem;">
        <h2 class="section-title">Category Blueprints &amp; Templates</h2>
        <p class="section-desc">Manage project category blueprints and scaffolding from <code>00_System/Config/categories.json</code></p>
      </div>
      <div id="categories-table-container">
        ${hasCache ? '' : `
          <div class="loading-state" style="padding: 1.5rem;">
            <div class="spinner"></div>
            <p>Loading blueprints...</p>
          </div>
        `}
      </div>
    </div>
  `;

  function renderPaths(configData) {
    currentConfigData = configData;
    const pathsContainer = document.getElementById("paths-list-container");
    if (!pathsContainer) return;
    const paths = configData?.paths || {};
    const editablePaths = Object.fromEntries(
      Object.entries(paths).filter(([key]) => !["root_path", "templates_path"].includes(key))
    );

    if (isEditingPaths) {
      pathsContainer.innerHTML = `
        <form id="edit-paths-form" class="studio-form" style="background: var(--surface-bg-card); padding: 1.25rem; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            ${Object.entries(editablePaths).map(([key, info]) => `
              <div class="form-group">
                <label class="form-label font-mono" for="path-input-${key}" style="text-transform: none;">${key}</label>
                <input type="text" id="path-input-${key}" name="${key}" class="form-input font-mono" value="${info.path || ''}" required />
              </div>
            `).join("")}

            <p class="form-hint">The system root and templates path are read-only here. Use <code>cos config edit</code> to change them.</p>
            <div class="form-group" style="padding: 0.75rem 1rem; border-radius: var(--radius-sm); background: var(--bg-app); border: 1px dashed var(--border-subtle); margin-top: 0.5rem;">
              <label class="checkbox-label" style="display: flex; align-items: flex-start; gap: 0.65rem; cursor: pointer;">
                <input type="checkbox" id="migrate-files-check" style="margin-top: 0.2rem; accent-color: var(--color-primary); width: 15px; height: 15px;" />
                <div>
                  <span style="font-weight: 600; font-size: 0.825rem; color: var(--text-primary);">Migrate &amp; copy existing files to new locations</span>
                  <p style="font-size: 0.725rem; color: var(--text-muted); margin-top: 0.15rem;">
                    If changing a folder location, copy all existing contents from old path to the newly configured path.
                  </p>
                </div>
              </label>
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 0.75rem;">
              <button type="button" class="btn btn-secondary" id="cancel-edit-paths-btn">Cancel</button>
              <button type="submit" class="btn btn-primary" id="save-paths-btn">
                ${icons.check} Save Configuration
              </button>
            </div>
          </div>
        </form>
      `;

      document.getElementById("cancel-edit-paths-btn")?.addEventListener("click", () => {
        isEditingPaths = false;
        const btnText = document.getElementById("edit-paths-btn-text");
        if (btnText) btnText.textContent = "Edit Paths";
        renderPaths(currentConfigData);
      });

      document.getElementById("edit-paths-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.target;
        const pathsMap = {};
        Object.keys(editablePaths).forEach(key => {
          const input = form.querySelector(`[name="${key}"]`);
          if (input) pathsMap[key] = input.value.trim();
        });

        const migrateFiles = Boolean(document.getElementById("migrate-files-check")?.checked);
        const saveBtn = document.getElementById("save-paths-btn");
        if (saveBtn) {
          saveBtn.disabled = true;
          saveBtn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Saving...`;
        }

        try {
          const res = await api.updatePaths(pathsMap, migrateFiles);
          showToast("System configuration paths updated successfully", "success");
          isEditingPaths = false;
          const btnText = document.getElementById("edit-paths-btn-text");
          if (btnText) btnText.textContent = "Edit Paths";

          const freshConfig = await api.getConfig();
          renderPaths(freshConfig);
        } catch (err) {
          showToast(`Failed to update paths: ${err.message}`, "error");
          if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = `${icons.check} Save Configuration`;
          }
        }
      });

      return;
    }

    pathsContainer.innerHTML = `
      <div class="path-list">
        ${Object.entries(paths).map(([key, info]) => `
          <div class="path-item">
            <div class="path-meta">
              <div class="path-title-row">
                <span class="path-name">${key}</span>
                <span class="path-status ${info.exists ? 'status-ok' : 'status-missing'}">
                  ${info.exists ? 'Connected' : 'Missing'}
                </span>
              </div>
              <span class="path-val font-mono">${info.path}</span>
            </div>
            <button class="icon-button copy-path-btn" data-copy="${info.path}" title="Copy path" aria-label="Copy path">
              ${icons.copy}
            </button>
          </div>
        `).join("")}
      </div>
    `;

    pathsContainer.querySelectorAll(".copy-path-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const text = btn.getAttribute("data-copy");
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          showToast("Path copied to clipboard", "info", 1500);
        } catch (err) {
          showToast("Path copied", "info", 1500);
        }
      });
    });
  }

  document.getElementById("toggle-edit-paths-btn")?.addEventListener("click", () => {
    isEditingPaths = !isEditingPaths;
    const btnText = document.getElementById("edit-paths-btn-text");
    if (btnText) btnText.textContent = isEditingPaths ? "Cancel Edit" : "Edit Paths";
    renderPaths(currentConfigData);
  });

  let isAddingMount = false;

  function renderMounts(configData) {
    const mountsContainer = document.getElementById("mounts-list-container");
    if (!mountsContainer) return;

    const rawConfig = configData?.config || configData || {};
    const mounts = rawConfig.external_mounts || [];

    if (isAddingMount) {
      mountsContainer.innerHTML = `
        <form id="add-mount-form" class="studio-form" style="background: var(--surface-bg-card); padding: 1.25rem; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
          <div style="display: flex; flex-direction: column; gap: 0.85rem;">
            <div class="form-group">
              <label class="form-label" for="mount-name-input">Mount Label / Drive Name</label>
              <input type="text" id="mount-name-input" class="form-input" placeholder="e.g. Media RAID (E:), Secondary SSD" required />
            </div>
            <div class="form-group">
              <label class="form-label font-mono" for="mount-path-input">Drive or Folder Path</label>
              <input type="text" id="mount-path-input" class="form-input font-mono" placeholder="e.g. E:\\ or D:\\Footage_Staging" required />
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 0.5rem;">
              <button type="button" class="btn btn-secondary" id="cancel-add-mount-btn">Cancel</button>
              <button type="submit" class="btn btn-primary" id="save-new-mount-btn">
                ${icons.plus} Add Mount
              </button>
            </div>
          </div>
        </form>
      `;

      document.getElementById("cancel-add-mount-btn")?.addEventListener("click", () => {
        isAddingMount = false;
        renderMounts(currentConfigData);
      });

      document.getElementById("add-mount-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("mount-name-input")?.value.trim();
        const p = document.getElementById("mount-path-input")?.value.trim();
        if (!p) return;

        const updated = [...mounts, { name: name || p, path: p }];
        try {
          await api.updateMounts(updated);
          showToast(`Added external mount: ${name || p}`, "success");
          isAddingMount = false;
          const fresh = await api.getConfig();
          currentConfigData = fresh;
          renderMounts(fresh);
        } catch (err) {
          showToast(`Failed to add mount: ${err.message}`, "error");
        }
      });
      return;
    }

    if (mounts.length === 0) {
      mountsContainer.innerHTML = `
        <div style="background: var(--surface-bg-card); padding: 1.25rem; border-radius: var(--radius-md); border: 1px dashed var(--border-subtle); text-align: center; color: var(--text-muted); font-size: 0.8rem;">
          <p>No custom external mounts configured yet. Click "Add Storage Mount" to mount external drives or folders.</p>
        </div>
      `;
      return;
    }

    mountsContainer.innerHTML = `
      <div class="path-list">
        ${mounts.map((m, idx) => `
          <div class="path-item">
            <div class="path-meta">
              <div class="path-title-row">
                <span class="path-name mount-label" style="color: var(--color-accent-cyan);"></span>
                <span class="path-status status-ok">Configured</span>
              </div>
              <span class="path-val font-mono mount-path"></span>
            </div>
            <button class="icon-button remove-mount-btn" data-index="${idx}" title="Remove Mount" aria-label="Remove mount" style="color: var(--color-danger);">
              ${icons.x}
            </button>
          </div>
        `).join("")}
      </div>
    `;

    mountsContainer.querySelectorAll(".path-item").forEach((item, idx) => {
      item.querySelector(".mount-label").textContent = mounts[idx].name || mounts[idx].path;
      item.querySelector(".mount-path").textContent = mounts[idx].path;
    });

    mountsContainer.querySelectorAll(".remove-mount-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const idx = parseInt(btn.getAttribute("data-index"), 10);
        const updated = mounts.filter((_, i) => i !== idx);
        try {
          await api.updateMounts(updated);
          showToast("Storage mount removed", "info");
          const fresh = await api.getConfig();
          currentConfigData = fresh;
          renderMounts(fresh);
        } catch (err) {
          showToast(`Failed: ${err.message}`, "error");
        }
      });
    });
  }

  document.getElementById("btn-add-mount-toggle")?.addEventListener("click", () => {
    isAddingMount = !isAddingMount;
    renderMounts(currentConfigData);
  });

  const prefSelect = document.getElementById("pref-default-view-select");
  if (prefSelect) {
    prefSelect.value = localStorage.getItem("cos_last_global_view") || "grid";
    prefSelect.addEventListener("change", () => {
      localStorage.setItem("cos_last_global_view", prefSelect.value);
      showToast(`Default view layout set to: ${prefSelect.value === 'grid' ? 'Large Icons Grid' : 'Details Table'}`, "info", 1500);
    });
  }

  let selectedCategoryKey = "Video";

  function renderCategories(catData) {
    const categoriesContainer = document.getElementById("categories-table-container");
    if (!categoriesContainer) return;
    const categories = catData?.categories || {};
    const categoryKeys = Object.keys(categories);
    if (categoryKeys.length === 0) return;

    if (!categories[selectedCategoryKey]) {
      selectedCategoryKey = categoryKeys[0];
    }

    const currentCat = categories[selectedCategoryKey] || {};
    const tStruct = currentCat.template_structure || {};
    const folders = Object.keys(tStruct).length > 0 ? Object.keys(tStruct) : (currentCat.folder_structure || []);
    const catIconSvg = getCategoryIconSvg(selectedCategoryKey);
    const totalFiles = Object.values(tStruct).reduce((acc, list) => acc + (Array.isArray(list) ? list.length : 0), 0);

    categoriesContainer.innerHTML = `
      <div class="blueprint-inspector-container">
        <!-- Left Column: Category Navigation List -->
        <div class="blueprint-nav-column">
          <div class="blueprint-nav-header">
            <span class="blueprint-nav-heading">Categories</span>
            <span class="blueprint-count-pill font-mono">${categoryKeys.length}</span>
          </div>
          <div class="blueprint-nav-list">
            ${categoryKeys.map(key => {
              const cat = categories[key] || {};
              const isSelected = key === selectedCategoryKey;
              const icon = getCategoryIconSvg(key);
              const struct = cat.template_structure || {};
              const fCount = Object.keys(struct).length || (cat.folder_structure || []).length || 0;
              return `
                <button type="button" class="blueprint-nav-item ${isSelected ? 'is-selected' : ''}" data-cat-key="${key}">
                  <div class="blueprint-nav-item-left">
                    <span class="blueprint-nav-icon">${icon}</span>
                    <span class="blueprint-nav-name">${key}</span>
                  </div>
                  <span class="blueprint-nav-badge font-mono">${fCount} dirs</span>
                </button>
              `;
            }).join("")}
          </div>
        </div>

        <!-- Right Column: Detail Blueprint Panel -->
        <div class="blueprint-detail-panel">
          <!-- Detail Header -->
          <div class="blueprint-detail-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
            <div class="blueprint-detail-identity">
              <div class="blueprint-detail-icon-box">
                ${catIconSvg}
              </div>
              <div>
                <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
                  <h3 class="blueprint-detail-title">${selectedCategoryKey}</h3>
                  <span class="status-indicator-tag ${currentCat.enabled !== false ? 'is-active' : ''}">
                    <span class="status-dot"></span>
                    <span>${currentCat.enabled !== false ? 'Active Blueprint' : 'Disabled'}</span>
                  </span>
                </div>
                <p class="blueprint-detail-desc">${currentCat.description || 'Standard project scaffold and template structure'}</p>
              </div>
            </div>
            <button class="btn btn-secondary btn-toggle-cat" data-cat-key="${selectedCategoryKey}" style="font-size: 0.75rem; padding: 0.25rem 0.6rem;">
              ${currentCat.enabled !== false ? 'Disable Category' : 'Enable Category'}
            </button>
          </div>

          <!-- Quick Metrics Strip -->
          <div class="blueprint-metrics-strip">
            <div class="blueprint-metric-item">
              <span class="insight-label">Target Directory</span>
              <span class="insight-val font-mono" style="font-size: 0.85rem; color: var(--text-primary);">01_Projects/${currentCat.physical_folder || selectedCategoryKey}/</span>
            </div>
            <div class="blueprint-metric-item">
              <span class="insight-label">Blueprint Subfolders</span>
              <span class="insight-val font-mono" style="font-size: 0.95rem; color: var(--color-primary);">${folders.length} subfolders</span>
            </div>
            <div class="blueprint-metric-item">
              <span class="insight-label">Seeded Template Files</span>
              <span class="insight-val font-mono" style="font-size: 0.95rem; color: var(--color-accent-cyan);">${totalFiles} templates</span>
            </div>
          </div>

          <!-- Structured Folder & Seed Files Breakdown -->
          <div class="blueprint-structure-section">
            <div class="blueprint-section-subheading">Scaffold Directory Blueprint</div>
            <div class="blueprint-folder-breakdown-list">
              ${folders.map(f => {
                const files = tStruct[f] || [];
                const isNotes = f === '00_Notes';
                return `
                  <div class="blueprint-folder-card ${isNotes ? 'is-notes-folder' : ''}">
                    <div class="blueprint-folder-card-header">
                      <div class="blueprint-folder-card-name">
                        <span class="folder-icon">${icons.folder}</span>
                        <strong class="font-mono">${f}/</strong>
                      </div>
                      ${isNotes ? '<span class="status-indicator-tag is-active" style="font-size: 0.65rem;">Obsidian Sync</span>' : ''}
                      ${files.length > 0 && !isNotes ? `<span class="folder-seed-count font-mono">${files.length} ${files.length === 1 ? 'file' : 'files'}</span>` : ''}
                    </div>
                    ${files.length > 0 ? `
                      <div class="blueprint-seed-files-wrap">
                        ${files.map(file => `
                          <span class="seed-file-chip font-mono">
                            <span class="seed-file-icon">${icons.file}</span>
                            <span>${file}</span>
                          </span>
                        `).join("")}
                      </div>
                    ` : `
                      <div class="blueprint-empty-folder-hint font-mono">Root subfolder</div>
                    `}
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        </div>
      </div>
    `;

    categoriesContainer.querySelectorAll(".blueprint-nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-cat-key");
        if (key && key !== selectedCategoryKey) {
          selectedCategoryKey = key;
          renderCategories(catData);
        }
      });
    });

    categoriesContainer.querySelector(".btn-toggle-cat")?.addEventListener("click", async () => {
      const isEnabled = currentCat.enabled !== false;
      const remaining = Object.keys(categories).filter(key => key !== selectedCategoryKey && categories[key].enabled !== false);
      if (isEnabled && remaining.length === 0) {
        showToast("Keep at least one project category enabled", "warning");
        return;
      }
      const defaultCategory = isEnabled && selectedCategoryKey === catData.default_category
        ? remaining[0]
        : catData.default_category;
      categories[selectedCategoryKey].enabled = !isEnabled;
      try {
        await api.updateCategories(categories, defaultCategory);
        showToast(`${selectedCategoryKey} category ${!isEnabled ? 'enabled' : 'disabled'}`, "success");
        renderCategories({ ...catData, categories, default_category: defaultCategory });
      } catch (err) {
        categories[selectedCategoryKey].enabled = isEnabled;
        showToast(`Failed to update category: ${err.message}`, "error");
      }
    });
  }

  async function loadSettingsData() {
    try {
      if (hasCache) {
        renderPaths(cachedConfig);
        renderMounts(cachedConfig);
        renderCategories(cachedCats);
      }

      api.getConfigSWR((freshConfig) => {
        renderPaths(freshConfig);
        renderMounts(freshConfig);
      });

      api.getCategoriesSWR((freshCats) => {
        renderCategories(freshCats);
      });
    } catch (err) {
      console.error("Error loading settings data:", err);
      showToast("Error loading system settings", "error");
    }
  }

  // Handle Sync
  const syncBtn = document.getElementById("trigger-sync-btn");
  const syncConsole = document.getElementById("sync-console");
  const syncLogEntries = document.getElementById("sync-log-entries");
  const syncTimeStamp = document.getElementById("sync-time-stamp");

  syncBtn?.addEventListener("click", () => {
    syncBtn.disabled = true;
    syncBtn.innerHTML = `
      <span class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0;"></span>
      Syncing...
    `;

    if (syncConsole) {
      syncConsole.style.display = "block";
      if (syncLogEntries) {
        syncLogEntries.innerHTML = `<div class="log-entry log-info"><span>[Engine]</span> <span>Connecting to /api/sync/stream...</span></div>`;
      }
    }

    let syncedChanges = 0;
    let projectsSynced = 0;

    api.streamSync(
      (event) => {
        if (!syncLogEntries) return;

        if (event.event === "start") {
          syncLogEntries.innerHTML += `<div class="log-entry log-info"><span>[Engine]</span> <span>${event.message}</span></div>`;
        } else if (event.event === "scanning_project") {
          projectsSynced++;
          if (syncTimeStamp) {
            syncTimeStamp.textContent = `Scanning: ${event.project}`;
          }
        } else if (event.event === "file_sync") {
          syncedChanges++;
          const typeClass = `log-${event.type || 'info'}`;
          syncLogEntries.innerHTML += `<div class="log-entry ${typeClass}"><span>[${event.project}]</span> <span>${(event.type || 'SYNC').toUpperCase()}: ${event.file} (${event.msg})</span></div>`;
        } else if (event.event === "complete") {
          if (syncTimeStamp) {
            syncTimeStamp.textContent = event.last_sync ? `Synced at ${event.last_sync.substring(11, 19)}` : "Finished";
          }
          syncLogEntries.innerHTML += `<div class="log-entry log-push" style="margin-top: 0.5rem; font-weight: bold;"><span>✨ Sync complete. ${event.total_changes || syncedChanges} operations across ${event.projects_synced || projectsSynced} projects.</span></div>`;
          showToast(`Sync complete: ${event.total_changes || 0} operations`, "success");
        }
        syncLogEntries.scrollTop = syncLogEntries.scrollHeight;
      },
      (err) => {
        showToast(`Sync failed: ${err.message}`, "error");
        if (syncLogEntries) {
          syncLogEntries.innerHTML += `<div class="log-entry log-error"><span>[Error]</span> <span>${err.message}</span></div>`;
        }
        syncBtn.disabled = false;
        syncBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          Sync With Vault
        `;
      },
      (completeData) => {
        syncBtn.disabled = false;
        syncBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          Sync With Vault
        `;
      }
    );
  });

  loadSettingsData();
}
