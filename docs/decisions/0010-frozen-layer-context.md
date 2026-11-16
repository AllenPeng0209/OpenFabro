# Frozen layer context for AI image review

The native-layer image test verified delivery of exact PNG bytes and an image-only nonce. The
assistant nevertheless called ordinary bottom copper pads technical openings when only F.Mask
was plotted. Pixel delivery and semantic interpretation are separate requirements.

The next phase should freeze a bounded, explicit display-state record at the same time as the
pixels, retain it with the immutable canvas reference, and include it with every provider input.
It should identify the focused layer, visible layers and copper features, personally hidden native
objects, the displayed PCB/input identity, and the plotted aperture layers' status and provenance.
An aperture still loading or deferred at capture must stay marked unknown in the historical frame.

The send path must reuse the frozen record rather than read live layer preferences. Reused capture
IDs must reject changed state even when PNG bytes match. Older references without this metadata
must remain readable and explicitly lack semantic layer evidence. The metadata describes a client
display snapshot; it does not replace native connectivity, ERC/DRC or manufacturing validation.

Meaningful checks should cover capture-versus-send changes, immutable retry identity, malformed and
oversized state, project/version/source mismatches, provider staging/history, and a real marked image
where visible copper pads coexist with a separately identified native mask layer. Acceptance requires
the actual in-app AI to distinguish those objects using the new frozen state. This document is a
plan for implementation, not a claim of completed visual acceptance.

Implementation now captures the record synchronously beside the copied Layout canvas and validates
project/version/native PCB/input identities, hidden native IDs and existing ready SVG exports. It
persists context hashes, rejects retry relabeling and carries the record through image history,
CLI staging and provider labels. Controlled browser cases prove late SVG completion does not change
the capture-time loading state. Two actual local-Codex trials read image-only6824/3716 and correctly
interpret distinct frozen F.Mask-ready and B.Cu/all-apertures-hidden frames, including two-image
history. Full Python837/Node169/browser424 plus4 post-compatibility context checks passed. The latter4
repeat existing checks and are not added to424. Two source reviews led to reproduced fixes for held
strokes/Enter, category focus, SVG timing, legacy count-field compatibility and filesystem races.
Actual offline CLI parsing verifies separated image flags/stdin. Receipt: test-results/canvas-context-acceptance.json.
These are bounded software/fixture results. General model reliability, large cache enumeration,
every provider/device, full Flux pixels and manufacturing remain unaccepted.
