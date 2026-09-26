# Task 06: Verification, End-to-End Build & Acceptance Audit

## 🔧 Agent Setup (DO THIS FIRST)

### Workflow to Follow
> Read `/mode-review` or `/review_code`. Use `view_file` on `C:\Users\johno\.gemini\config\global_workflows\review_code.md`.

### Required Skills
> Look up each skill in your system prompt and `view_file` its SKILL.md:
>
> | Skill | Path | Why |
> |---|---|---|
> | security-audit | `C:\Users\johno\.gemini\config\skills\security-audit\SKILL.md` | Audit code quality, security boundaries, and bundle integrity |

---

## Objective
Perform full build, automated verification, and quality audit across the updated CreativeOS application:
1. **Frontend Production Build**:
   * Run `npm run build` inside `00_System/GUI` and verify the `dist/` bundle compiles with zero syntax/module errors.
2. **Backend API Validation**:
   * Run pytest or endpoint smoke tests to confirm all new and existing routes (`/api/projects`, `/api/fs/list`, `/api/fs/transfer`, `/api/sync/stream`, `/api/storage/reclaim`) respond properly.
3. **Acceptance Criteria Verification**:
   * Confirm zero emojis in UI — only clean vector SVG glyphs.
   * Confirm multi-tab switching works without UI breakage.
   * Confirm Large Icons Grid View (Screenshot 1) and Details Table View (Screenshot 2) render flawlessly.
   * Confirm Dark Mode and Light Mode render with correct Fluent contrast tokens.
4. **Documentation & Handoff**:
   * Generate `Orchestrator_Summary.md` in `00_System/Tasks/orchestrator-sessions/orch-20260816-win11-explorer/`.

---

## Definition of Done
* [ ] `npm run build` succeeds cleanly.
* [ ] Server boots with zero traceback errors.
* [ ] All 4 views are functional, responsive, and free of visual artifacts.
* [ ] `Orchestrator_Summary.md` is created.
