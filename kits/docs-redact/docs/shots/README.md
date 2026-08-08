# Screenshots — pending a real run

This kit has not been run yet. `docs-qa`'s and `docs-extract`'s `docs/shots/*.png` are real
captures taken from their own local UI, after a real (or stub) run produced something on screen to
photograph — they are not mockups. This directory intentionally ships no images for the same
reason: there is nothing genuine to capture until `python -m src.app` has actually been started
and driven through a no-key state, a stub or real detection, and the redacted/highlighted toggle.

What belongs here once that happens, matching the shape the sibling kits use (`kit-nokey.png`,
`kit-answered.png`, plus whatever states are worth a second image):

- `redact-nokey.png` — the app with no `API_KEY` configured, showing the calm "not set" state.
- `redact-detected.png` — a document after detection, redacted view, legend and stats visible.
- `redact-highlighted.png` — the same result toggled to the highlighted view.

`docs-redact-wireframe.html` (outside this repo, built for stakeholder approval) shows the intended
composition. It is a mock, not a source of images — the screenshots that eventually land here must
come from this kit's own running UI, not be redrawn from the wireframe.
