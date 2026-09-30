import { api, formatBytes } from "../api.js";
import { openConfirmModal } from "./modal.js";
import { showToast } from "./toast.js";
import { beginWindowsCleanupJob, watchWindowsCleanupJob } from "./windowsCleanupJob.js";

const outdatedServerMessage = "CreativeOS is using an older background server. Restart that server, then reopen the app.";

const notes = {
  "user-temp": "Files in use are skipped.",
  "windows-temp": "Administrator access may be needed; locked files are skipped.",
  prefetch: "Windows rebuilds this cache. Clearing it can slow the next few launches.",
  directx: "Shaders rebuild on the next run.",
  "nvidia-dx": "Shaders rebuild on the next run.",
  "nvidia-gl": "Shaders rebuild on the next run.",
  "amd-dx": "Shaders rebuild on the next run.",
  updates: "Windows Update may lock downloads. This does not stop the service.",
};

export function renderWindowsCleanup(container, onUpdate = () => {}) {
  container.innerHTML = `
    <div class="windows-cleanup-heading">
      <div>
        <h2>Windows caches <span class="windows-cleanup-total font-mono">Not scanned</span></h2>
        <p class="windows-cleanup-status" role="status">Loading saved scan...</p>
      </div>
      <div class="windows-cleanup-actions">
        <button type="button" class="btn btn-danger" id="clear-windows-btn" hidden disabled>Clear selected</button>
        <button type="button" class="btn btn-secondary" id="scan-windows-btn">Rescan</button>
      </div>
    </div>
    <div class="windows-cleanup-list"></div>
    <details class="windows-cleanup-guidance">
      <summary>What gets cleared? What about Windows system cleanup?</summary>
      <p>Only the contents of selected folders are removed. Locked files and links are skipped. Sizes are estimates, not guaranteed space savings. Prefetch may slow app launches until rebuilt. Windows Update downloads may require admin access or a stopped update service. This app does not change services or hibernation settings.</p>
      <div class="windows-cleanup-tools">
        <button type="button" class="btn btn-secondary btn-sm" data-tool="disk-cleanup">Open Disk Cleanup</button>
        <button type="button" class="btn btn-secondary btn-sm" data-tool="storage-settings">Open Storage Settings</button>
      </div>
      <p>Use these Windows tools for Update Cleanup, old installations, Delivery Optimization, thumbnails, Recycle Bin and Storage Sense. Those items are not part of this folder scan.</p>
    </details>
  `;

  const scanButton = container.querySelector("#scan-windows-btn");
  const clearButton = container.querySelector("#clear-windows-btn");
  const status = container.querySelector(".windows-cleanup-status");
  const totalLabel = container.querySelector(".windows-cleanup-total");
  const list = container.querySelector(".windows-cleanup-list");
  let locations = [];
  let busy = false;
  let requested = false;
  let outdated = false;
  let needsRescan = false;
  let lastResults = new Map();
  const selected = new Set();

  function updateSelection() {
    const size = locations.filter(item => selected.has(item.id)).reduce((sum, item) => sum + (item.size_bytes || 0), 0);
    clearButton.disabled = busy || outdated || needsRescan || selected.size === 0;
    clearButton.textContent = selected.size ? `Clear selected (${formatBytes(size)})` : "Clear selected";
  }

  function renderRows(results = lastResults) {
    list.replaceChildren();
    for (const item of locations) {
      const row = document.createElement("div");
      row.className = "windows-cleanup-row";
      const selectable = !outdated && !needsRescan && (item.status === "available" || item.status === "partial") && item.size_bytes > 0;
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = selected.has(item.id);
      check.disabled = busy || !selectable;
      check.setAttribute("aria-label", `Select ${item.name}`);
      check.addEventListener("change", () => {
        if (check.checked) selected.add(item.id);
        else selected.delete(item.id);
        updateSelection();
      });

      const details = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.name;
      title.title = notes[item.id] || "";
      const path = document.createElement("span");
      path.className = "windows-cleanup-path";
      path.textContent = item.path;
      details.append(title, path);

      const size = document.createElement("div");
      size.className = "windows-cleanup-size font-mono";
      size.textContent = item.size_bytes === null ? "—" : `${item.status === "partial" ? "≥ " : ""}${formatBytes(item.size_bytes)}`;
      const caption = document.createElement("small");
      const result = results.get(item.id);
      caption.textContent = result
        ? `${formatBytes(result.removed_bytes)} removed${result.skipped ? ` · ${result.skipped} skipped` : ""}`
        : item.status === "available" ? `${item.file_count} files`
          : item.status === "partial" ? `${item.file_count}+ files · ${item.skipped} skipped`
            : item.status === "missing" ? "Not present" : "Cannot access";
      size.append(caption);

      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "btn btn-secondary btn-sm";
      clear.textContent = "Clear";
      clear.disabled = busy || !selectable;
      clear.setAttribute("aria-label", `Clear ${item.name}`);
      clear.title = notes[item.id] || "";
      clear.addEventListener("click", () => confirmClear([item.id]));
      row.append(check, details, size, clear);
      list.append(row);
    }
    clearButton.hidden = locations.length === 0;
    updateSelection();
  }

  function showSnapshot(data, results = new Map()) {
    if (!data || !container.isConnected) return;
    requested = true;
    locations = data.locations || [];
    needsRescan = false;
    lastResults = results;
    selected.clear();
    const measured = locations.reduce((sum, item) => sum + (item.size_bytes || 0), 0);
    const incomplete = locations.some(item => item.status === "partial" || item.status === "inaccessible");
    totalLabel.textContent = data.scanned_at ? `${incomplete ? "≥ " : ""}${formatBytes(measured)}` : "Not scanned";
    status.textContent = data.scanned_at
      ? `Updated ${new Date(data.scanned_at).toLocaleString()}`
      : data.supported ? "No saved scan yet." : "Only available on Windows.";
    renderRows(results);
    onUpdate(data);
  }

  async function scan() {
    if (busy) return;
    requested = true;
    busy = true;
    scanButton.disabled = true;
    scanButton.textContent = "Scanning...";
    status.textContent = "Measuring folders...";
    lastResults = new Map();
    renderRows();
    try {
      showSnapshot(await api.refreshWindowsCleanup());
    } catch (err) {
      outdated = err.message === "API route not found" || err.message === "Method Not Allowed";
      if (container.isConnected) status.textContent = outdated ? outdatedServerMessage : `Scan failed: ${err.message}`;
    } finally {
      busy = false;
      scanButton.disabled = outdated;
      scanButton.textContent = "Rescan";
      if (container.isConnected) renderRows();
    }
  }

  function onJobUpdate(job) {
    if (!container.isConnected) return;
    busy = job.status === "running";
    scanButton.disabled = busy || outdated;
    if (busy) {
      status.textContent = job.phase === "indexing"
        ? "Updating saved sizes..."
        : `${job.location} · ${job.processed_files.toLocaleString()} files checked`;
    } else if (job.status === "complete") {
      if (job.inventory) showSnapshot(job.inventory, new Map(job.results.map(item => [item.id, item])));
      else status.textContent = job.cache_error || "Cleanup finished. Rescan for current sizes.";
    } else if (job.status === "error") {
      needsRescan = true;
      status.textContent = job.message || "Cleanup stopped. Rescan before trying again.";
    }
    renderRows();
  }

  function confirmClear(ids) {
    const chosen = locations.filter(item => ids.includes(item.id));
    if (busy || needsRescan || chosen.length !== ids.length) return;
    const total = chosen.reduce((sum, item) => sum + (item.size_bytes || 0), 0);
    openConfirmModal({
      title: "Clear Windows caches?",
      message: `Remove the contents of ${chosen.length} selected ${chosen.length === 1 ? "folder" : "folders"}?`,
      subtext: `${formatBytes(total)} measured. This permanently deletes files; locked files and links will be skipped.`,
      confirmText: "Clear selected",
      variant: "danger",
      onConfirm: () => {
        busy = true;
        scanButton.disabled = true;
        status.textContent = "Starting cleanup...";
        renderRows();
        // Do not return this promise: the confirmation closes while the server
        // job continues and the floating progress control stays available.
        beginWindowsCleanupJob(ids).catch(err => {
          if (err.message === "Windows cleanup is already running") {
            watchWindowsCleanupJob(onJobUpdate);
            return;
          }
          if (container.isConnected) {
            busy = false;
            scanButton.disabled = outdated;
            status.textContent = `Could not start cleanup: ${err.message}`;
            renderRows();
          }
          showToast(`Could not start cleanup: ${err.message}`, "error");
        });
      },
    });
  }

  scanButton.addEventListener("click", scan);
  clearButton.addEventListener("click", () => confirmClear([...selected]));
  container.querySelectorAll("[data-tool]").forEach(button => {
    button.addEventListener("click", async () => {
      try {
        await api.openWindowsCleanupTool(button.dataset.tool);
      } catch (err) {
        showToast(`Could not open Windows tool: ${err.message}`, "error");
      }
    });
  });

  api.getHealth().then(health => {
    if (!container.isConnected || requested) return;
    if (!health.windows_cleanup_cached || !health.windows_cleanup_jobs) {
      outdated = true;
      scanButton.disabled = true;
      status.textContent = outdatedServerMessage;
      return;
    }
    watchWindowsCleanupJob(onJobUpdate);
    return api.getWindowsCleanup().then(data => {
      if (!container.isConnected || requested) return;
      if (data.scanned_at || !data.supported) showSnapshot(data);
      else scan();
    });
  }).catch(err => {
    if (container.isConnected) status.textContent = `Could not load saved scan: ${err.message}`;
  });

  return { showSnapshot };
}
