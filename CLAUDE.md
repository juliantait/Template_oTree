# oTree-Template — rules for agents working in this template

This template is copied to start new experiments, so a mistake here propagates to
every study built from it. `conventions.md` holds the design principles and the
README explains the parameter scheme; this file is the short list of rules you
must not break.

**`DECISIONS.md` records why things are the way they are** — each decision with
its reasoning, the alternative that was rejected, and *where it is enforced* (or
an admission that nothing enforces it). **Read it before changing anything that
looks odd, and add to it when you make a decision someone could later mistake
for an accident.** Most of what looks like redundancy in this codebase is
load-bearing, and that file is where the evidence lives.

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

## The collapsed-distinction rule — where the bugs actually are

**When two genuinely different situations reach identical code and become
indistinguishable, that is where the bug lives.** Go looking for it deliberately:
it is the single most productive audit you can run on this codebase, and it does
not show up as a failing test, because both situations behave "correctly" for
whichever meaning the shared code picked.

The four worked examples below were all found on one day (2026-08-12), each by
comparing this template against an independent implementation of the same
feature. The examples are the point — the rule alone reads as a platitude.

- **`unknown` vs `undetermined` device.** A User-Agent that parsed and matched
  nothing is a device type a study may reject. No header, no request, an
  exception or garbage is *not a device type* and must always be allowed. Collapsed,
  a study rejecting `unknown` starts ejecting laptops behind a privacy proxy.
- **Allowed-on-entry vs allowed-to-clear.** Absence of evidence *allows on entry*
  but must never *clear* an existing screen-out, or anyone lifts their own
  screen-out by sending no User-Agent. The clear predicate is exactly the
  entry-allow predicate **minus undetermined**.
- **Cannot-import-yet vs symbol-drifted.** A guard installed before oTree's views
  are importable must fail quietly and retry; the same guard finding the symbol
  changed shape is version drift and must be loud. `except Exception` around both
  makes them identical, and turns a missing guard into something nobody can see.
- **Abandoned vs screened-out.** Exit code `0` means "never reached an ending";
  a screen-out has its own code. Collapsed, you cannot tell someone the gate
  turned away from someone who closed the tab during the task.

The tell is usually a single predicate, a shared `except`, or one value doing two
jobs. When you find one, keep them apart *and say why at the point of the split* —
the next reader will otherwise see redundancy and simplify it back.

### The same rule inverted — one concept, two implementations

**When one concept has two implementations, they will drift, and the drift will
be invisible until the environment changes.** Same defect class, mirrored: not
two situations reaching identical code, but one situation reaching two
implementations that disagree.

Worked example, found the same day. "Is this the same participant id?" was
answered twice: conflict detection compared labels in **Python**
(whitespace-collapsed, case-folded, `identity.rows_with_label`), while the entry
lookup used `pp_set.filter_by(label=…)`, i.e. **SQL**. So a participant
returning as `ABC123` whose row held `abc123` took a fresh row — and that same
spelling typed on the confirmation page was then refused as a conflict with the
row it had just failed to match. Worse, the SQL half is decided by the database
**collation**, so it behaved one way on the sqlite dev database and another on a
postgres deployment: green locally, broken only in production.

The fix is always the same — **one implementation, called by both** — and the
audit question is: *does any concept in this codebase get decided in two places,
and does one of them delegate to something the environment controls* (a
database, a locale, a browser, a clock)?

**The client-side variant, which fails silently and reads as success.** A path
check in JavaScript deciding *which pages are monitored* is a second source of
truth about a question the server already answers. When the two disagree, the
script simply declines to run: no error, no exception, no failing test — the
column fills with clean values for everybody and a dead feature looks like good
news. `exp_pilots` shipped exactly this (a hard `return` on any `/outro/` path
in `_static/global/js/ai_safety_monitor.js`), so its questionnaire pages could have been wired perfectly
server-side and still recorded nothing.

The general rule: **wiring can be verified, a silent refusal to run cannot** —
unless something asserts that observations actually *arrive*. Any client-side
instrumentation needs a test that a monitored page produces a record, not merely
that the page is configured to be monitored.

**A second instance, same shape, different mechanism: `form.submit()` does not
fire submit event listeners.** A page whose real work lives in an
`addEventListener('submit', …)` handler — `preventDefault`, a gate POST, a
reload carrying a flag — is bypassed entirely by `form.submit()`. The page
reloads without the flag, auto-submits again, and loops forever: no participant
row, no error, no failing test, and it happens **only to real arrivals** whose
URL carries an id. Use **`form.requestSubmit()`**, which fires the handler, and
pair any auto-submit with a loop guard that falls back to showing the button
when the gate POST fails or the reload comes back without its flag.

## Styling: shared components, never page-local patches

**Style with reusable components in `_static/global/css/`. A page template
composes existing classes; it does not carry its own tweaks.** No inline
`style=`, no one-off rule added to make a single page look right, no
page-specific override of a shared component.

This is the collapsed-distinction rule wearing a stylesheet. Every CSS bug in
this template came from the same shape:

- `.welcome-card` was referenced by three templates and **defined nowhere** — it
  came from a snapshot without its rule, so those pages simply had no centring.
- The instructions page carried **two widths for one concept** (a band *and* a
  reading measure), so the text, the eyebrow and the pager each landed on a
  different number and the pager could not be aligned.
- `logo_section.html` set `height` **inline**, which beats any stylesheet, so
  the component's own rule was inert until the attribute was removed.

**When a page needs something new:** add a component, give it an INTENTION
comment saying what it is for, and add a specimen to
`_static/global/html/template.html` so it is demonstrated rather than orphaned.
When two pages need the same thing, they use the **same class** — the same
component obeying different rules in different places is a defect even when each
instance looks reasonable on its own.

**Genuine exceptions exist** (a page-level rule that truly belongs to one
screen). Mark them `EXCEPTION` with the reason, so the next reader can tell a
deliberate departure from an accreted patch.

## Testing standard

Bot tests passing is not evidence that a browser works. Drive form pages **over
real HTTP**, including a submit with the JavaScript-filled hidden fields **empty**.
Before a launch, fuzz with a headless browser one worker per surface (entry,
instructions and quiz, task, monitor, endings) — that practice found an XSS and a
dropped participant label that server-side testing missed.

**Never assert an absence without asserting the matching presence.** A test that
only checks "this page does not contain X" passes against *any* page that
happens to be blank of X — including a page the participant never reached. Two
faults in the completion-code tests (2026-08-15) hid behind exactly this: the
walker was screened out at entry in one case and never left the consent page in
the other, so the page under test was the wrong page entirely, and all four
"does not carry another population's code" assertions passed happily. Only the
paired "carries its OWN code" assertion exposed it. An absence-only leak test is
indistinguishable from a test of nothing.

Two related traps, both of which produce false confidence rather than a false
alarm: a suite bound to a **fixed port** can silently test a stale server from
an earlier run (this happened, and reported a fixed defect as still present);
and a suite driven against an **externally started server** inherits that
server's mode, so a leak test pointed at a DEBUG server measures oTree's
`vars_for_template` debug panel rather than what a participant can see. Assert
what a real participant reaches — start the server in production mode.

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
`docs/headless_chromium_recipe.md`.

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
