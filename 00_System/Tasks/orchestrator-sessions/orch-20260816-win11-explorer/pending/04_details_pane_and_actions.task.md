# Task 04: Right Details Inspector Pane & CreativeOS Action Deck

## 🔧 Agent Setup (DO THIS FIRST)

### Workflow to Follow
> Read `/mode-code` or `/vibe-build`. Use `view_file` on `C:\Users\johno\.gemini\config\global_workflows\mode-code.md`.

### Required Skills
> Look up each skill in your system prompt and `view_file` its SKILL.md:
>
> | Skill | Path | Why |
> |---|---|---|
> | frontend-design | `C:\Users\johno\.gemini\config\skills\frontend-design\SKILL.md` | Windows 11 Details Pane layout & typography |
> | ui-ux-pro-max | `C:\Users\johno\.gemini\config\skills\ui-ux-pro-max\SKILL.md` | Action hierarchy and modal feedback |

---

## Objective
Implement Zone 3 (Right Details & Action Deck Pane) that provides deep telemetry, specifications, and contextual studio operations for any selected item:
1. **Dynamic Hero Preview Box**: Large vector card or thumbnail corresponding to the selected folder, video, audio, or document file.
2. **CreativeOS 1-Click Action Deck**:
   * `[ 📤 Prep & Open Export Folder ]` — Calls `/api/projects/{name}/export-folder` to create `Video/`, `Thumbnail/`, `Audio/` and launch in Explorer.
   * `[ 🚗 Copy to Shuttle Drive ]` — Calls `/api/projects/{name}/travel`.
   * `[ ⚡ Reclaim Cache ]` — Opens existing SSE streaming cache reclaim modal (`reclaimModal.js`).
   * `[ 🎥 Create Proxies ]` — For raw media files.
   * `[ 📦 Move to Cold Archive ]` — Calls `/api/projects/{name}/archive`.
3. **Specifications & Metadata Table**: Total size, footage footprint, client name, category, and Obsidian Vault sync status.
4. **Collapsible Pane Control**: Toggle open/closed via the `🗂 Details` ribbon button or status bar icon.

---

## Scope & Files
* `00_System/GUI/src/js/components/modal.js`
* `00_System/GUI/src/js/components/reclaimModal.js`
* `00_System/GUI/src/js/views/explorerView.js` / Inspector module
* `00_System/GUI/src/css/main.css`

---

## Definition of Done
* [ ] Selecting any item in the canvas immediately updates the Details Pane with real metadata.
* [ ] All action buttons execute their respective API endpoints with toast / modal progress feedback.
* [ ] Details pane toggle expands/collapses the right column cleanly.
