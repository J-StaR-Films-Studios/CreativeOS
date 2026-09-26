# Task 01: Backend API Bridges & Endpoint Extensions

## 🔧 Agent Setup (DO THIS FIRST)

### Workflow to Follow
> Read `/mode-code` or `/vibe-build`. Use `view_file` on `C:\Users\johno\.gemini\config\global_workflows\mode-code.md`.

### Required Skills
> Look up each skill in your system prompt and `view_file` its SKILL.md:
>
> | Skill | Path | Why |
> |---|---|---|
> | security-audit | `C:\Users\johno\.gemini\config\skills\security-audit\SKILL.md` | Ensure safe filesystem boundaries on Windows |

---

## Objective
Extend [`00_System/Scripts/cos/api.py`](file:///c:/CreativeOS/00_System/Scripts/cos/api.py) to support:
1. Dynamic external drive whitelisting (`external_mounts` in `config.json` or arbitrary configured drive letters `D:\`, `E:\`).
2. `@app.post("/api/projects/clone")` — Git repository clone and adoption (`cos clone` parity).
3. `@app.post("/api/projects/init")` — Unmanaged folder adoption (`cos init` parity).
4. `@app.post("/api/projects/{name}/export-folder")` — Automatic export subfolder scaffold and retrieval (`cos export` parity).
5. `@app.post("/api/system/clean-downloads")` — Downloads auto-sorter (`cos clean` parity).
6. `@app.post("/api/exports/sort-inbox")` — Export inbox sorter (`cos sort-exports` parity).
7. `@app.post("/api/fs/transfer")` — Safe cross-drive file/folder copy or ingest for dual-pane transfers.

---

## Scope & Implementation Details
* **File to modify**: `00_System/Scripts/cos/api.py` and helper utilities in `00_System/Scripts/cos/`.
* **Security**: Update `_get_allowed_roots()` to dynamically include configured external mounts from `config.json`.
* **Non-Destructive**: Preserve all existing endpoints (`/api/projects`, `/api/fs/list`, `/api/storage/reclaim`, `/api/sync/stream`).

---

## Definition of Done
* [ ] External paths (e.g. `D:\`, `E:\` if mounted) pass `_check_path_allowed()` safely.
* [ ] `POST /api/projects/clone` clones a git repo and returns project metadata.
* [ ] `POST /api/projects/init` scans and creates `.project_meta.json` + `00_Notes/Idea.md`.
* [ ] `POST /api/projects/{name}/export-folder` creates `Video/`, `Thumbnail/`, `Audio/` subfolders in `02_Exports`.
* [ ] `POST /api/system/clean-downloads` organizes loose files into extension subfolders.
* [ ] API passes Python syntax checks without regression.
