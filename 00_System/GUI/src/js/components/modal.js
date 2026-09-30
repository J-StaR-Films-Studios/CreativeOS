/**
 * Precision Studio Modals & Dialogs
 * Includes: Project Inspector (with Metadata Editing, Travel, Archive),
 * Resurrect Picker Modal, Confirmation Warning Dialogs, and Live SSE Sync Stream.
 */

import { api, formatBytes } from "../api.js";
import { getCategoryIconSvg, icons } from "../icons.js";
import { openReclaimModal } from "./reclaimModal.js";
import { showToast } from "./toast.js";

let activeModalCloser = null;

export function closeActiveModal() {
  if (activeModalCloser) {
    activeModalCloser();
  }
}

function lockBodyScroll() {
  document.body.style.overflow = "hidden";
}

function unlockBodyScroll() {
  document.body.style.overflow = "";
}

/**
 * Generic Confirmation / Warning Modal
 */
export function openConfirmModal({
  title = "Confirm Action",
  message = "Are you sure you want to proceed?",
  subtext = "",
  confirmText = "Proceed",
  cancelText = "Cancel",
  variant = "warning", // "warning", "danger", "info"
  onConfirm = async () => {},
}) {
  const modalContainer = document.getElementById("modal-container");
  if (!modalContainer) return;

  const isDanger = variant === "danger";
  const accentColor = isDanger ? "var(--color-danger)" : "var(--color-warning)";

  modalContainer.innerHTML = `
    <div class="modal-backdrop" id="confirm-modal-backdrop">
      <div class="modal-dialog modal-dialog-sm" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <div class="modal-header">
          <div class="modal-title-group">
            <div class="modal-category-icon" style="color: ${accentColor};">
              ${isDanger ? icons.error : icons.warning}
            </div>
            <div>
              <div class="modal-eyebrow">
                <span class="status-pill" style="color: ${accentColor}; background: ${accentColor}18;">
                  ${variant.toUpperCase()}
                </span>
              </div>
              <h2 id="confirm-title" class="modal-title">${title}</h2>
            </div>
          </div>
          <button class="modal-close-btn" id="confirm-modal-close-btn" aria-label="Close dialog">
            ${icons.x}
          </button>
        </div>

        <div class="modal-body">
          <div style="padding: 0.5rem 0;">
            <p style="color: var(--text-primary); font-size: 0.875rem; margin-bottom: ${subtext ? '0.35rem' : '0'}; line-height: 1.45;">${message}</p>
            ${subtext ? `<p class="font-mono" style="color: var(--text-muted); font-size: 0.775rem; margin: 0;">${subtext}</p>` : ''}
          </div>
        </div>

        <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 0.65rem;">
          <button class="btn btn-secondary" id="confirm-cancel-btn">${cancelText}</button>
          <button class="btn ${isDanger ? 'btn-danger' : 'btn-primary'}" id="confirm-proceed-btn">
            ${confirmText}
          </button>
        </div>
      </div>
    </div>
  `;

  modalContainer.style.display = "block";
  lockBodyScroll();

  function closeModal() {
    modalContainer.style.display = "none";
    unlockBodyScroll();
    modalContainer.innerHTML = "";
    activeModalCloser = null;
  }

  document.getElementById("confirm-modal-close-btn")?.addEventListener("click", closeModal);
  document.getElementById("confirm-cancel-btn")?.addEventListener("click", closeModal);
  document.getElementById("confirm-modal-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "confirm-modal-backdrop") closeModal();
  });

  document.getElementById("confirm-proceed-btn")?.addEventListener("click", async () => {
    const btn = document.getElementById("confirm-proceed-btn");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Processing...`;
    }
    try {
      await onConfirm();
      closeModal();
    } catch (err) {
      showToast(`Action failed: ${err.message}`, "error");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = confirmText;
      }
    }
  });

  activeModalCloser = closeModal;
}

/**
 * Project Inspector Modal with Editable Metadata, File Explorer Jump, Travel & Archive
 */
export function openProjectInspector(project, categoryConfig = {}, onProjectUpdated = () => {}) {
  const modalContainer = document.getElementById("modal-container");
  if (!modalContainer) return;

  let currentProject = { ...project };
  let isEditMode = false;
  let realEntries = null;
  let isLoadingStructure = true;

  function renderStructureContent() {
    const cat = currentProject.type || "Video";
    const catInfo = categoryConfig[cat] || {};
    const tStruct = catInfo.template_structure || {};
    const templateFolders = Object.keys(tStruct).length > 0
      ? Object.keys(tStruct)
      : (catInfo.folder_structure || ["00_Notes", "01_Footage", "02_Audio", "03_Exports"]);
    const templateSet = new Set(templateFolders);

    let nodes = [];
    let presentBlueprintCount = 0;
    let customCount = 0;
    let missingCount = 0;
    let totalFolders = 0;

    if (realEntries === null) {
      // Initial blueprint fallback while live scan is running
      nodes = templateFolders.map(f => ({ name: f, status: "template", exists: true }));
      presentBlueprintCount = templateFolders.length;
      totalFolders = templateFolders.length;
    } else {
      const diskDirs = realEntries.filter(e => e.is_dir);
      const diskDirMap = new Map(diskDirs.map(d => [d.name, d]));
      totalFolders = diskDirs.length;

      // 1. Template folders on disk
      templateFolders.forEach(f => {
        if (diskDirMap.has(f)) {
          nodes.push({ name: f, status: "template", exists: true });
          presentBlueprintCount++;
        }
      });

      // 2. Custom user-added folders on disk
      diskDirs.forEach(d => {
        if (!templateSet.has(d.name)) {
          nodes.push({ name: d.name, status: "custom", exists: true });
          customCount++;
        }
      });

      // 3. Missing blueprint folders
      templateFolders.forEach(f => {
        if (!diskDirMap.has(f)) {
          nodes.push({ name: f, status: "missing", exists: false });
          missingCount++;
        }
      });
    }

    return `
      <div class="modal-section-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
        <div style="display: flex; align-items: center; gap: 0.45rem;">
          <h4 class="modal-section-heading" style="margin-bottom: 0;">Directory Structure</h4>
          <span class="folder-count-tag font-mono">${totalFolders} folder${totalFolders === 1 ? '' : 's'}</span>
          ${isLoadingStructure ? `<span class="spinner" style="width: 11px; height: 11px; border-width: 2px;"></span>` : ''}
        </div>
        <div class="structure-legend-pills font-mono">
          <span class="legend-pill legend-template" title="Standard folders created from category template">
            Template (${presentBlueprintCount})
          </span>
          <span class="legend-pill legend-custom" title="Custom folders created by user">
            + Custom (${customCount})
          </span>
          ${missingCount > 0 ? `
            <span class="legend-pill legend-missing" title="Template folders not found on disk">
              Missing (${missingCount})
            </span>
          ` : ''}
        </div>
      </div>
      <div class="folder-tree-view">
        <div class="tree-root">
          <span class="tree-icon">${icons.folder}</span>
          <strong>${currentProject.slug || currentProject.name}</strong>
        </div>
        <div class="tree-branches">
          ${nodes.map((node, idx) => `
            <div class="tree-node ${node.status === 'missing' ? 'is-missing-node' : ''}">
              <span class="tree-line">${idx === nodes.length - 1 ? '└─' : '├─'}</span>
              <span class="tree-folder-icon">${icons.folder}</span>
              <span class="tree-name font-mono ${node.name === '00_Notes' ? 'notes-highlight' : ''}" title="${node.name}">${node.name}</span>
              
              ${node.status === 'template' ? `
                <span class="tree-badge-blueprint font-mono">Template</span>
                ${node.name === '00_Notes' ? '<span class="tree-badge-obsidian font-mono">Obsidian Vault</span>' : ''}
              ` : node.status === 'custom' ? `
                <span class="tree-badge-custom font-mono">+ Custom</span>
              ` : `
                <span class="tree-badge-missing font-mono">Missing from template</span>
              `}
            </div>
          `).join("")}
          <div class="tree-node">
            <span class="tree-line">└─</span>
            <span class="tree-file-icon">${icons.file}</span>
            <span class="tree-name font-mono">.project_meta.json</span>
            <span class="tree-badge-system font-mono">System</span>
          </div>
        </div>
      </div>
    `;
  }

  function renderModal() {
    const isStale = currentProject.is_stale || currentProject.status === "stale";
    const cat = currentProject.type || "Video";

    const fullPath = currentProject.path || "";
    const relPath = currentProject.relative_path || currentProject.slug || "";
    const catIconSvg = getCategoryIconSvg(cat);

    modalContainer.innerHTML = `
      <div class="modal-backdrop" id="modal-backdrop">
        <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="modal-title">
          <!-- Modal Header -->
          <div class="modal-header">
            <div class="modal-title-group">
              <div class="modal-category-icon">
                ${catIconSvg}
              </div>
              <div>
                <div class="modal-eyebrow">
                  <span class="category-pill-tag">${cat}</span>
                  <span class="status-pill ${isStale ? 'status-stale' : 'status-active'}">
                    ${isStale ? 'Stale' : 'Active'}
                  </span>
                </div>
                <h2 id="modal-title" class="modal-title" title="${currentProject.name}">${currentProject.name}</h2>
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.45rem;">
              <button class="btn btn-secondary" id="modal-toggle-edit-btn" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;">
                ${isEditMode ? icons.x : icons.edit}
                <span>${isEditMode ? 'Cancel' : 'Edit'}</span>
              </button>
              <button class="modal-close-btn" id="modal-close-btn" aria-label="Close modal">
                ${icons.x}
              </button>
            </div>
          </div>

          <!-- Modal Body -->
          <div class="modal-body">
            ${isEditMode ? `
              <!-- Editable Metadata Form -->
              <div class="modal-section">
                <form id="edit-metadata-form" class="studio-form">
                  <div class="form-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
                    <div class="form-group">
                      <label class="form-label" for="edit-project-name">Project Title *</label>
                      <input type="text" id="edit-project-name" class="form-input font-mono" value="${currentProject.name || ''}" required />
                    </div>

                    <div class="form-group">
                      <label class="form-label" for="edit-project-client">Client</label>
                      <input type="text" id="edit-project-client" class="form-input" value="${currentProject.client && currentProject.client !== 'None' ? currentProject.client : ''}" placeholder="Internal / None" />
                    </div>
                  </div>

                  <div class="form-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-top: 0.75rem;">
                    <div class="form-group">
                      <label class="form-label" for="edit-project-category">Category</label>
                      <select id="edit-project-category" class="form-select">
                        ${Object.keys(categoryConfig).map(k => `
                          <option value="${k}" ${k === cat ? 'selected' : ''}>${k}</option>
                        `).join("")}
                      </select>
                    </div>

                    <div class="form-group">
                      <label class="form-label" for="edit-project-status">Activity Status</label>
                      <select id="edit-project-status" class="form-select">
                        <option value="active" ${!isStale ? 'selected' : ''}>Active Project</option>
                        <option value="stale" ${isStale ? 'selected' : ''}>Stale (Inactive)</option>
                      </select>
                    </div>
                  </div>

                  <div class="form-group" style="margin-top: 0.75rem;">
                    <label class="form-label" for="edit-project-desc">Description</label>
                    <textarea id="edit-project-desc" class="form-textarea" rows="2" placeholder="Brief project summary...">${currentProject.description || ''}</textarea>
                  </div>

                  <div class="form-group" style="margin-top: 0.75rem;">
                    <label class="form-label" for="edit-project-tags">Tags (comma separated)</label>
                    <input type="text" id="edit-project-tags" class="form-input font-mono" value="${Array.isArray(currentProject.tags) ? currentProject.tags.join(', ') : (currentProject.tags || '')}" placeholder="youtube, edit, client, v1" />
                  </div>

                  <div class="form-actions" style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
                    <button type="button" class="btn btn-secondary" id="edit-cancel-btn">Cancel</button>
                    <button type="submit" class="btn btn-primary" id="edit-save-btn">
                      ${icons.save || icons.check}
                      Save Changes
                    </button>
                  </div>
                </form>
              </div>
            ` : `
              <!-- Read-only Metrics Grid (3 stats) -->
              <div class="modal-metrics-grid">
                <div class="modal-metric-card">
                  <span class="metric-label">Total Size</span>
                  <span class="metric-val">${formatBytes(currentProject.total_size || 0)}</span>
                  <span class="metric-sub">${currentProject.file_count !== undefined ? `${currentProject.file_count} files` : 'Workspace footprint'}</span>
                </div>
                <div class="modal-metric-card">
                  <span class="metric-label">Media</span>
                  <span class="metric-val" style="color: var(--color-accent-cyan);">${formatBytes(currentProject.media_size || 0)}</span>
                  <span class="metric-sub">RAW &amp; Audio</span>
                </div>
                <div class="modal-metric-card">
                  <span class="metric-label">Reclaimable</span>
                  <span class="metric-val" style="color: ${(currentProject.reclaimable_size || 0) > 0 ? 'var(--color-warning)' : 'var(--text-dim)'};">${formatBytes(currentProject.reclaimable_size || 0)}</span>
                  <span class="metric-sub">Caches &amp; Trash</span>
                </div>
              </div>

              <!-- Metadata Properties Table -->
              <div class="modal-section">
                <div class="modal-props-grid">
                  <div class="prop-item">
                    <span class="prop-label">Client</span>
                    <span class="prop-val">${currentProject.client && currentProject.client !== "None" ? currentProject.client : "Internal"}</span>
                  </div>
                  <div class="prop-item">
                    <span class="prop-label">Created</span>
                    <span class="prop-val font-mono">${currentProject.created || "—"}</span>
                  </div>
                  <div class="prop-item">
                    <span class="prop-label">Modified</span>
                    <span class="prop-val font-mono">${currentProject.last_meaningful_update ? currentProject.last_meaningful_update.substring(0, 10) : '—'}</span>
                  </div>
                  <div class="prop-item">
                    <span class="prop-label">Vault Link</span>
                    <span class="prop-val font-mono" style="color: var(--color-success);">00_Notes &harr; Vault</span>
                  </div>
                </div>
                ${currentProject.description ? `
                  <p style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; margin-top: 0.35rem;">
                    ${currentProject.description}
                  </p>
                ` : ''}
              </div>
            `}

            <!-- Location Row -->
            <div class="modal-section">
              <h4 class="modal-section-heading">Workspace Path</h4>
              <div class="modal-path-box">
                <div class="path-display-row">
                  <span class="path-chip">Relative</span>
                  <code class="path-code font-mono" title="${relPath}">${relPath}</code>
                  <button class="copy-path-btn" data-copy="${relPath}" title="Copy relative path" aria-label="Copy relative path">${icons.copy}</button>
                </div>
                <div class="path-display-row">
                  <span class="path-chip">System</span>
                  <code class="path-code font-mono" title="${fullPath}">${fullPath}</code>
                  <button class="copy-path-btn" data-copy="${fullPath}" title="Copy full path" aria-label="Copy full path">${icons.copy}</button>
                </div>
              </div>
            </div>

            <!-- Workspace Actions Strip -->
            <div class="modal-section">
              <h4 class="modal-section-heading">Actions</h4>
              <div class="workspace-actions-grid" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem;">
                <button class="btn btn-secondary action-btn-explorer" id="modal-explore-files-btn" style="font-size: 0.785rem; padding: 0.4rem 0.65rem;">
                  ${icons.folderOpen}
                  Browse Files
                </button>
                <button class="btn btn-secondary action-btn-openos" id="modal-open-native-btn" style="font-size: 0.785rem; padding: 0.4rem 0.65rem;">
                  ${icons.externalLink}
                  Open in OS
                </button>
                <button class="btn btn-secondary action-btn-travel" id="modal-travel-btn" style="font-size: 0.785rem; padding: 0.4rem 0.65rem;" title="Export to Shuttle Drive">
                  ${icons.travel}
                  Shuttle Travel
                </button>
                <button class="btn btn-secondary action-btn-archive" id="modal-archive-btn" style="color: var(--color-warning); font-size: 0.785rem; padding: 0.4rem 0.65rem;" title="Move to Cold Storage">
                  ${icons.archive}
                  Archive
                </button>
                ${(currentProject.reclaimable_size || 0) > 0 ? `
                  <button class="btn btn-secondary action-btn-reclaim" id="modal-reclaim-btn" style="color: var(--color-warning); font-size: 0.785rem; padding: 0.4rem 0.65rem;" title="Clean Dependencies & Caches">
                    ${icons.zap}
                    Reclaim (${formatBytes(currentProject.reclaimable_size)})
                  </button>
                ` : ''}
              </div>
            </div>

            <!-- Live Differentiated Blueprint Structure -->
            <div class="modal-section" id="modal-structure-container">
              ${renderStructureContent()}
            </div>
          </div>

          <!-- Modal Footer Actions -->
          <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-copy-cd-btn" style="font-size: 0.8rem;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
              Copy Terminal cd
            </button>
            <a href="#storage?project=${encodeURIComponent(currentProject.slug || currentProject.name || '')}" class="btn btn-primary" id="modal-view-storage-btn" style="font-size: 0.8rem;">
              Storage Analytics
            </a>
          </div>
        </div>
      </div>
    `;

    // Reattach Event Handlers
    attachModalHandlers();
  }

  // Asynchronously scan real live directory structure
  if (currentProject.path) {
    api.listFiles(currentProject.path).then(res => {
      realEntries = res.entries || [];
      isLoadingStructure = false;
      const structureEl = document.getElementById("modal-structure-container");
      if (structureEl) {
        structureEl.innerHTML = renderStructureContent();
      }
    }).catch(() => {
      isLoadingStructure = false;
      const structureEl = document.getElementById("modal-structure-container");
      if (structureEl) {
        structureEl.innerHTML = renderStructureContent();
      }
    });
  }

  function closeModal() {
    modalContainer.style.display = "none";
    unlockBodyScroll();
    modalContainer.innerHTML = "";
    activeModalCloser = null;
  }

  function attachModalHandlers() {
    document.getElementById("modal-close-btn")?.addEventListener("click", closeModal);
    document.getElementById("modal-backdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "modal-backdrop") closeModal();
    });

    document.getElementById("modal-view-storage-btn")?.addEventListener("click", closeModal);

    // Toggle Edit Mode
    document.getElementById("modal-toggle-edit-btn")?.addEventListener("click", () => {
      isEditMode = !isEditMode;
      renderModal();
    });

    document.getElementById("cancel-edit-btn")?.addEventListener("click", () => {
      isEditMode = false;
      renderModal();
    });

    // Live Path Preview Function
    const updateFsPreview = () => {
      const nameInput = document.getElementById("edit-project-name");
      const clientInput = document.getElementById("edit-project-client");
      const categorySelect = document.getElementById("edit-project-category");
      const syncCheck = document.getElementById("edit-sync-filesystem");
      const previewMsg = document.getElementById("fs-sync-preview-msg");

      if (!previewMsg) return;

      const currentRel = currentProject.relative_path || currentProject.name;
      const newTitle = nameInput?.value.trim() || currentProject.name;
      const newClient = clientInput?.value.trim() || "";
      const newCat = categorySelect?.value || currentProject.type || "Video";

      // Extract date prefix if present
      const origDir = currentProject.path ? currentProject.path.split(/[\\/]/).pop() : currentProject.name;
      let datePrefix = "";
      if (origDir && origDir.length >= 11 && origDir[4] === "-" && origDir[7] === "-" && origDir[10] === "_") {
        datePrefix = origDir.substring(0, 11);
      }
      const newSlug = newTitle.replace(/\s+/g, "_");
      const newDirName = datePrefix ? `${datePrefix}${newSlug}` : newSlug;

      let targetRel = "";
      if (newClient && newClient.toLowerCase() !== "none" && newClient.toLowerCase() !== "internal") {
        targetRel = `Clients/${newClient}/${newDirName}`;
      } else {
        targetRel = `${newCat}/${newDirName}`;
      }

      if (syncCheck?.checked) {
        if (targetRel !== currentRel) {
          previewMsg.innerHTML = `<span style="color: var(--color-success); font-weight: 600;">Moving directory on disk:</span> <code>${currentRel}</code> &rarr; <code>${targetRel}</code>`;
        } else {
          previewMsg.innerHTML = `<span style="color: var(--text-muted);">Folder name already matches disk path: <code>${currentRel}</code></span>`;
        }
      } else {
        previewMsg.innerHTML = `<span style="color: var(--text-muted);">Metadata only (folder location stays: <code>${currentRel}</code>)</span>`;
      }
    };

    const nameInputEl = document.getElementById("edit-project-name");
    const clientInputEl = document.getElementById("edit-project-client");
    const categorySelectEl = document.getElementById("edit-project-category");
    const syncCheckEl = document.getElementById("edit-sync-filesystem");

    nameInputEl?.addEventListener("input", updateFsPreview);
    clientInputEl?.addEventListener("input", updateFsPreview);
    categorySelectEl?.addEventListener("change", updateFsPreview);
    syncCheckEl?.addEventListener("change", updateFsPreview);

    // Save Metadata Form Submit
    document.getElementById("edit-metadata-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const newName = nameInputEl?.value.trim();
      if (!newName) {
        showToast("Project title cannot be empty", "error");
        return;
      }

      const tagsInput = document.getElementById("edit-project-tags");
      const descInput = document.getElementById("edit-project-desc");

      const tagsArray = (tagsInput?.value || "")
        .split(",")
        .map(t => t.trim())
        .filter(Boolean);

      const payload = {
        name: newName,
        client: clientInputEl?.value.trim() || "None",
        category: categorySelectEl?.value || currentProject.type,
        tags: tagsArray,
        description: descInput?.value.trim() || "",
        sync_filesystem: Boolean(syncCheckEl?.checked),
      };

      const saveBtn = document.getElementById("save-metadata-btn");
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Saving...`;
      }

      try {
        const lookupKey = currentProject.path || currentProject.relative_path || currentProject.slug || currentProject.name;
        const res = await api.updateProject(lookupKey, payload);
        if (res.moved) {
          showToast(`Project updated and moved to ${res.project.relative_path}`, "success");
        } else {
          showToast("Project metadata updated successfully", "success");
        }

        currentProject = {
          ...currentProject,
          ...res.project,
          path: res.project.path || res.new_path || currentProject.path,
          relative_path: res.project.relative_path || currentProject.relative_path,
          name: res.project.name,
          client: res.project.client,
          type: res.project.type,
          tags: res.project.tags,
          description: res.project.description,
        };
        isEditMode = false;
        renderModal();
        onProjectUpdated(currentProject);
      } catch (err) {
        showToast(`Failed to update metadata: ${err.message}`, "error");
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.innerHTML = `${icons.check} Save Changes`;
        }
      }
    });

    // Browse in Explorer Action
    document.getElementById("modal-explore-files-btn")?.addEventListener("click", () => {
      closeModal();
      window.location.hash = `#explorer?path=${encodeURIComponent(currentProject.path || "")}`;
    });

    // Open Natively in OS
    document.getElementById("modal-open-native-btn")?.addEventListener("click", async () => {
      try {
        const targetPath = currentProject.path || currentProject.relative_path || currentProject.slug || currentProject.name || "";
        showToast("Opening project folder natively...", "info", 1500);
        await api.openPath(targetPath);
      } catch (err) {
        showToast(`Failed to open: ${err.message}`, "error");
      }
    });

    // Travel to Shuttle
    document.getElementById("modal-travel-btn")?.addEventListener("click", () => {
      openConfirmModal({
        title: "Launch Shuttle Travel",
        message: `Export and sync '${currentProject.name}' to your external Shuttle Drive?`,
        subtext: `Target: <SHUTTLE_PATH>/Projects/${currentProject.relative_path || currentProject.slug}`,
        confirmText: "Launch Travel",
        variant: "info",
        onConfirm: async () => {
          const res = await api.travelProject(currentProject.path || currentProject.name || currentProject.slug);
          showToast(`Exported to Shuttle: ${res.dest_path}`, "success", 3000);
        },
      });
    });

    // Archive Project
    document.getElementById("modal-archive-btn")?.addEventListener("click", () => {
      openConfirmModal({
        title: "Archive Project to Cold Storage",
        message: `Move '${currentProject.name}' from active projects to the Cold Archive?`,
        subtext: "This safely moves project files out of the active studio tree. You can resurrect it anytime.",
        confirmText: "Archive Project",
        variant: "danger",
        onConfirm: async () => {
          const res = await api.archiveProject(currentProject.path || currentProject.name || currentProject.slug);
          showToast(`Project archived to ${res.archive_path}`, "success", 3000);
          closeModal();
          onProjectUpdated(null); // Signal removal
        },
      });
    });

    // Reclaim Cache & Dependencies from Metric Card
    const reclaimCard = document.getElementById("modal-metric-reclaim-card");
    if (reclaimCard && (currentProject.reclaimable_size || 0) > 0) {
      reclaimCard.addEventListener("click", () => {
        openReclaimModal(currentProject, (res) => {
          currentProject.reclaimable_size = res.remaining_reclaimable || 0;
          renderModal();
          if (onProjectUpdated) onProjectUpdated(currentProject);
        });
      });
    }

    // Copy Terminal CD button
    document.getElementById("modal-copy-cd-btn")?.addEventListener("click", async () => {
      const fullTarget = currentProject.path || "";
      const cmd = `cd "${fullTarget}"`;
      try {
        await navigator.clipboard.writeText(cmd);
        showToast("Copied terminal command: " + cmd, "info", 2000);
      } catch (err) {
        const temp = document.createElement("textarea");
        temp.value = cmd;
        document.body.appendChild(temp);
        temp.select();
        document.execCommand("copy");
        document.body.removeChild(temp);
        showToast("Copied terminal command: " + cmd, "info", 2000);
      }
    });

    // Copy path buttons
    modalContainer.querySelectorAll(".copy-path-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const textToCopy = btn.getAttribute("data-copy");
        if (!textToCopy) return;
        try {
          await navigator.clipboard.writeText(textToCopy);
          showToast("Copied to clipboard", "info", 1500);
        } catch (err) {
          showToast("Copied to clipboard", "info", 1500);
        }
      });
    });
  }

  modalContainer.style.display = "block";
  document.body.style.overflow = "hidden";
  activeModalCloser = closeModal;

  renderModal();
}

/**
 * Resurrect Archived Projects Modal Picker
 */
export async function openResurrectModal(onResurrected = () => {}) {
  const modalContainer = document.getElementById("modal-container");
  if (!modalContainer) return;

  modalContainer.innerHTML = `
    <div class="modal-backdrop" id="resurrect-modal-backdrop">
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true" aria-labelledby="resurrect-title">
        <div class="modal-header">
          <div class="modal-title-group">
            <div class="modal-category-icon" style="color: var(--color-accent-cyan); background: rgba(56, 189, 248, 0.1);">
              ${icons.resurrect}
            </div>
            <div>
              <div class="modal-eyebrow">
                <span class="status-pill" style="color: var(--color-accent-cyan); background: rgba(56, 189, 248, 0.1); border-color: rgba(56, 189, 248, 0.2);">
                  COLD STORAGE RESTORE
                </span>
              </div>
              <h2 id="resurrect-title" class="modal-title">Resurrect Archived Project</h2>
            </div>
          </div>
          <button class="modal-close-btn" id="resurrect-close-btn" aria-label="Close modal">
            ${icons.x}
          </button>
        </div>

        <div class="modal-body">
          <div class="search-box" style="margin-bottom: 1rem;">
            <span class="search-icon">${icons.search}</span>
            <input type="text" id="resurrect-search-input" class="search-input" placeholder="Filter archived projects by name or client..." />
          </div>

          <div id="archived-projects-container" style="max-height: 400px; overflow-y: auto;">
            <div class="loading-state">
              <div class="spinner"></div>
              <p>Scanning cold archive index...</p>
            </div>
          </div>
        </div>

        <div class="modal-footer" style="display: flex; justify-content: flex-end;">
          <button class="btn btn-secondary" id="resurrect-cancel-btn">Close</button>
        </div>
      </div>
    </div>
  `;

  modalContainer.style.display = "block";
  lockBodyScroll();

  function closeModal() {
    modalContainer.style.display = "none";
    unlockBodyScroll();
    modalContainer.innerHTML = "";
    activeModalCloser = null;
  }

  document.getElementById("resurrect-close-btn")?.addEventListener("click", closeModal);
  document.getElementById("resurrect-cancel-btn")?.addEventListener("click", closeModal);
  document.getElementById("resurrect-modal-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "resurrect-modal-backdrop") closeModal();
  });
  activeModalCloser = closeModal;

  try {
    const archivedProjects = await api.getArchivedProjects();
    const container = document.getElementById("archived-projects-container");
    const searchInput = document.getElementById("resurrect-search-input");

    function renderList() {
      if (!container) return;
      const query = (searchInput?.value || "").toLowerCase().trim();
      const filtered = archivedProjects.filter(p => {
        if (!query) return true;
        return (p.name && p.name.toLowerCase().includes(query)) ||
               (p.client && p.client.toLowerCase().includes(query)) ||
               (p.type && p.type.toLowerCase().includes(query));
      });

      if (filtered.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <h3 style="margin-bottom: 0.35rem; color: var(--text-primary); font-size: 1rem;">
              ${archivedProjects.length === 0 ? 'No Archived Projects' : 'No Matches Found'}
            </h3>
            <p style="font-size: 0.8rem;">${archivedProjects.length === 0 ? 'No projects currently in cold storage.' : `No projects matching "${query}"`}</p>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="archived-cards-list" style="display: flex; flex-direction: column; gap: 0.5rem;">
          ${filtered.map((p, index) => {
            const iconSvg = getCategoryIconSvg(p.type);
            return `
              <div class="archived-item-card" style="display: flex; align-items: center; justify-content: space-between; padding: 0.7rem 0.9rem; background: var(--badge-bg); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); gap: 1rem;">
                <div style="display: flex; align-items: center; gap: 0.65rem; min-width: 0;">
                  <div class="card-icon-tag" style="width: 28px; height: 28px; font-size: 13px; flex-shrink: 0;">${iconSvg}</div>
                  <div style="min-width: 0;">
                    <h4 style="margin: 0; font-size: 0.875rem; color: var(--text-primary); font-weight: 600;" class="text-ellipsis">${p.name}</h4>
                    <div style="font-size: 0.7rem; color: var(--text-muted); display: flex; gap: 0.65rem; margin-top: 0.15rem;" class="font-mono">
                      <span>${p.type}</span>
                      <span>Client: ${p.client && p.client !== 'None' ? p.client : 'Internal'}</span>
                      <span>${p.created || ''}</span>
                    </div>
                  </div>
                </div>
                <button class="btn btn-primary restore-action-btn" data-index="${index}" data-name="${p.name || p.slug}" style="flex-shrink: 0; padding: 0.35rem 0.75rem; font-size: 0.785rem;">
                  ${icons.resurrect}
                  Restore
                </button>
              </div>
            `;
          }).join("")}
        </div>
      `;

      container.querySelectorAll(".restore-action-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const projName = btn.getAttribute("data-name");
          const projectPath = filtered[Number(btn.getAttribute("data-index"))].path;
          openConfirmModal({
            title: "Resurrect Project",
            message: `Restore '${projName}' back to active Projects workspace?`,
            subtext: "The project will be moved back into its designated category folder and re-indexed.",
            confirmText: "Restore Project",
            variant: "info",
            onConfirm: async () => {
              const res = await api.resurrectProject(projectPath);
              showToast(`Project restored: ${res.path}`, "success", 3000);
              closeModal();
              onResurrected(res);
            },
          });
        });
      });
    }

    searchInput?.addEventListener("input", renderList);
    renderList();

  } catch (err) {
    const container = document.getElementById("archived-projects-container");
    if (container) {
      container.innerHTML = `
        <div class="empty-state" style="border-color: var(--color-danger);">
          <h3 style="color: var(--color-danger); margin-bottom: 0.35rem; font-size: 1rem;">Cannot Access Archive</h3>
          <p style="font-size: 0.8rem;">${err.message}</p>
        </div>
      `;
    }
  }
}

/**
 * Real-time SSE Live Sync Modal & Console
 */
export function openLiveSyncModal(onComplete = () => {}) {
  const modalContainer = document.getElementById("modal-container");
  if (!modalContainer) return;

  modalContainer.innerHTML = `
    <div class="modal-backdrop" id="sync-modal-backdrop">
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true" aria-labelledby="sync-modal-title">
        <div class="modal-header">
          <div class="modal-title-group">
            <div class="modal-category-icon" style="color: var(--color-success); background: rgba(34, 197, 94, 0.1);">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
            </div>
            <div>
              <div class="modal-eyebrow">
                <span class="status-pill status-active" id="sync-modal-status-badge">
                  <span class="status-dot pulsing"></span>
                  STREAMING SYNC
                </span>
              </div>
              <h2 id="sync-modal-title" class="modal-title">Obsidian Brain Live Sync</h2>
            </div>
          </div>
          <button class="modal-close-btn" id="sync-modal-close-btn" aria-label="Close modal">
            ${icons.x}
          </button>
        </div>

        <div class="modal-body">
          <div class="sync-live-summary" style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; margin-bottom: 0.75rem;">
            <div class="modal-metric-card" style="padding: 0.65rem 0.85rem; background: var(--badge-bg); border-radius: var(--radius-md);">
              <span class="metric-label">Status</span>
              <span class="metric-val font-mono" id="sync-metric-status" style="font-size: 1rem; color: var(--color-accent-cyan);">Connecting</span>
            </div>
            <div class="modal-metric-card" style="padding: 0.65rem 0.85rem; background: var(--badge-bg); border-radius: var(--radius-md);">
              <span class="metric-label">Scanned</span>
              <span class="metric-val font-mono" id="sync-metric-projects" style="font-size: 1rem;">0</span>
            </div>
            <div class="modal-metric-card" style="padding: 0.65rem 0.85rem; background: var(--badge-bg); border-radius: var(--radius-md);">
              <span class="metric-label">Synced</span>
              <span class="metric-val font-mono" id="sync-metric-changes" style="font-size: 1rem; color: var(--color-success);">0</span>
            </div>
          </div>

          <div class="log-console" style="display: block; max-height: 240px; overflow-y: auto;">
            <div class="console-top-bar">
              <span class="console-title font-mono">Stream Log</span>
              <span id="sync-stream-status" class="console-time font-mono">Live</span>
            </div>
            <div id="sync-stream-log-body" class="console-body font-mono" style="font-size: 0.75rem;">
              <div class="log-entry"><span>Connecting to sync stream...</span></div>
            </div>
          </div>
        </div>

        <div class="modal-footer" style="display: flex; justify-content: flex-end;">
          <button class="btn btn-primary" id="sync-modal-done-btn" disabled>
            ${icons.check} Done
          </button>
        </div>
      </div>
    </div>
  `;

  modalContainer.style.display = "block";
  lockBodyScroll();

  let closeStream = null;

  function closeModal() {
    if (closeStream) closeStream();
    modalContainer.style.display = "none";
    unlockBodyScroll();
    modalContainer.innerHTML = "";
    activeModalCloser = null;
  }

  document.getElementById("sync-modal-close-btn")?.addEventListener("click", closeModal);
  document.getElementById("sync-modal-done-btn")?.addEventListener("click", closeModal);
  document.getElementById("sync-modal-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "sync-modal-backdrop") closeModal();
  });
  activeModalCloser = closeModal;

  const logBody = document.getElementById("sync-stream-log-body");
  const metricStatus = document.getElementById("sync-metric-status");
  const metricProjects = document.getElementById("sync-metric-projects");
  const metricChanges = document.getElementById("sync-metric-changes");
  const statusBadge = document.getElementById("sync-modal-status-badge");
  const doneBtn = document.getElementById("sync-modal-done-btn");

  let projectsCount = 0;
  let changesCount = 0;

  closeStream = api.streamSync(
    (event) => {
      if (!logBody) return;

      if (event.event === "start") {
        if (metricStatus) metricStatus.textContent = "Scanning";
        logBody.innerHTML += `<div class="log-entry log-info"><span>[Engine]</span> <span>${event.message}</span></div>`;
      } else if (event.event === "scanning_project") {
        projectsCount++;
        if (metricProjects) metricProjects.textContent = String(projectsCount);
        logBody.innerHTML += `<div class="log-entry font-mono" style="opacity: 0.7;"><span>[Scan]</span> <span>Checking project: ${event.project}</span></div>`;
      } else if (event.event === "file_sync") {
        changesCount++;
        if (metricChanges) metricChanges.textContent = String(changesCount);
        const typeClass = `log-${event.type || 'info'}`;
        logBody.innerHTML += `<div class="log-entry ${typeClass}"><span>[${event.project}]</span> <span>${(event.type || 'SYNC').toUpperCase()}: ${event.file} &rarr; ${event.msg}</span></div>`;
      } else if (event.event === "complete") {
        if (metricStatus) {
          metricStatus.textContent = "Synchronized";
          metricStatus.style.color = "var(--color-success)";
        }
        if (metricProjects) metricProjects.textContent = String(event.projects_synced || projectsCount);
        if (metricChanges) metricChanges.textContent = String(event.total_changes || changesCount);
        if (statusBadge) {
          statusBadge.innerHTML = `${icons.check} SYNC COMPLETE`;
          statusBadge.classList.add("status-active");
        }
        if (doneBtn) {
          doneBtn.disabled = false;
        }
        logBody.innerHTML += `<div class="log-entry log-push" style="margin-top: 0.5rem; font-weight: bold;"><span>✨ Sync complete. ${event.total_changes || 0} operations across ${event.projects_synced || 0} projects.</span></div>`;
        showToast("Obsidian Brain sync complete", "success");
        onComplete(event);
      }
      logBody.scrollTop = logBody.scrollHeight;
    },
    (err) => {
      if (metricStatus) {
        metricStatus.textContent = "Error";
        metricStatus.style.color = "var(--color-danger)";
      }
      if (doneBtn) doneBtn.disabled = false;
      if (logBody) {
        logBody.innerHTML += `<div class="log-entry log-error"><span>[Error] ${err.message || 'Stream disconnected'}</span></div>`;
      }
      showToast(`Sync error: ${err.message}`, "error");
    },
    (completeData) => {
      if (doneBtn) doneBtn.disabled = false;
    }
  );
}
