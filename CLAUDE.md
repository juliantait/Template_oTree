# oTree-Template — rules for agents working in this template

This template is copied to start new experiments, so a mistake here propagates to
every study built from it. `conventions.md` holds the design principles and the
README explains the parameter scheme; this file is the short list of rules you
must not break.

## The three orthogonal controls

Everything a participant experiences is determined by three **independent** axes,
declared at the top of `settings.py`:

1. **Study type** — `prolific` or `lab`. Recruitment plumbing only: ID capture and
   completion-code redirects and the integrity modules for Prolific; bank details
   and demographics for lab.
2. **Debug** — driven by the environment (`OTREE_PRODUCTION` unset means debug on),
   so production can never ship skip controls. It must be possible to debug a
   *Prolific-configured* study with all its modules on.
3. **Pilot feedback form** — its own flag, on for a pilot or friend test, off for
   the real run, independent of the other two.

A profile resolves into **explicit** config values at import, so the admin shows
exactly what a session ran with; a profile must never change behaviour silently at
runtime. Testing switches are a **reversible override layer** — turning testing off
must return every gate to the real study behaviour with nothing left changed.

## Correctness rules (each shipped a live bug in the pilot this template feeds)

- **Never `getattr(participant, 'field', default)`** — the vars descriptor raises
  `KeyError`, which the default does not catch. Use `participant.vars.get(...)`.
- **Never `session.config['name']`** — the config is frozen at session creation, so
  parameters added later are missing for running sessions. Use the safe accessor.
- **Never read a nullable model field bare** — use `field_maybe_none`.
- **Render telemetry as explicit hidden inputs** — oTree auto-renders any unplaced
  form field as a visible labelled box.
- **Escape participant- and URL-supplied values** — the templates do not
  auto-escape; this caused a reflected XSS.
- **Instrumentation must never break a page** — wrap all capture defensively.
- **`NUM_ROUNDS` is fixed at import.** A config may run fewer rounds, never more,
  and a rounds or page-sequence change must never be deployed over live sessions.

## Testing standard

Bot tests passing is not evidence that a browser works. Drive form pages **over
real HTTP**, including a submit with the JavaScript-filled hidden fields **empty**.
Before a launch, fuzz with a headless browser one worker per surface (entry,
instructions and quiz, task, monitor, endings) — that practice found an XSS and a
dropped participant label that server-side testing missed.

**Read `skills_claude/writing_tests.md` before writing or editing any test.** It
holds the method (the two drivers, the no-JS submit, phone User-Agents,
asserting on rendered visible text rather than raw HTML, escaping, frozen
configs, measured browser rendering checks); the README's Testing table says what
each kind of check is and is not evidence of.

**A layout or copy change needs a MEASURED render check**, not a look:
`tests/render_check.py` drives real headless Chromium at three viewports and
asserts on element geometry and rendered pixels. Layout failures produce no
error at all — nothing 500s and no test goes red while the participant gets a
broken page. Headless Chromium runs here without root; the recipe is
`_ai/headless_chromium_recipe.md`.

## Deploying

`scripts/predeploy_check.sh` boots a candidate build against a **copy of the live
database**, drives an existing mid-flow participant plus a fresh one plus a no-JS
submit, and fails on any 5xx. Run it before every deploy: a fresh install cannot
detect a broken upgrade path.

Run with no database argument (the template's own case — there is no live data
yet) it runs the fresh-install checks only and reports the upgrade path **NOT
TESTED**; that is never a pass for a study that has live sessions, and
`--require-db` turns it into a failure. It does not replace
`scripts/prelaunch_check.py`, which is the static config guard (placeholder
completion codes, DEBUG still on, testing loosenings) — run both.
