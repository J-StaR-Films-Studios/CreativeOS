# Task 05: Dual-Pane External RAID Bridge & Media Scrubber Station

## 🔧 Agent Setup (DO THIS FIRST)

### Workflow to Follow
> Read `/mode-code` or `/vibe-build`. Use `view_file` on `C:\Users\johno\.gemini\config\global_workflows\mode-code.md`.

### Required Skills
> Look up each skill in your system prompt and `view_file` its SKILL.md:
>
> | Skill | Path | Why |
> |---|---|---|
> | frontend-design | `C:\Users\johno\.gemini\config\skills\frontend-design\SKILL.md` | Media player and dual pane styling |
> | ui-ux-pro-max | `C:\Users\johno\.gemini\config\skills\ui-ux-pro-max\SKILL.md` | Audio waveform rendering and split navigation |

---

## Objective
Implement the 2 advanced workstation modes in the explorer:
1. **Dual-Pane External RAID Ingestion Bridge (View 3)**:
   * A split-screen layout dividing the center canvas into Left (Active Project Directory) and Right (Mounted External RAID / Camera Card / Sound Library).
   * Active pane focus indicator and 1-click **"📥 Ingest to Project"** button to copy selected files/folders without needing two separate OS windows.
2. **Media Scrubber & Waveform Audition Station (View 4)**:
   * Interactive video player with timeline scrubbing, timecode display, and resolution/codec badge for `.mp4`, `.mov`, `.mkv`, `.mxf` files using `/api/fs/raw`.
   * Live audio waveform visualizer for sound effects and music files with play/pause and **"Drop into Active Project Audio/"** action.

---

## Scope & Files
* `00_System/GUI/src/js/views/explorerView.js`
* `00_System/GUI/src/css/main.css` & `cards.css`

---

## Definition of Done
* [ ] Split-Pane mode allows side-by-side browsing of internal projects and external drives.
* [ ] Transfer button triggers `/api/fs/transfer` and refreshes the destination directory.
* [ ] Video and Audio files render live scrubbable players in the center canvas or right details pane.
