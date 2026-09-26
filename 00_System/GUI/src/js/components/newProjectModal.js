/**
 * New Project & Repository Modal Dialog
 * Supports: Template Blueprint Scaffolding (/api/projects), Git Repo Cloning (/api/projects/clone),
 * and Existing Directory Adoption (/api/projects/init).
 */

import { api } from "../api.js";
import { getCategoryIconSvg, icons } from "../icons.js";
import { showToast } from "./toast.js";

let activeModalCloser = null;

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function closeNewProjectModal() {
  if (activeModalCloser) {
    activeModalCloser();
  }
}

export async function openNewProjectModal(onCreated = () => {}) {
  const modalContainer = document.getElementById("modal-container");
  if (!modalContainer) return;

  closeNewProjectModal();
  const previouslyFocused = document.activeElement;
  let activeTab = "scaffold"; // "scaffold" | "clone" | "adopt"
  let categoriesData = {};
  let defaultCategory = "Video";
  let simpleStructure = { "00_Notes": ["Notes.md", "Client_Links.md"] };

  try {
    const data = await api.getCategories();
    categoriesData = data.categories || {};
    defaultCategory = data.default_category || "Video";
    if (data.simple_structure) simpleStructure = data.simple_structure;
  } catch (err) {
    console.warn("Could not load categories in modal:", err);
  }
  const enabledCategories = Object.keys(categoriesData).length
    ? Object.entries(categoriesData).filter(([, cfg]) => cfg.enabled !== false)
    : [["Code", { description: "" }]];

  modalContainer.innerHTML = `
    <div class="modal-backdrop win11-modal-backdrop" id="new-project-modal-backdrop">
      <div class="modal-dialog win11-dialog" role="dialog" aria-modal="true" aria-labelledby="new-proj-title" style="max-width: 620px;">
        <!-- Fluent Header with Tabs -->
        <div class="win11-modal-header">
          <div class="win11-modal-title-group">
            <div class="win11-modal-icon">
              ${icons.plus}
            </div>
            <div>
              <span class="win11-modal-eyebrow font-mono">CREATIVEOS WORKSPACE</span>
              <h2 id="new-proj-title" class="win11-modal-title">Create / Import Project</h2>
            </div>
          </div>
          <button class="win11-modal-close" id="new-proj-close-btn" aria-label="Close modal">
            ${icons.x}
          </button>
        </div>

        <!-- Mode Switcher Tabs -->
        <div class="win11-modal-tabs">
          <button class="win11-modal-tab active" data-tab="scaffold" id="tab-btn-scaffold">
            ${icons.folder}
            <span>Blueprint Scaffold</span>
          </button>
          <button class="win11-modal-tab" data-tab="clone" id="tab-btn-clone">
            ${icons.git}
            <span>Clone Git Repo</span>
          </button>
          <button class="win11-modal-tab" data-tab="adopt" id="tab-btn-adopt">
            ${icons.externalLink}
            <span>Adopt Existing</span>
          </button>
        </div>

        <!-- Tab Body Container -->
        <div class="win11-modal-body" id="modal-tab-content">
          <!-- Dynamically populated -->
        </div>
      </div>
    </div>
  `;

  modalContainer.style.display = "block";
  document.body.style.overflow = "hidden";

  function closeModal() {
    modalContainer.removeEventListener("keydown", handleModalKeydown);
    modalContainer.style.display = "none";
    document.body.style.overflow = "";
    modalContainer.innerHTML = "";
    activeModalCloser = null;
    if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
      previouslyFocused.focus();
    }
  }

  function handleModalKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeModal();
      return;
    }
    if (e.key !== "Tab") return;

    const focusable = [...modalContainer.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )].filter(el => !el.hidden && el.offsetParent !== null);
    if (!focusable.length) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  activeModalCloser = closeModal;
  modalContainer.addEventListener("keydown", handleModalKeydown);

  document.getElementById("new-proj-close-btn")?.addEventListener("click", closeModal);
  document.getElementById("new-project-modal-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "new-project-modal-backdrop") closeModal();
  });

  // Tab switching
  const tabBtns = modalContainer.querySelectorAll(".win11-modal-tab");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.getAttribute("data-tab");
      renderTabBody();
      queueMicrotask(() => document.getElementById("modal-tab-content")?.querySelector("[autofocus], input, select, button")?.focus());
    });
  });

  function renderTabBody() {
    const bodyEl = document.getElementById("modal-tab-content");
    if (!bodyEl) return;

    if (activeTab === "scaffold") {
      bodyEl.innerHTML = `
        <form id="modal-scaffold-form" class="win11-modal-form">
          <div class="win11-form-row">
            <div class="win11-form-group flex-1">
              <label class="win11-label" for="m-proj-name">Project Title <span class="req">*</span></label>
              <input type="text" id="m-proj-name" class="win11-input" placeholder="e.g. Summer Promo, Brand Redesign" required autofocus />
              <span class="win11-form-hint" style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Special characters are automatically sanitized.</span>
            </div>
          </div>

          <div class="win11-form-row two-col">
            <div class="win11-form-group">
              <label class="win11-label" for="m-proj-category">Category Blueprint</label>
              <select id="m-proj-category" class="win11-select">
                ${enabledCategories.map(([k, cfg]) => `
                  <option value="${escapeHtml(k)}" ${k === defaultCategory ? 'selected' : ''}>${escapeHtml(k)} — ${escapeHtml(cfg.description || '')}</option>
                `).join("")}
              </select>
            </div>
            <div class="win11-form-group">
              <label class="win11-label" for="m-proj-client">Client (Optional)</label>
              <input type="text" id="m-proj-client" class="win11-input" placeholder="e.g. Nike, Internal" />
              <span class="win11-form-hint" style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Places inside <code>Clients/[Client]/</code></span>
            </div>
          </div>

          <div class="win11-form-row two-col">
            <div class="win11-form-group">
              <label class="win11-label" for="m-proj-date">Date Prefix (Optional)</label>
              <input type="date" id="m-proj-date" class="win11-input font-mono" />
            </div>
            <div class="win11-form-group">
              <label class="win11-label" for="m-proj-subfolder">Custom Subfolder Location</label>
              <input type="text" id="m-proj-subfolder" class="win11-input font-mono" placeholder="e.g. 2026/Campaigns" />
            </div>
          </div>

          <!-- Switches -->
          <div class="win11-switches-strip">
            <label class="win11-switch-label">
              <input type="checkbox" id="m-proj-git" />
              <span>Initialize Git repository</span>
            </label>
            <label class="win11-switch-label">
              <input type="checkbox" id="m-proj-simple" />
              <span>Minimal template (notes only)</span>
            </label>
          </div>

          <!-- Live Interactive Scaffold Tree Preview -->
          <div class="win11-scaffold-preview" style="margin-top: 0.5rem;">
            <div class="win11-preview-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <span class="font-mono" style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); letter-spacing: 0.05em;">SCAFFOLD DIRECTORY PREVIEW</span>
              <span class="win11-tree-tag" id="m-preview-cat-badge">Video</span>
            </div>
            <div class="font-mono" id="m-preview-path" style="font-size: 0.725rem; color: var(--color-primary); font-weight: 600; margin-bottom: 4px; word-break: break-all;">01_Projects/Video/...</div>
            <div class="win11-scaffold-tree-box" id="m-scaffold-tree-output"></div>
          </div>

          <div class="win11-modal-actions">
            <button type="button" class="btn btn-secondary" id="m-cancel-btn">Cancel</button>
            <button type="submit" class="btn btn-primary" id="m-submit-btn">
              ${icons.plus}
              Create Project
            </button>
          </div>
        </form>
      `;

      // Handlers for scaffold
      const nameInp = document.getElementById("m-proj-name");
      const catSel = document.getElementById("m-proj-category");
      const clientInp = document.getElementById("m-proj-client");
      const dateInp = document.getElementById("m-proj-date");
      const subInp = document.getElementById("m-proj-subfolder");
      const gitCb = document.getElementById("m-proj-git");
      const simpleCb = document.getElementById("m-proj-simple");
      const previewPathEl = document.getElementById("m-preview-path");
      const previewCatBadge = document.getElementById("m-preview-cat-badge");
      const treeOutput = document.getElementById("m-scaffold-tree-output");

      function updatePreview() {
        const rawName = (nameInp?.value || "").trim() || "My_New_Project";
        const cleanName = rawName.replace(/[^a-zA-Z0-9_\-\s]/g, "").replace(/\s+/g, "_");

        let datePrefix;
        if (dateInp?.value) {
          datePrefix = dateInp.value;
        } else {
          const now = new Date();
          datePrefix = now.toISOString().substring(0, 10);
        }

        const slug = `${datePrefix}_${cleanName}`;
        const selectedCat = catSel?.value || defaultCategory;
        const catConfig = categoriesData[selectedCat] || {};
        const client = (clientInp?.value || "").trim();
        const sub = (subInp?.value || "").trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
        const isSimple = simpleCb?.checked || false;

        let baseRel = client ? `Clients/${client.replace(/[^a-zA-Z0-9_\-\s]/g, "").replace(/\s+/g, "_")}` : (catConfig.physical_folder || selectedCat);
        if (sub) baseRel += `/${sub}`;
        const fullTarget = `01_Projects/${baseRel}/${slug}`;

        if (previewPathEl) previewPathEl.textContent = fullTarget;
        if (previewCatBadge) previewCatBadge.textContent = isSimple ? `${selectedCat} (Minimal)` : selectedCat;

        // Build structure tree
        let struct = {};
        if (isSimple) {
          struct = simpleStructure;
        } else if (catConfig.template_structure && Object.keys(catConfig.template_structure).length > 0) {
          struct = catConfig.template_structure;
        } else {
          const list = catConfig.folder_structure || ["00_Notes", "01_Footage", "02_Audio", "03_Exports"];
          list.forEach(f => { struct[f] = []; });
        }

        if (treeOutput) {
          const folders = Object.keys(struct);
          let treeHtml = `
            <div class="win11-tree-root">
              <span>${icons.folder}</span>
              <span><strong>${escapeHtml(slug)}</strong></span>
            </div>
          `;

          folders.forEach((folder) => {
            const files = struct[folder] || [];
            const isNotes = folder === "00_Notes";
            treeHtml += `
              <div class="win11-tree-node">
                <span style="color: var(--text-muted);">├─</span>
                <span style="color: var(--color-primary);">${icons.folder}</span>
                <span style="font-weight: 600;">${escapeHtml(folder)}/</span>
                ${isNotes ? '<span class="win11-tree-tag">Obsidian Brain</span>' : ''}
              </div>
            `;
            if (Array.isArray(files) && files.length > 0) {
              files.forEach((file) => {
                treeHtml += `
                  <div class="win11-tree-file">
                    <span style="color: var(--text-muted);">│  ├─</span>
                    <span>${icons.file}</span>
                    <span>${escapeHtml(file)}</span>
                  </div>
                `;
              });
            }
          });

          treeOutput.innerHTML = treeHtml;
        }
      }

      nameInp?.addEventListener("input", updatePreview);
      catSel?.addEventListener("change", updatePreview);
      clientInp?.addEventListener("input", updatePreview);
      dateInp?.addEventListener("change", updatePreview);
      subInp?.addEventListener("input", updatePreview);
      gitCb?.addEventListener("change", updatePreview);
      simpleCb?.addEventListener("change", updatePreview);
      updatePreview();

      document.getElementById("m-cancel-btn")?.addEventListener("click", closeModal);

      document.getElementById("modal-scaffold-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submitBtn = document.getElementById("m-submit-btn");
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Creating...`;
        }

        try {
          const payload = {
            name: nameInp.value.trim(),
            category: catSel.value,
            client: clientInp.value.trim() || null,
            destination_subpath: subInp.value.trim() || null,
            date: dateInp.value || null,
            git: Boolean(gitCb?.checked),
            simple: Boolean(simpleCb?.checked),
          };

          const res = await api.createProject(payload);
          showToast(`Project '${res.project.name || payload.name}' created!`, "success");
          closeModal();
          onCreated(res.project);
        } catch (err) {
          showToast(`Creation failed: ${err.message}`, "error");
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `${icons.plus} Create Project`;
          }
        }
      });

    } else if (activeTab === "clone") {
      bodyEl.innerHTML = `
        <form id="modal-clone-form" class="win11-modal-form">
          <div class="win11-form-row">
            <div class="win11-form-group flex-1">
              <label class="win11-label" for="m-clone-url">Git Repository URL <span class="req">*</span></label>
              <input type="text" id="m-clone-url" class="win11-input font-mono" placeholder="https://github.com/user/repository.git" required autofocus />
              <span class="win11-form-hint">Supports HTTPS and SSH Git clone URLs.</span>
            </div>
          </div>

          <div class="win11-form-row two-col">
            <div class="win11-form-group">
              <label class="win11-label" for="m-clone-category">Category</label>
              <select id="m-clone-category" class="win11-select">
                ${enabledCategories.map(([k]) => `
                  <option value="${escapeHtml(k)}" ${k === "Code" ? 'selected' : ''}>${escapeHtml(k)}</option>
                `).join("")}
              </select>
            </div>
            <div class="win11-form-group">
              <label class="win11-label" for="m-clone-client">Client (Optional)</label>
              <input type="text" id="m-clone-client" class="win11-input" placeholder="e.g. Acme, Internal" />
            </div>
          </div>

          <div class="win11-form-row">
            <div class="win11-form-group flex-1">
              <label class="win11-label" for="m-clone-name">Folder Name Override (Optional)</label>
              <input type="text" id="m-clone-name" class="win11-input font-mono" placeholder="Leave empty to use repository name" />
            </div>
          </div>

          <div class="win11-info-banner">
            <div class="win11-banner-icon">${icons.info}</div>
            <div class="win11-banner-text">
              CreativeOS will clone the repository, index its workspace files, and scaffold <code>00_Notes/Idea.md</code> linked to Obsidian Brain.
            </div>
          </div>

          <div class="win11-modal-actions">
            <button type="button" class="btn btn-secondary" id="m-clone-cancel-btn">Cancel</button>
            <button type="submit" class="btn btn-primary" id="m-clone-submit-btn">
              ${icons.git}
              Clone &amp; Adopt
            </button>
          </div>
        </form>
      `;

      document.getElementById("m-clone-cancel-btn")?.addEventListener("click", closeModal);

      document.getElementById("modal-clone-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const urlInp = document.getElementById("m-clone-url");
        const catInp = document.getElementById("m-clone-category");
        const clientInp = document.getElementById("m-clone-client");
        const nameInp = document.getElementById("m-clone-name");
        const submitBtn = document.getElementById("m-clone-submit-btn");

        if (!urlInp?.value.trim()) return;

        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Cloning Repository...`;
        }

        try {
          const payload = {
            url: urlInp.value.trim(),
            category: catInp.value,
            client: clientInp.value.trim() || null,
            name: nameInp.value.trim() || null,
          };

          const res = await api.cloneProject(payload);
          showToast(`Cloned repo to '${res.project.name || res.project.slug}'!`, "success");
          closeModal();
          onCreated(res.project);
        } catch (err) {
          showToast(`Clone failed: ${err.message}`, "error");
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `${icons.git} Clone &amp; Adopt`;
          }
        }
      });

    } else if (activeTab === "adopt") {
      bodyEl.innerHTML = `
        <form id="modal-adopt-form" class="win11-modal-form">
          <div class="win11-form-row">
            <div class="win11-form-group flex-1">
              <label class="win11-label" for="m-adopt-path">Existing Folder Path <span class="req">*</span></label>
              <input type="text" id="m-adopt-path" class="win11-input font-mono" placeholder="C:\\Projects\\MyExistingFolder or 01_Projects\\Video\\..." required autofocus />
              <span class="win11-form-hint">Choose a folder inside your configured Projects directory.</span>
            </div>
          </div>

          <div class="win11-form-row two-col">
            <div class="win11-form-group">
              <label class="win11-label" for="m-adopt-category">Category</label>
              <select id="m-adopt-category" class="win11-select">
                ${enabledCategories.map(([k]) => `
                  <option value="${escapeHtml(k)}" ${k === defaultCategory ? 'selected' : ''}>${escapeHtml(k)}</option>
                `).join("")}
              </select>
            </div>
            <div class="win11-form-group">
              <label class="win11-label" for="m-adopt-client">Client (Optional)</label>
              <input type="text" id="m-adopt-client" class="win11-input" placeholder="e.g. Acme, Internal" />
            </div>
          </div>

          <div class="win11-form-row">
            <div class="win11-form-group flex-1">
              <label class="win11-label" for="m-adopt-name">Project Title Override (Optional)</label>
              <input type="text" id="m-adopt-name" class="win11-input" placeholder="Defaults to folder name" />
            </div>
          </div>

          <div class="win11-modal-actions">
            <button type="button" class="btn btn-secondary" id="m-adopt-cancel-btn">Cancel</button>
            <button type="submit" class="btn btn-primary" id="m-adopt-submit-btn">
              ${icons.check}
              Adopt as Project
            </button>
          </div>
        </form>
      `;

      document.getElementById("m-adopt-cancel-btn")?.addEventListener("click", closeModal);

      document.getElementById("modal-adopt-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const pathInp = document.getElementById("m-adopt-path");
        const catInp = document.getElementById("m-adopt-category");
        const clientInp = document.getElementById("m-adopt-client");
        const nameInp = document.getElementById("m-adopt-name");
        const submitBtn = document.getElementById("m-adopt-submit-btn");

        if (!pathInp?.value.trim()) return;

        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span> Adopting...`;
        }

        try {
          const payload = {
            path: pathInp.value.trim(),
            category: catInp.value,
            client: clientInp.value.trim() || null,
            name: nameInp.value.trim() || null,
          };

          const res = await api.initProject(payload);
          showToast(`Project '${res.project.name}' adopted!`, "success");
          closeModal();
          onCreated(res.project);
        } catch (err) {
          showToast(`Adoption failed: ${err.message}`, "error");
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `${icons.check} Adopt as Project`;
          }
        }
      });
    }
  }

  renderTabBody();
  queueMicrotask(() => modalContainer.querySelector("[autofocus], input, select, button")?.focus());
}
