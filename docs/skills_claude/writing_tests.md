# Skill: writing tests for a study built from this template

Read this whole file before writing or editing tests. The deliverable is one or
more scripts in `scripts/tests/`, each runnable on its own (`python scripts/tests/<name>.py`) and
exiting non-zero on any failed check. Copy the shape of the files already there —
a `check(cond, msg)` that prints PASS/FAIL and collects failures, `section()`
headers, and a summary at the end. No pytest, no fixtures, no framework.

## Overriding principle

> **A TEST IS EVIDENCE ABOUT A PARTICIPANT'S EXPERIENCE, OR IT IS NOTHING.**

Every check must correspond to something that could actually happen to someone
in the study: a page they see, a submit they make, a value that reaches the
data. If you cannot say which participant a failing check saves, delete it.

## ⚠️ THE SINGLE MOST IMPORTANT RULE ⚠️

> **BOT TESTS PASSING IS NOT EVIDENCE THAT A BROWSER WORKS.**

`otree test` bots submit through the Python API. They never issue an HTTP POST,
never render a page, never leave a JavaScript-filled field empty, never carry a
User-Agent. Three live outages in the pilot this template came from went green
under bots:

- a participant field read with `getattr(participant, 'k', default)` — the vars
  descriptor raises `KeyError`, which the default does not catch, so every real
  consent submit 500'd while the bots' code path had the key already set;
- a nullable field read bare (`player.rt_ms`) — oTree raises `TypeError` on
  reading a null column, so every task submit 500'd for anyone with JS blocked,
  which is exactly the participant no friend-tester resembles;
- `session.config['new_param']` on a session created before that parameter
  existed — `KeyError`, mid-study, for the participants already in the database.

So: **drive the real thing.** Everything below is about how.

## The five kinds of check, and what each is evidence of

| Kind | Answers | Blind to |
|---|---|---|
| HTTP flow (`http_flow_test.py`, `gated_flow_test.py`) | can a participant get from entry to an ending in every config, without a 5xx? | anything about how the page LOOKS |
| Server-side gates (`device_gate_test.py`, `screenout_softwall_test.py`) | does a gate decided from the REQUEST fire correctly — and, as importantly, never fire on somebody it should not? | client-side behaviour |
| Identity/state over time (`identity_test.py`) | does a returning participant reach the SAME row, and does a duplicate id degrade instead of 500-ing? | anything about the pages themselves |
| Content (`example_quiz_content_test.py`) | does the page SAY what the design says it says? | everything not asserted |
| Rendering (`render_check.py`) | is it laid out, visible and clickable in a browser? | data correctness |
| Frozen/upgrade (`frozen_config_test.py`, `scripts/predeploy_check.sh`) | does an EXISTING participant survive this build? | fresh-install bugs |

Write the cheapest kind that can see your change. A wording edit needs a content
check; a CSS edit needs a render check; a new session-config parameter needs the
frozen-config list extended.

## Driving a form page over real HTTP

Two drivers, both already in `scripts/tests/`. Pick by what you need to reach.

**Against a server you started** — closest to production, exercises the real
ASGI stack end to end. Start it on a THROWAWAY database and point the test at it:

```bash
OTREE_ADMIN_PASSWORD=admin otree prodserver 8000
python scripts/tests/http_flow_test.py http://localhost:8000
```

Create sessions over the REST API (`POST /api/sessions` with
`session_config_name`, `num_participants`, and `modified_session_config_fields`
for per-scenario overrides), then walk with a `requests.Session`: GET the page,
parse its form with `FormParser`, build the payload with `build_payload`, POST
back to the same URL. oTree forms have **no `action` attribute** — they post to
the page's own URL — and the CSRF field is named `csrftoken`, not
`csrfmiddlewaretoken`.

**In-process** (`from otree_inprocess import boot`) — when you need what HTTP
cannot reach: the stored session config, the model rows behind a page, or the
DEBUG/production switch. `boot()` handles two traps you must not re-introduce:

- oTree opens the RELATIVE name `db.sqlite3` **in the current directory at
  import time** and ignores the path inside a sqlite `DATABASE_URL`. Setting the
  env var alone runs your test against the project's own database. `boot()`
  imports `otree.database` while chdir'd into a temp directory, then chdirs back
  because `_static/` and the template roots are equally CWD-relative.
- `settings.py` derives `DEBUG = 'OTREE_PRODUCTION' not in os.environ` —
  **presence, not value**, so `OTREE_PRODUCTION=''` means production here. Pass
  `boot(production=True/False)` and never set the variable by hand.

## The no-JS submit (the one bots can never do)

A page's JavaScript-filled hidden fields (`client_ms`, `is_mobile`,
`device_info_json`, anything you add) arrive **EMPTY** from a participant whose
JS is blocked, broken, or slow, and JS-*created* inputs do not arrive at all.
Post exactly that:

```python
overrides = {'is_mobile': '', 'device_info_json': '', 'client_ms': ''}
```

Then assert the walk still reaches an ending. Every new hidden field is a fresh
chance to reintroduce the `TypeError` above, so add it to the empty-post list in
`http_flow_test.py` **in the same change that adds the field**, and read it
server-side with `player.field_maybe_none('name')`.

## Simulating a phone

A gate decided from the entry REQUEST (this template's `allowed_devices`) can
only be exercised by sending a phone User-Agent — no bot has one, and the
client-side `is_mobile` field is measurement that blocks nobody:

```python
s = requests.Session()
s.headers['User-Agent'] = PHONE_UA        # see device_gate_test.py
```

Test the option **both ways round**: with the gate off, a phone must be entirely
unaffected; with it on, the phone must never render the consent page at all.

**Weight a gate's tests towards the FALSE POSITIVE.** The failure that costs you
real participants is the laptop that gets turned away, not the phone that slips
through, so most of `device_gate_test.py` is browsers that must NOT be screened:
desktop Chrome/Safari/Firefox/Edge, Chrome OS, a touchscreen laptop, an iPad, an
Android tablet, and every shape of unusable `User-Agent`. Two traps when you
send a malformed one:

- `requests` **refuses to send** a header value with leading whitespace or
  control characters — it validates client-side, and a broken browser does not.
  Patch it out (`requests.models.check_header_validity = lambda h: None`) or you
  are testing your HTTP client, not your gate.
- a control-character header never reaches application code anyway: **uvicorn
  rejects the request at the protocol layer** and closes the connection. There
  is no HTTP leg to write for that one, so assert it against the classifier
  directly and say in the test why (`device_gate_test.py` §A3b).

When a rule is ASYMMETRIC — this template's screen-out allows an unusable
header on entry but never lets one CLEAR an existing screen-out — write the two
assertions **next to each other**, so the asymmetry is visible to whoever reads
the file next (`screenout_softwall_test.py` §8).

## Assert against rendered VISIBLE TEXT, not raw HTML

Copy the `visible_text()` helper (`gated_flow_test.py`,
`example_quiz_content_test.py`): strip comments, `<script>`/`<style>` bodies and
tags, collapse whitespace, then assert. Both directions of the raw-HTML mistake
have already bitten this repo:

- **False failure.** Body copy WRAPS ACROSS SOURCE LINES, so a sentence that
  reads perfectly on screen is not a contiguous substring of the source. The
  assertion fails on a newline, not on the wording.
- **False pass.** A keyword can appear only in a SCRIPT or an HTML COMMENT —
  the entry page's capture script legitimately contains the literal
  `PROLIFIC_PID`, which is functional code, not prose. "The word Prolific is on
  the page" was true of the source and false of what anybody read.

Raw HTML is the right target for exactly two things: **structure** (`'name="age"'
in html`, a `checked` attribute, a class) and **escaping** (below).

## Escaping: assert on the raw HTML, and prove the value survives

oTree's ibis engine does **not** auto-escape `{{ }}`. Any participant- or
URL-supplied value hand-interpolated into a page is a reflected XSS until
proven otherwise; `{{ formfield }}` is safe, hand-built inputs are not. Pin it
(`xss_escaping_test.py`):

- render the page with a hostile value in the entry URL
  (`/join/<anon>?participant_label=…`, the parameter an attacker controls);
- assert the **raw payload appears nowhere** in the page, and that unambiguous
  injection markers (`<script>alert(1)`, `onmouseover="alert(2)"`) are absent —
  never generic fragments like `<script`, which occur on every normal page;
- assert the escaped form IS present in the attribute, and that the value
  **round-trips into the database un-truncated** — an unescaped quote silently
  truncates the value, so escaping is a data-fidelity fix as well as a security
  one;
- run it in **production mode**, or oTree's DEBUG var dump echoes the payload at
  the foot of every page and the whole-page scan means nothing.

## Driving a specific config, not the default

Never let a test walk "whatever the first config is". Name it, and override
parameters per scenario so the assertion is about the parameter and not about
today's defaults:

```python
requests.post(base + '/api/sessions', json={
    'session_config_name': 'prolific', 'num_participants': 2,
    'modified_session_config_fields': {'allowed_devices': ['computer']}})
```

The strongest form of this: create a SECOND session with deliberately different
values and require the page to follow them. A hard-coded "around 30 minutes"
passes a same-value check and fails this one.

## Reading state back

Three ways, in order of preference:

1. **REST API** — `POST /api/get_session/<code>` with
   `{'participant_vars': ['exit_code']}` reads participant fields back over
   HTTP with no database access (`device_gate_test.py`).
2. **In-process ORM** — `ot.participant_vars(code)`, or query the app's `Player`
   directly. Always read nullable columns with `field_maybe_none()`: a bare read
   of a null column raises `TypeError`.
3. **The wide CSV export** — `PARTICIPANT_FIELDS` appear ONLY in
   `all_apps_wide.csv`, flattened as `participant.<name>`; they are in no
   per-app export. Use it to prove a value actually reaches the analyst.

Assert on the **numeric exit code** (`settings.EXIT_CODES`) rather than on the
ending's wording wherever you can — the code is the contract, the wording is
copy.

## Frozen configs and the upgrade path

A session config is a SNAPSHOT taken at creation. A parameter added later does
not exist for a session already running, so `config['name']` raises `KeyError` —
a 500 for a participant mid-study. Read every parameter through
`common.cfg(config, name)`, which falls back to the value shipped in
`settings.SESSION_CONFIG_DEFAULTS` and raises a NAMED error for a key nobody
ever shipped. **Templates count too**: `{{ session.config.x }}` has exactly the
same failure and took every page of this template down when tested (fixed by
reading the build constant `{{ C.STATIC_VERSION }}` instead).

`frozen_config_test.py` simulates this by deleting keys from a created session's
stored config and walking it. **When you add a session-config parameter, add its
name to that test's `STRIPPED` list in the same change** — a parameter that is
never stripped is a parameter whose frozen behaviour is untested.

## Rendering checks (a real browser, measured — not eyeballed)

`scripts/tests/render_check.py` drives headless Chromium over a real server, writes
screenshots to `_ai/render_check/` and asserts on **measured element geometry**.
Reach for it whenever you touch CSS, a template's structure, or anything about
what is visible — none of it is reachable from an HTTP test, and all of it fails
silently: nothing 500s, no test goes red, the participant just gets a broken
page.

Setup on a box without root (full recipe, including the exact package list, in
`docs/headless_chromium_recipe.md` — it works, do not conclude otherwise):

```bash
pip install playwright pillow uvicorn requests && playwright install chromium
# unpack the nine library .debs into a private sysroot, then:
LD_LIBRARY_PATH=<sysroot>/usr/lib/x86_64-linux-gnu python scripts/tests/render_check.py
```

How to write one of these checks:

- **Measure, do not look.** `getBoundingClientRect()` + `getComputedStyle()`
  through `page.evaluate`, and assert on numbers you print in the message. "The
  card never touches the viewport edge" is `card.y - shell.y >= 1`, reported as
  a pixel count; a screenshot proves nothing about a value nobody measured.
- **Test at three viewports**, always including a short laptop (1280×720 — the
  most common participant screen, and the one where a wide-but-short layout goes
  wrong) and a phone.
- **Drive the state, then measure it.** Set `scrollTop` and assert it MOVED; a
  flex child without `min-height: 0` refuses to shrink and the region silently
  never scrolls while every CSS rule reads correctly. Press Tab to get a real
  `:focus-visible` ring — programmatic `.focus()` may not paint one.
- **Some things can only be measured off the PIXELS.** Decode the screenshot
  (Pillow) and compare strips: that is how "the content fades out where it is
  cut" and "the scroll shadow disappears at the end" are asserted here. Both
  were CSS-present and visually absent.
- **Playwright hides scrollbars by default** (`--hide-scrollbars` is a default
  headless arg). Launch with
  `pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])` or every
  screenshot loses the clearest scroll affordance there is.
- **Render in production mode**, so the DEBUG var dump and the testing-only skip
  buttons are absent and the screenshots show the participant's page.
- **`page.evaluate` still works with `java_script_enabled=False`**, so the
  no-JS rendering path can be driven and measured too. Do it: a page that works
  only with JS is a dead end for the participant it fails on.

## Study-specific content tests

`scripts/tests/example_quiz_content_test.py` is the model. Copy it, keep the shape —
structural invariants, then "does it reach the participant", then mechanics,
then "what must not be in production" — and rewrite the expectations for your
study. Do not keep the shipped one passing by loosening it: a content test that
survives a content change unchanged was never testing the content.

## Checklist before you finish

- [ ] Every new test runs standalone, prints PASS/FAIL per check, exits non-zero
      on failure, and says in its docstring how to run it.
- [ ] It drives real HTTP (or a real browser); no bot is treated as evidence.
- [ ] The throwaway-database rule holds: no test can touch a real database.
- [ ] Any JS-filled field you added is in the empty-post list, and read
      server-side with `field_maybe_none`.
- [ ] Copy assertions are made against `visible_text()`, structure/escaping
      assertions against raw HTML.
- [ ] The config under test is named explicitly, and a parameter's effect is
      proven by a second session with a different value.
- [ ] Any new session-config parameter is in `frozen_config_test.py`'s
      `STRIPPED` list.
- [ ] Anything you changed about layout or copy has a measured render check, and
      the screenshots in `_ai/render_check/` were regenerated.
- [ ] State is read back over the REST API or the ORM and asserted on exit codes,
      not on ending copy.
- [ ] You ran everything you shipped, and said plainly which checks you ran and
      which you could not.
