# Task 03: Tree Navigation Sidebar & Unified Dual-Mode Canvas

## 🔧 Agent Setup (DO THIS FIRST)

### Workflow to Follow
> Read `/mode-code` or `/vibe-build`. Use `view_file` on `C:\Users\johno\.gemini\config\global_workflows\mode-code.md`.

### Required Skills
> Look up each skill in your system prompt and `view_file` its SKILL.md:
>
> | Skill | Path | Why |
> |---|---|---|
> | frontend-design | `C:\Users\johno\.gemini\config\skills\frontend-design\SKILL.md` | Windows 11 Tree sidebar & file table styling |
> | ui-ux-pro-max | `C:\Users\johno\.gemini\config\skills\ui-ux-pro-max\SKILL.md` | High-density data presentation and responsive grid |

---

## Objective
Implement Zone 1 (Left Navigation Tree) and Zone 2 (Unified Center Canvas) to merge the capabilities of `dashboardView.js` and `explorerView.js`:
1. **Zone 1: Navigation Tree Sidebar**:
   * Pinned Workspaces: `Desktop`, `Downloads`, `01_Projects` (expandable with sub-categories `Video`, `Code`, `Clients`), `02_Exports`, `03_Vault`.
   * This PC / Mounted Drives: `(C:)`, `(D:) [Footage RAID]`, `(E:) [SFX Library]`, `(Z:) [NAS]`.
   * Real Windows 11 vector folder shapes and drive glyphs.
2. **Zone 2: Dual-Mode Canvas**:
   * **Mode A: Large Icons / Grid View (Screenshot 1)**: Authentic folder shapes with preview sheets, video clip cards with play overlays, code badges, filename labels, and selection boxes.
   * **Mode B: Details Table View (Screenshot 2)**: Full Windows Explorer data table with `Name`, `Date modified`, `Type`, `Size`, sortable headers, and keyboard navigation.
   * Instant switching between Mode A and Mode B via ribbon `⊞ View ▾` or status bar toggle.

---

## Scope & Files
* `00_System/GUI/src/js/views/explorerView.js` (refactored as the unified explorer engine)
* `00_System/GUI/src/js/components/projectCard.js`
* `00_System/GUI/src/css/cards.css` & `tables.css`

---

## Definition of Done
* [ ] Clicking sidebar items navigates to the target folder/drive.
* [ ] Both Grid View and Details Table View render live files and projects correctly.
* [ ] Keyboard navigation (`Arrow keys`, `Enter` to open, `Backspace` to go up) functions smoothly.
* [ ] Item selection updates the status bar and notifies the Right Details Pane.
