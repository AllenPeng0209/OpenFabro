# Mechanical source and model Undo/Redo

The editable CAD workflow needs real reversal of document changes. Selecting an older native model
only changes a personal view; it does not restore the active source or model pointer. Implement a
persistent project CAD journal for successful source and model mutations, independent of the electrical
design version. Each entry captures exact source bytes and the verified native asset identity on both
sides. Native assets remain immutable and are reused during restoration without rebuilding.

Record creation, parameter changes, saved CAD code and native rebuilds in their actual order. Restoring
a code-only edit or a model-only rebuild must preserve the intermediate stale-model state when that
was the original state. Undoing creation removes its editable source and active pointer but retains
all exported revisions. A new edit truncates the redo branch while preserving historical files.

Guard restoration with a monotonic journal revision, entry identity, expected current source and model
pointer, and trusted target-asset integrity. Reject peer/external changes and active builds. Apply source,
pointer and cursor together using the existing synchronous failure compensation. This is not a claim
of crash/powerloss or multiprocess durability.

Use Ctrl/Cmd-Z and redo from the active mechanical editor and saved CAD-file context; input/textarea
Undo remains native while typing. PCB and schematic Undo stay in their existing editor scope. Offer
explicit CAD Undo/Redo controls and a build-from-source action for unbuilt files. Keep source/model
selection coherent across Undo, Redo, reload and project changes. AI and manual CAD writes must leave
the journal consistent; whole mixed Agent batch reversal remains the separate file/design mechanism.

Phase51 scoped acceptance is test-results/cad-history-acceptance.json. Actual Agent and manual Main51
workflows, native asset reuse, input/editor scoping, mobile and full Undo-to-absence/Redo restoration
passed. The latest queued-intent editor generation is host-tested after the final AI review; that
review is preserved as historical evidence. Three reports were fully read and exact-proposal matched.

1018Python/oneexisting warning,272Node,585browser/86suites pass. Main87105/38973, assetse9c5c12ce184,
all51idle, saved electricalv1 unchanged/noNative, CADhistoryrevision24/cursor4/4entries/current8mm.
Old50savedspecs/versions and2139accepted hashes/nsmtimes remain exact. Frozen51retains2190files and
accepted nsmtimes, including all CAD/mechanical/source-snapshot groups. Current wheel matches
46assets/HTML/108Python using existing runtime dependencies. No clean-OS or physical acceptance.
Complete Flux remains the objective, self-hosted software first; watch deferred. Unrelated production,
branding and driving_into_world work remains unchanged.
