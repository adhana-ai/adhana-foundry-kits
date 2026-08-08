# Screenshots

Two real captures on disk, taken by `tools/shoot_ui.mjs` against `python -m src.app` running on
this machine — not mockups, not redrawn from `docs-redact-wireframe.html`.

- `redact-landing.png` — the app on load: `apartment-lease-notice-01` (a real shipped document)
  in the source panel, the 7-category legend built from `/api/categories`, no call made yet.
- `redact-nokey.png` — the same document after clicking "Detect & redact" with no `API_KEY`
  configured: the calm red note ("No API_KEY is configured, so nothing was called...") and the
  result panel staying empty rather than erroring. This is the pass's failure/limitation shot.

Both are free — neither drives `/api/redact` far enough to reach the provider. A third shot,
`redact-answered.png` (a real detected-and-redacted result, `--live`), is NOT here yet: capturing
it spends one real model call, and this pass's brief was explicit that no further spend should
happen after the three paid eval runs (r001/r002/r003) already on disk. Run
`node tools/shoot_ui.mjs --live` to add it once a future session is authorized to spend that call.

`docs-redact-wireframe.html` (outside this repo, built for stakeholder approval) shows the intended
composition and stays a mock, not a source of images.
