# Decisions: Testing

Read before writing or changing a test, the geometry baseline or the asset manifest.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

Cross-reference: "the two-severity entry above" in the geometry-baseline entry is
the config-drift check in [`build_and_deploy.md`](build_and_deploy.md).

---

## The asset manifest is re-stamped by hand, so a test asserts it actually was — 2026-08-17

`settings.STATIC_VERSION` is the cache-buster on every CSS/JS URL;
`scripts/asset_manifest.json` records the sha256 of everything under `_static/`
against the version current when the files last changed, and
`scripts/prelaunch_check.py` fails when the two disagree so a redeploy can never
serve changed assets from cache on an unbumped version. **Who bumps it and
when:** anyone who changes, adds, renames or removes a file under `_static/`
bumps `STATIC_VERSION` (settings.py) *and* re-records the manifest with
`python scripts/prelaunch_check.py --stamp-assets`. Those are two manual steps,
and the second is the one that gets forgotten.

It was. On 2026-08-15 the logo rename bumped the version 14 → 15 and left the
manifest at 14; nothing runs the pre-launch guard routinely, so the stale stamp
sat hidden for two days and was found by accident on 2026-08-17 — the exact
"a check that goes stale silently and is then discovered by accident" failure
this repo names in CLAUDE.md. A stale stamp is not cosmetic: it compares the
files against a hash that describes no real generation of them, silently
disabling the guard for the *next* change. The fix on 2026-08-17 was a
RE-STAMP, not a further bump: version 15 had never been recorded at all, so
re-stamping recorded the current files (the logo rename plus that day's tab-
monitor JS rename) against the version already bumped for them.

**Rejected:** auto-stamping from a git hook — hooks are not committed, so they
would not travel with a copied template, and there is no static build step to
hang the stamp on. Also rejected: hashing `_static/` in `settings.py`'s boot
banner — the pre-launch script's docstring already refuses this, because
hashing every file on every server start is a deploy-time cost charged to every
page render.
**Enforced:** `scripts/tests/asset_manifest_test.py` runs the guard's OWN
`asset_problems()` in the routine suite (one implementation of "is it fresh?",
called by both the launch gate and the test) and pairs it with a positive
control that the guard fires on each stale shape; the launch gate itself is
`scripts/prelaunch_check.py` (`asset_problems`, `--stamp-assets`); the "when"
is stated at `settings.STATIC_VERSION` and in the rebranding section of `.claude/reference/editing_a_study.md`.

---

## The layout geometry baseline is committed, so intentional change is reviewable — 2026-08-12

`scripts/tests/render_check.py` measures element geometry at three viewports;
`scripts/tests/geometry_baseline.json` is committed **on purpose** (to `scripts/tests/`, not
gitignored `_ai/`) so an intentional layout change shows up as a reviewable
diff of that file, and an unintentional one fails `--diff`. Layout failures
produce no error otherwise — nothing 500s while the participant gets a broken
page.
**Enforced:** `render_check.py --diff` exits non-zero on movement beyond ±3px;
adopting a change requires `--update-baseline` and reading the diff.

---

## A test that cannot fail is not evidence — standing principle

Bot tests passing is not evidence a browser works (three pilot outages went
green under bots); a content test loosened until it survives a content change
was never testing the content; a drift check that fails on everything gets
ignored and then catches nothing (see the two-severity entry above). Every
check must correspond to a participant it could save.
**Enforced:** as method, in `.claude/skills/writing-tests/SKILL.md` (real HTTP, no-JS
submits, phone User-Agents, visible-text assertions, measured rendering);
structurally, nowhere — this one is held by review and by the suites being the
shape they are.
