# Windows cleanup inventory

## Goal

Show measured Windows cache locations alongside project storage, keep the figures available between app launches, and let the user clear selected cache contents after confirmation. This is not a full-drive analyzer; scheduled scans never clear files.

## Components and data flow

- `cos.system_storage` scans eight fixed Windows cache locations without following symlinks or junctions. It saves snapshots atomically to `00_System/Config/windows_cleanup_index.json` and returns saved results without rescanning. Paths come from Windows environment variables, never from API input.
- The existing optional weekly `cos storage scan --quiet --background` task refreshes both the project storage index and the Windows snapshot. Manual project rescans refresh both too. No scheduled task deletes files.
- `/api/storage/windows-cleanup` reads the saved snapshot. `/refresh` scans and saves it. `POST /job` validates selected location IDs and starts one background cleanup at a time. `GET /job` returns file progress, bytes removed, and the result; after deletion the job refreshes the snapshot. The earlier synchronous `/clear` route remains for existing clients and rejects calls while a job is running. `/api/storage` includes the latest Windows snapshot with project figures.
- `windowsCleanup.js` displays cached figures when the Storage Inventory opens. It scans automatically only if no saved snapshot exists, and offers Rescan, individual Clear, and selected Clear actions. After confirmation the dialog closes; `windowsCleanupJob.js` polls the job and keeps a floating progress control visible across in-app navigation. `storageView.js` adds measured Windows caches as a separate segment in the allocation strip, with a lower-bound marker when the scan is incomplete. It never merges this figure into project reclaim estimates.

## Data storage

There is no database table or migration. `windows_cleanup_index.json` has `version`, `supported`, `scanned_at`, and `locations`. Each location records `id`, `name`, `path`, `status`, `size_bytes`, `file_count`, and `skipped`. The reader rejects outdated versions or snapshots whose paths differ from the current Windows environment. Missing scans return no locations, not zeros presented as a complete scan. File sizes are logical totals, not guaranteed disk savings. Job progress lives in server memory, so a server restart interrupts an active cleanup; rescan before trying again. Custom temp paths inside a project can overlap project measurements.
