# Task 02: Windows 11 Chrome & Navigation Shell

## 🔧 Agent Setup (DO THIS FIRST)

### Workflow to Follow
> Read `/mode-code` or `/vibe-build`. Use `view_file` on `C:\Users\johno\.gemini\config\global_workflows\mode-code.md`.

### Required Skills
> Look up each skill in your system prompt and `view_file` its SKILL.md:
>
> | Skill | Path | Why |
> |---|---|---|
> | frontend-design | `C:\Users\johno\.gemini\config\skills\frontend-design\SKILL.md` | Authentic Fluent/Windows 11 desktop styling |
> | ui-ux-pro-max | `C:\Users\johno\.gemini\config\skills\ui-ux-pro-max\SKILL.md` | UI polish, typography, and crisp layouts |

---

## Objective
Replace the web-style top navigation bar in [`00_System/GUI/index.html`](file:///c:/CreativeOS/00_System/GUI/index.html) and [`00_System/GUI/src/css/main.css`](file:///c:/CreativeOS/00_System/GUI/src/css/main.css) with an authentic **Windows 11 File Explorer Chrome**:
1. **Windows 11 Tab Bar**: Multi-tab browsing (`01_Projects`, external drives, `+` new tab).
2. **Navigation & Breadcrumbs Row**: Back (`←`), Forward (`→`), Up (`↑`), Refresh (`⟳`), interactive breadcrumb segments with path navigation, and search box.
3. **Command Ribbon**:
   * Standard actions: `+ New ▾` (Blank Project, From Template, Clone Git Repo), Cut, Copy, Rename, Share, Delete, `⇅ Sort ▾`, `⊞ View ▾`.
   * CreativeOS macro extensions: `🧹 Clean Downloads` (with unfiled count badge), `📥 Sort Inbox`, `🧠 Sync Vault`, and `🗂 Details` pane toggle.
4. **3-Zone Layout Grid Skeleton**: Set up the 3-column CSS grid (`Zone 1: Sidebar` | `Zone 2: Canvas` | `Zone 3: Inspector`).
5. **Windows 11 Bottom Status Bar**: Item count, selection summary, and quick view toggles.

---

## Scope & Files
* `00_System/GUI/index.html`
* `00_System/GUI/src/css/main.css` & `tokens.css`
* `00_System/GUI/src/js/app.js` & `js/router.js`
* Reference: [`c:/CreativeOS/mockups/creativeos_3zone_mockups.html`](file:///c:/CreativeOS/mockups/creativeos_3zone_mockups.html)

---

## Definition of Done
* [ ] Zero emojis used — all icons are pure vector SVG glyphs matching Windows 11 Fluent Design.
* [ ] Tabs can be added, closed, and switched.
* [ ] Address bar reflects current directory and allows clicking breadcrumb parents.
* [ ] Command bar buttons trigger appropriate operations or modals.
* [ ] Status bar displays accurate live item count.
