# Parameter scheme

*Read this when you add or change a session-config parameter, a recruitment profile, or the screen lock.*

## Parameter scheme (read `docs/conventions.md` and `settings.py` first)
Three **independent axes** at the top of `settings.py` determine everything a
participant experiences:

1. **Study type** — `recruitment`: `prolific` | `lab`. The recruitment
   plumbing, decided once per study:
   - `prolific` — external-ID capture, completion-code redirects, tab monitor,
     comprehension disqualification, passive + device capture. Paid on-platform.
   - `lab` — no Prolific plumbing, no tab monitor; collects bank details and
     demographics; supervised one-time quiz re-read instead of disqualification.
2. **DEBUG** — from the environment (`OTREE_PRODUCTION` unset → DEBUG on).
   Drives every dev affordance: skip controls, quiz solutions in the browser,
   and the `quiz_verify=False` clickthrough loosening (honoured **only** under
   DEBUG). Orthogonal to study type: a prolific-configured session under DEBUG
   still runs all its integrity modules.
3. **Pilot feedback form** — `pilot_feedback`: shows a free-text feedback page
   at the end. On for pilots/friend tests, off for the real run, regardless of
   the other two axes.

Everything optional is one **feature flag** in `SESSION_CONFIG_DEFAULTS`, shipped
**OFF**. The study-type profile is a named bundle of flag values that is
**resolved into explicit config keys at import**, so the admin session-config
view shows exactly what a session will run with. An explicit per-config flag
always overrides the profile. (There is no `testing` study type — clickthrough
loosenings belong to the DEBUG axis; see the `test` session config for the
pattern.)

Modules (all off by default): `prolific_capture_participant_id`, `prolific_completion_redirects`,
`tab_monitor`, `quiz_comprehension_dq`, `quiz_reread`, `telemetry_passive_capture`,
`telemetry_device_capture`, `collect_outro_bank_details`,
`collect_outro_demographics`, `pilot_feedback`. The one deliberate exception to
off-by-default is **`explicit_consent`** (the consent page asks an explicit
"I consent / I do not consent" question, declining routed to exit code -1):
it ships **ON**, because asking is the safer ethical footing and a study must
opt out — the lab profile resolves it OFF (implicit consent by continuing,
with an experimenter in the room). It is an ethics decision with its own flag,
not Prolific plumbing — see .claude/DECISIONS.md (2026-08-14). Thresholds (`quiz_comprehension_max_failures`,
`tab_monitor_*`) and Prolific codes (`prolific_cc_code`, `prolific_noconsent_code`, `prolific_dq_code`)
are config values too. Each participant records a numeric
`exit_code` (see `docs/CODEBOOK.md`). `C.NUM_ROUNDS` is fixed at import — a config may
run fewer rounds, never more.

**`prolific_allowed_devices`** (the entry device allow-list) and **`prolific_screenout_return_url`**
(where a screened-out participant is sent, codeless) have their own reference
section — **[The device check](entry_and_identity.md#the-device-check-what-it-inspects-and-what-it-cannot)**
— because the name promises more certainty than any User-Agent check can
deliver. Read it before narrowing the list.

Every participant field, exit code, stage timestamp and future-proofing spare
column is documented in **`docs/CODEBOOK.md`** (including the repurpose convention for
spares: never rename in place).

### The screen lock (`screen_lock`, ON by default)

Participant pages feel like a screen, not a website: no selecting text outside
fields, no text cursor over text, no dragging images, no right-click menu.
Everything that should be clicked still can be, and fields work as normal. Set
`screen_lock=False` on a config, or untick it when creating a session, to turn it
off; the script is then not loaded and nothing is left changed.

- **Text a participant must copy gets the class `selectable`**, also for right-click
  and long-press. A forked study that shows a code, an email address or a link as
  text must add it (specimen in `_static/global/html/template.html`). The ways back
  to Prolific already carry it.
- **HTML5 drag and drop in a task needs the lock off** or a `selectable` wrapper: the
  lock stops `dragstart` everywhere else. Sliders and fields are not affected.
- **Fields:** Ctrl+V works; the right-click menu is gone there too on a computer, and
  a long-press on a phone stays, since a phone has no other way to paste.
- **Not reached:** the room's two pages before a session exists (the gate and oTree's
  wait page), oTree's "no more pages" page, and any page not including
  `css_bundle.html`. Admin pages are never locked. F12 can undo it.

Why, and what a session created before the key gets: `.claude/DECISIONS.md`, "The screen lock".
