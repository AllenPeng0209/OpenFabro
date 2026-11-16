# Recoverable file editor drafts

The Files editor previously kept unsaved text only in the open page. Refreshing, closing or
crashing the page could lose edits. A stale source draft could be blocked correctly by the
server while offering no useful way to combine it with a newer saved file.

Keep synchronous recovery snapshots in browser storage, scoped to the session identity and
project. Each page owns its own writer and record IDs. Store exact local text, base text, source
SHA or design version, timestamp and monotonic revision. Storage denial or quota exhaustion
keeps the tab buffer editable and visibly identifies the missing recovery copy. Never evict
another unsaved draft silently. Recovery is local to that browser and origin, not a server backup.

Opening a recovery copy reads the current saved file and builds a bounded, line-aware three-way
comparison. Independent edits combine; overlapping edits require explicit draft, saved or custom
resolution. Preserve CRLF, LF, CR and final-newline differences. Large edits use a coarser review
region without truncating any version. Custom resolution text is shown before applying.

Apply rereads both the journal revision and saved source. Any newer revision requires another
review. Applying creates an unsaved editor buffer; only Save writes the project. A missing file
requires explicit recovery confirmation and is represented as a virtual file until saved. Existing
server path, size, SHA, design-version, permission and CAD-history protections still apply.
The optional allow_missing text GET reports absence without creating a file or bypassing guards.

Foreign snapshots are retired with revision-specific tombstones. A tab never removes another
writer's key: a concurrent later edit must remain recoverable. Save completion clears only the
accepted revision; newer input is rebased to the accepted text/SHA/version and snapshotted again.
design.json recovery goes through the existing graphical-design synchronization, validation,
version and Undo path. CAD recovery remains an unsaved draft and blocks building until saved.

This is file-editor durability, not recovery of graphical edits, chat input, every CAD dialog or
unsent tool operations. Browser data clearing and a full disk can still remove or prevent local
recovery. No account credential or external AI call is needed for the recovery workflow.

Accepted in scope with `test-results/draft-acceptance.json`: 1121 Python (one existing socket-thread
warning), 303 Node and662 browser checks across104suites passed. Nine journal/merge/EOL tests and
13 draft browser checks cover reload, conflicts, stale review, pending/successive Save, quota after
an earlier durable copy, deleted files, design versions, actual tabs and UUID-helper absence.
Owner isolation is a Node check; project isolation and compact views have browser coverage. Main
GUI exercised document/CAD recovery and retained the original native model; exact final fault
injections ran in isolation. Installed source/static equality and native smoke passed with reused
dependencies/FreeCAD. Original61 specs/versions and3025 SHA/ns-mtimes are preserved.

Full Flux functional and pixel parity, graphical/chat/dialog and cross-device recovery, and a
clean-OS installation remain open.
