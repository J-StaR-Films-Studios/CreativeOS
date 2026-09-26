/**
 * CreativeOS API Client with SWR Caching & Background Revalidation
 */

const API_BASE = "/api";
let activeRequestsCount = 0;

export function showTopLoader() {
  activeRequestsCount++;
  const bar = document.getElementById("top-progress-bar");
  if (bar) bar.style.display = "block";
}

export function hideTopLoader() {
  activeRequestsCount = Math.max(0, activeRequestsCount - 1);
  if (activeRequestsCount === 0) {
    const bar = document.getElementById("top-progress-bar");
    if (bar) {
      setTimeout(() => {
        if (activeRequestsCount === 0) bar.style.display = "none";
      }, 150);
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Client Local Storage Cache Layer
// ──────────────────────────────────────────────────────────────────────────────

export const cacheStore = {
  get: (key) => {
    try {
      const raw = localStorage.getItem(`cos_cache_${key}`);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  set: (key, data) => {
    try {
      localStorage.setItem(`cos_cache_${key}`, JSON.stringify(data));
    } catch {}
  },
  invalidate: (key) => {
    try {
      if (key) {
        localStorage.removeItem(`cos_cache_${key}`);
      } else {
        Object.keys(localStorage)
          .filter((k) => k.startsWith("cos_cache_"))
          .forEach((k) => localStorage.removeItem(k));
      }
    } catch {}
  },
};

async function request(endpoint, options = {}, trackProgress = true) {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (trackProgress) showTopLoader();

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const errorMsg = data.detail || data.message || `Request failed with status ${response.status}`;
      throw new Error(errorMsg);
    }

    return data;
  } catch (err) {
    console.error(`[API Error] ${endpoint}:`, err);
    throw err;
  } finally {
    if (trackProgress) hideTopLoader();
  }
}

/**
 * Stale-While-Revalidate (SWR) Fetch Pattern
 * Returns cached data immediately if present; revalidates in the background.
 */
export async function fetchSWR(cacheKey, fetcher, onUpdate = null) {
  const cached = cacheStore.get(cacheKey);

  // Background revalidation task
  const revalidate = async () => {
    try {
      showTopLoader();
      const fresh = await fetcher();
      const cachedStr = JSON.stringify(cached);
      const freshStr = JSON.stringify(fresh);
      cacheStore.set(cacheKey, fresh);

      if (onUpdate && (!cached || cachedStr !== freshStr)) {
        onUpdate(fresh);
      }
      return fresh;
    } catch (err) {
      console.warn(`[SWR Revalidation Failed] ${cacheKey}:`, err);
    } finally {
      hideTopLoader();
    }
  };

  if (cached !== null) {
    // Fire revalidation in the background without blocking UI
    setTimeout(revalidate, 10);
    return cached;
  }

  // Cold start: wait for network
  return await revalidate();
}

export const api = {
  // System Health & Config
  getHealth: () => request("/health", {}, false),
  getConfig: () => request("/config"),
  getCategories: () => request("/categories"),

  // SWR Cached Endpoints for Instant UI Rendering
  getProjectsSWR: (onUpdate) => fetchSWR("projects", () => request("/projects", {}, false), onUpdate),
  getCategoriesSWR: (onUpdate) => fetchSWR("categories", () => request("/categories", {}, false), onUpdate),
  getConfigSWR: (onUpdate) => fetchSWR("config", () => request("/config", {}, false), onUpdate),
  getStorageSWR: (onUpdate) => fetchSWR("storage", () => request("/storage", {}, false), onUpdate),

  // Projects CRUD & Actions (Mutations automatically invalidate local cache)
  getProjects: () => request("/projects"),
  createProject: async (payload) => {
    const res = await request("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },
  updateProject: async (name, payload) => {
    const res = await request(`/projects/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },
  travelProject: (name) => request(`/projects/${encodeURIComponent(name)}/travel`, {
    method: "POST",
  }),
  archiveProject: async (name) => {
    const res = await request(`/projects/${encodeURIComponent(name)}/archive`, {
      method: "POST",
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },
  getArchivedProjects: () => request("/projects/archived"),
  resurrectProject: async (name) => {
    const res = await request(`/projects/${encodeURIComponent(name)}/resurrect`, {
      method: "POST",
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },

  // File Explorer & Media Preview
  listFiles: (path = "") => request(`/fs/list${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  openPath: (path) => request("/fs/open", {
    method: "POST",
    body: JSON.stringify({ path }),
  }),
  openFile: (path) => request("/fs/open", {
    method: "POST",
    body: JSON.stringify({ path }),
  }),
  getRawFileUrl: (path) => `/api/fs/raw?path=${encodeURIComponent(path)}`,
  getFileContent: (path, maxBytes = 500000) => request(`/fs/content?path=${encodeURIComponent(path)}&max_bytes=${maxBytes}`),
  transferFiles: (payload) => request("/fs/transfer", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  deletePath: async (path, permanent = false) => {
    const res = await request("/fs/delete", {
      method: "POST",
      body: JSON.stringify({ path, permanent, recycle_bin: !permanent }),
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },
  cleanDownloads: (folder = null) => request("/system/clean-downloads", {
    method: "POST",
    body: JSON.stringify({ folder }),
  }),
  sortExportsInbox: (inbox_path = null) => request("/exports/sort-inbox", {
    method: "POST",
    body: JSON.stringify({ inbox_path }),
  }),
  cloneProject: async (payload) => {
    const res = await request("/projects/clone", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },
  initProject: async (payload) => {
    const res = await request("/projects/init", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    cacheStore.invalidate("projects");
    cacheStore.invalidate("storage");
    return res;
  },
  createExportFolder: (name) => request(`/projects/${encodeURIComponent(name)}/export-folder`, {
    method: "POST",
  }),

  // Storage & Reclaim
  getStorage: () => request("/storage"),
  refreshStorage: async () => {
    const res = await request("/storage/refresh", {
      method: "POST",
    });
    if (res && res.projects) {
      cacheStore.set("storage", res);
      cacheStore.set("projects", res.projects);
    }
    return res;
  },
  getProjectReclaimable: (project) => request(`/storage/reclaimable?project=${encodeURIComponent(project)}`),
  reclaimProject: async (project, targets = null) => {
    const res = await request("/storage/reclaim", {
      method: "POST",
      body: JSON.stringify({ project, targets }),
    });
    const cachedStorage = cacheStore.get("storage");
    if (cachedStorage && Array.isArray(cachedStorage.projects)) {
      const pMatch = cachedStorage.projects.find(p => p.name === res.project || p.slug === res.slug || p.path === res.path);
      if (pMatch) {
        pMatch.reclaimable_size = res.remaining_reclaimable || 0;
        pMatch.total_size = Math.max(0, (pMatch.total_size || 0) - (res.freed_bytes || 0));
        cachedStorage.total_size = Math.max(0, (cachedStorage.total_size || 0) - (res.freed_bytes || 0));
        cachedStorage.reclaimable_size = Math.max(0, (cachedStorage.reclaimable_size || 0) - (res.freed_bytes || 0));
        cacheStore.set("storage", cachedStorage);
      }
    }
    return res;
  },
  reclaimBulk: async ({ stale_only = false, days = 90, project_slugs = null } = {}) => {
    const res = await request("/storage/reclaim-bulk", {
      method: "POST",
      body: JSON.stringify({ stale_only, days, project_slugs }),
    });
    if (res && res.new_storage_summary) {
      const cachedStorage = cacheStore.get("storage");
      if (cachedStorage) {
        cachedStorage.total_size = res.new_storage_summary.total_size;
        cachedStorage.reclaimable_size = res.new_storage_summary.reclaimable_size;
        cachedStorage.media_size = res.new_storage_summary.media_size;
        cacheStore.set("storage", cachedStorage);
      }
    }
    return res;
  },

  // Note Sync
  triggerSync: () => request("/sync", {
    method: "POST",
  }),

  // Update Config Paths
  updatePaths: async (pathsMap, moveFiles = false) => {
    const res = await request("/config/paths", {
      method: "PUT",
      body: JSON.stringify({
        paths: pathsMap,
        move_files: moveFiles,
      }),
    });
    cacheStore.invalidate("config");
    return res;
  },

  // Drives & External Storage Mounts
  getDrives: () => request("/config/drives"),
  updateMounts: async (mounts) => {
    const res = await request("/config/mounts", {
      method: "PUT",
      body: JSON.stringify({ mounts }),
    });
    cacheStore.invalidate("config");
    return res;
  },

  // Category Configuration
  updateCategories: async (categories, defaultCategory = null) => {
    const res = await request("/categories", {
      method: "PUT",
      body: JSON.stringify({
        categories,
        default_category: defaultCategory,
      }),
    });
    cacheStore.invalidate("categories");
    return res;
  },

  /**
   * Real-time Server-Sent Events (SSE) Reclaim Stream
   */
  streamReclaim: ({ project = null, targets = null, slugs = null, stale_only = false, days = 90 } = {}, onEvent, onError, onComplete) => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    if (targets && Array.isArray(targets)) params.set("targets", targets.join(","));
    if (slugs && Array.isArray(slugs)) params.set("slugs", slugs.join(","));
    if (stale_only) params.set("stale_only", "true");
    if (days) params.set("days", String(days));

    const url = `${API_BASE}/storage/reclaim/stream?${params.toString()}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.event === "error") {
          eventSource.close();
          if (onError) onError(new Error(data.message || "Reclaim failed"));
        } else if (data.event === "complete") {
          eventSource.close();
          cacheStore.invalidate("storage");
          if (onComplete) onComplete(data);
        } else {
          if (onEvent) onEvent(data);
        }
      } catch (err) {
        console.error("[Reclaim SSE Parse Error]", err);
      }
    };

    eventSource.onerror = (err) => {
      eventSource.close();
      if (onError) onError(err);
    };

    return eventSource;
  },

  /**
   * Real-time Server-Sent Events (SSE) Sync Stream
   */
  streamSync: (onEvent, onError, onComplete) => {
    const url = `${API_BASE}/sync/stream`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (onEvent) onEvent(data);
        if (data.event === "complete" || data.event === "error") {
          eventSource.close();
          if (data.event === "complete") {
            cacheStore.invalidate("projects");
            if (onComplete) onComplete(data);
          }
          if (data.event === "error" && onError) onError(new Error(data.message || "Sync error"));
        }
      } catch (err) {
        console.error("Failed to parse SSE payload:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.warn("SSE stream encountered an error / connection closed:", err);
      eventSource.close();
      if (onError) onError(err);
    };

    return () => eventSource.close();
  },
};

/**
 * Format bytes to readable size
 */
export function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let val = bytes;
  let unitIndex = 0;
  while (val >= 1024 && unitIndex < units.length - 1) {
    val /= 1024;
    unitIndex++;
  }
  return `${val.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

