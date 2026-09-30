import { api, formatBytes } from "../api.js";
import { showToast } from "./toast.js";

let activeJob = null;
let currentPanelUpdate = null;
let pollTimer = null;
let polling = false;
let pollFailures = 0;

function progressPercent(job) {
  if (job.status === "complete") return 100;
  if (job.phase === "indexing") return 95;
  if (job.estimated_files > 0) {
    return Math.min(95, Math.round((job.processed_files / job.estimated_files) * 100));
  }
  return job.total ? Math.min(95, Math.round(((job.current - 1) / job.total) * 100)) : 0;
}

function progressText(job) {
  if (job.status === "complete") return `${formatBytes(job.removed_bytes)} removed`;
  if (job.status === "error") return job.message || "Cleanup status unknown";
  if (job.phase === "indexing") return "Updating storage index...";
  return `${job.location} · ${job.processed_files.toLocaleString()} files checked`;
}

function updateDetails() {
  const dialog = document.getElementById("windows-cleanup-job-dialog");
  if (!dialog || !activeJob) return;
  dialog.querySelector(".windows-job-location").textContent = progressText(activeJob);
  dialog.querySelector(".windows-job-count").textContent = activeJob.estimated_files
    ? `${activeJob.processed_files.toLocaleString()} / ~${activeJob.estimated_files.toLocaleString()} files · folder ${activeJob.current}/${activeJob.total}`
    : `Folder ${activeJob.current}/${activeJob.total}`;
  dialog.querySelector(".windows-job-freed").textContent = `${formatBytes(activeJob.removed_bytes)} removed`;
  dialog.querySelector(".reclaim-pill-progress-fill").style.width = `${progressPercent(activeJob)}%`;
}

function openDetails() {
  if (document.getElementById("windows-cleanup-job-dialog")) return;
  const backdrop = document.createElement("div");
  backdrop.id = "windows-cleanup-job-dialog";
  backdrop.className = "modal-backdrop is-open";
  backdrop.innerHTML = `
    <div class="modal-dialog modal-dialog-sm" role="dialog" aria-modal="true" aria-labelledby="windows-job-title">
      <div class="modal-header"><h2 id="windows-job-title" class="modal-title">Windows cleanup</h2></div>
      <div class="modal-body windows-job-details">
        <strong class="windows-job-location"></strong>
        <div class="reclaim-pill-progress-bar"><div class="reclaim-pill-progress-fill"></div></div>
        <span class="windows-job-count font-mono"></span>
        <span class="windows-job-freed font-mono"></span>
      </div>
      <div class="modal-footer"><button type="button" class="btn btn-secondary">Minimize</button></div>
    </div>
  `;
  const close = () => backdrop.remove();
  backdrop.querySelector("button").addEventListener("click", close);
  backdrop.addEventListener("click", event => {
    if (event.target === backdrop) close();
  });
  document.body.append(backdrop);
  backdrop.querySelector("button").focus();
  updateDetails();
}

function updatePill() {
  let pill = document.getElementById("windows-cleanup-job-pill");
  if (!activeJob || activeJob.status === "idle") {
    pill?.remove();
    return;
  }
  if (!pill) {
    pill = document.createElement("button");
    pill.type = "button";
    pill.id = "windows-cleanup-job-pill";
    pill.className = "reclaim-floating-pill windows-cleanup-job-pill";
    pill.setAttribute("aria-label", "Open Windows cleanup progress");
    pill.innerHTML = `
      <span class="reclaim-pill-pulse"></span>
      <span class="windows-job-pill-copy"><strong></strong><small class="font-mono"></small></span>
      <span class="reclaim-pill-progress-bar"><span class="reclaim-pill-progress-fill"></span></span>
    `;
    pill.addEventListener("click", openDetails);
    document.body.append(pill);
  }
  pill.querySelector("strong").textContent = activeJob.status === "running"
    ? "Clearing Windows caches"
    : activeJob.status === "complete" ? "Windows cleanup finished" : "Windows cleanup interrupted";
  const percent = progressPercent(activeJob);
  pill.querySelector("small").textContent = activeJob.status === "running" && activeJob.estimated_files
    ? `~${percent}% · ${progressText(activeJob)}` : progressText(activeJob);
  pill.querySelector(".reclaim-pill-progress-fill").style.width = `${percent}%`;
  updateDetails();
}

function updateJob(job) {
  activeJob = job;
  updatePill();
  if (currentPanelUpdate) currentPanelUpdate(job);
}

function schedulePoll(delay = 700) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, delay);
}

function finishJob(job) {
  if (job.status === "complete") {
    const skipped = job.results?.reduce((sum, item) => sum + item.skipped, 0) || 0;
    showToast(`${formatBytes(job.removed_bytes)} removed${skipped ? `; ${skipped} skipped` : ""}.`, job.cache_error || skipped ? "info" : "success");
  } else {
    showToast(job.message || "Windows cleanup stopped. Rescan before trying again.", "error");
  }
  setTimeout(() => {
    if (activeJob?.id === job.id && activeJob.status !== "running") {
      document.getElementById("windows-cleanup-job-pill")?.remove();
    }
  }, 8000);
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    const job = await api.getWindowsCleanupJob();
    pollFailures = 0;
    if (activeJob?.id && job.id !== activeJob.id) {
      throw new Error("The server restarted during cleanup. Rescan before clearing more files.");
    }
    const wasRunning = activeJob?.status === "running";
    updateJob(job);
    if (job.status === "running") {
      schedulePoll();
    } else if (wasRunning) {
      finishJob(job);
    }
  } catch (err) {
    pollFailures++;
    if (pollFailures < 5 && !err.message.includes("server restarted")) {
      updateJob({ ...activeJob, location: "Waiting for the server..." });
      schedulePoll(2000);
    } else {
      const message = err.message.includes("server restarted")
        ? err.message : "Connection lost. Cleanup may still be running; return to Storage to check.";
      updateJob({ ...activeJob, status: "error", message });
      showToast(message, "error");
    }
  } finally {
    polling = false;
  }
}

export function watchWindowsCleanupJob(onUpdate) {
  currentPanelUpdate = onUpdate;
  if (activeJob?.status === "running") {
    onUpdate(activeJob);
    return;
  }
  api.getWindowsCleanupJob().then(job => {
    if (job.status === "running") {
      pollFailures = 0;
      updateJob(job);
      schedulePoll(0);
    }
  }).catch(err => showToast(`Could not check cleanup progress: ${err.message}`, "error"));
}

export async function beginWindowsCleanupJob(ids) {
  if (activeJob?.status === "running") return;
  const job = await api.startWindowsCleanupJob(ids);
  pollFailures = 0;
  updateJob(job);
  if (job.status === "running") schedulePoll(0);
  else finishJob(job);
}
