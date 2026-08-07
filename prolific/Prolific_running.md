# Running oTree-Template on Prolific — implementation guide

This document explains everything that must change to take the current
**oTree-Template** (configured for the CREED physical lab) and run it as an
**online study on Prolific**. It is written so a worker who can only see the
`oTree-Template` folder has all the detail they need — every reference code
snippet below is copied verbatim from a working production project
(`Perceived Value-for-Money (TI-Thesis)/paymentpressure`, abbreviated
**PP** below), which the worker cannot access directly.

There are two largely independent parts:

1. **Different finish screens** — routing participants to different endings
   (normal completion, no-consent / screen-out, inactivity / timeout,
   disqualification…) and returning them to Prolific with the correct
   completion code. This is the part that makes the study "Prolific-shaped."
2. **Tab-switching / AI-safety monitor** — detecting when a participant tabs
   away (e.g. to use an AI tool) and disqualifying them after repeated
   violations. This is currently only a *spec* in the template
   (`prolific/tab-switch monitor.txt`); nothing is wired in.

Part 2's disqualification path *ends* in a finish screen, so build Part 1
first.

---

## Current state of the template (what is lab-specific today)

Before changing anything, understand what is hard-wired for the lab:

- **`settings.py`**
  - `ROOMS` has one entry whose own comment says *"This room exists on the
    computers in the CREED large lab as a desktop shortcut."* Lab rooms
    identify participants by seat/computer, not by a URL token. Online you
    use a self-serve session-wide link instead.
  - `DEBUG = True`.
  - No Prolific completion codes anywhere.
- **`before/__init__.py`** — `startpage` is described as a *"wait screen
  before experimenter starts the experiment"*: an experimenter manually
  launches the session in the room. There is no self-serve online entry and
  no capture of an external participant ID.
- **`outro/__init__.py`** — collects **bank account / BIC / SEPA** details
  (`Demographics` page) to pay people by bank transfer. This is the lab
  payment model and is the *opposite* of Prolific, which pays through the
  platform. The bank/SEPA flow must be removed for Prolific.
- **`outro`** is a flat `page_sequence = [Demographics, Results]` with a
  single ending. There is no concept of multiple finish screens.
- The template's `intro` app is a 2-player game
  (`PLAYERS_PER_GROUP = 2`, `NUM_ROUNDS = 2`), so online you also need
  arrival-matching and dropout handling (see §1.6).

---

# PART 1 — Different finish screens

## 1.1 The core idea: Prolific completion URLs

A participant is returned to Prolific by sending their browser to a special
URL that contains a **completion code**:

```
https://app.prolific.co/submissions/complete?cc=<COMPLETION_CODE>
```

Each distinct outcome you want Prolific to record gets its **own code**,
which you create in the Prolific study UI:

- A **standard completion code** — participant finished normally → they get
  paid the base reward.
- One or more **"returned / screened-out" codes** — for people who don't
  consent, fail an attention/device check, time out, or are disqualified.
  On Prolific these are configured as completion codes with action
  "approve" or as screen-out codes depending on whether you still want to
  pay a partial reward.

The oTree side does **not** decide payment amounts on Prolific — it only
decides *which URL (which code)* the participant is sent to. Bonuses (e.g. a
partial drop-out bonus) are paid separately via Prolific's bonus mechanism
using the data you export from oTree.

## 1.2 Where the codes live: `settings.py` session config

In PP, every session config carries its codes as plain keys
(`paymentpressure/settings.py`):

```python
SESSION_CONFIGS = [
    dict(
        name='payment_pressure_NoCC',
        display_name="Payment Pressure - No CC",
        app_sequence=['phonecheck','intro','wage','pp','outro'],
        num_demo_participants=100,
        career_concern=0,
        cc_code="C15LWM8C",      # normal completion code
        error_code="CDOQXZ3R",   # screen-out / error code
    ),
    dict(
        name='payment_pressure_CC',
        ...
        cc_code="C15LWM8C",
        error_code="CDOQXZ3R",
    ),
]
```

> [!NOTE]
> Codes are per-session-config, **not** global. That way the same code-base
> can be pointed at different Prolific studies just by editing the config.
> You can add as many code keys as you have outcomes, e.g.
> `cc_code`, `error_code`, `noconsent_code`, `timeout_code`, `dq_code`.

**Template change:** add these keys to each entry in `SESSION_CONFIGS` (or to
`SESSION_CONFIG_DEFAULTS` if they're shared). The template currently has a
single `test` config — add the codes there and create one real config per
Prolific study.

## 1.3 The redirect mechanism: `js_vars` + a button

The completion URL is built **server-side** in the final page's `js_vars`,
then a button in the template sends the browser there. From PP
(`paymentpressure/outro/__init__.py`):

```python
class Results(Page):
    def js_vars(player):
        cc_code = player.session.config["cc_code"]
        link = "https://app.prolific.co/submissions/complete?cc=" + str(cc_code)
        return dict(
            completionlink=link
        )
    def vars_for_template(self):
        return dict(
            earned=cu(self.participant.earned)
        )
```

And the template (`paymentpressure/outro/Results.html`):

```html
You must click the button below to complete the study and return to prolific:
<br><br>
<button type="button" class="btn btn-primary btn-right btn-lg" onclick="completed()"> Back to Prolific </button>

<script>
    let completionlink = js_vars.completionlink;
    function completed() {
        console.log("clicking the button")
        window.location.href = completionlink;
    }
</script>
```

Key points:
- `js_vars` makes the link available to client JS as `js_vars.completionlink`.
- The participant must **click** the button (Prolific best practice — an
  automatic redirect can fire before oTree has committed the final data).
- To send someone to a *different* code, just build the link from a
  different config key (e.g. `player.session.config["error_code"]`). You can
  branch inside `js_vars`:

```python
def js_vars(player):
    cfg = player.session.config
    if player.participant.timedout == 3:
        code = cfg["error_code"]
    else:
        code = cfg["cc_code"]
    return dict(completionlink="https://app.prolific.co/submissions/complete?cc=" + str(code))
```

## 1.4 Capturing the Prolific ID and screening at entry

Online you must (a) record who the participant is on Prolific, and
(b) screen out unsuitable participants *before* they enter the study. PP does
this in a dedicated first app called **`phonecheck`**
(`paymentpressure/phonecheck/__init__.py`), which is the first entry in every
`app_sequence`:

```python
class Player(BasePlayer):
    is_mobile = models.BooleanField()
    consent = models.BooleanField()
    prolific_id = models.StringField(label='ProlificID:')

class Consent(Page):
    form_model = 'player'
    form_fields = ['consent', 'prolific_id', 'is_mobile']

    def error_message(player: Player, values):
        if values['is_mobile']:
            return ("Sorry, this experiment does not allow mobile browsers. "
                    "<a href='https://app.prolific.co/submissions/complete?cc=CDOQXZ3R'>"
                    "Return Submission & Back to Prolific </a>")

    def before_next_page(self, timeout_happened):
        import time
        self.participant.wait_page_arrival = time.time()
        self.participant.timedout = 0

page_sequence = [Consent]
```

What this does:
- **`prolific_id`** is a normal text field. In a real deployment you usually
  pre-fill it from the URL Prolific appends
  (`?participant_label=...` or a custom query param) rather than asking the
  participant to type it — but capturing it on the consent page works and is
  what PP ships.
- **`is_mobile`** is set by client-side JS (a small script detecting mobile
  user agents / screen size) into a hidden field; `error_message` blocks
  mobile users and shows them an inline link back to Prolific using the
  **error code**.
- **`consent`** is captured here. To send non-consenters to a finish screen
  rather than just blocking them, see §1.5 — you branch on consent and route
  them to a dedicated ending.
- `before_next_page` stamps `wait_page_arrival` (used by the timeout logic,
  §1.6) and initialises `timedout = 0`.

**Template change:** the template already has `before/welcome+consent.html`
and a `before` app. Convert it (or add a `phonecheck`-style first page) to:
capture `prolific_id`, run a mobile check, and record `consent`. Add
`prolific_id`, `is_mobile`, `consent` as Player fields and the timing
participant fields described next.

## 1.5 Routing: the state variable that decides the ending

The whole multi-finish system hinges on **one participant-level variable**
that records *why* the participant is finishing. In PP this is
`participant.timedout`, declared in `PARTICIPANT_FIELDS`
(`paymentpressure/settings.py`):

```python
PARTICIPANT_FIELDS = ['high_payment','choice','payoff_r1','payoff_r2',
    'payoff_selected','category','career_concern','remain','group','time',
    'wait_page_arrival','timedout', ... ,'earned']
```

`timedout` takes the values:

| value | meaning |
|-------|---------|
| `0` | normal — completed the experiment |
| `1` | dropped / timed out **after** round 1 (gets paid for round 1) |
| `3` | never paired in time — never started the experiment (show-up only) |

> Use whatever set of codes makes sense for your design — `0/1/3` is just
> PP's scheme. Add `2` for "no consent", `4` for "AI-safety disqualified",
> etc. The point is: a single participant field carries the reason, every
> finish screen reads it, and `js_vars` maps it to a Prolific code.

### How the ending text branches on it

`paymentpressure/outro/Results.html` shows different text per outcome:

```html
{{if player.paidfor == 3 }}
    {{if player.participant.timedout == 3 }}
        We could not pair you in time to start the experiment.
    {{else}}
        We could not pair you in time to complete the experiment.
        You therefore get a bonus of {{player.payoff}}.
    {{endif}}
{{else}}
    {{if player.participant.timedout == 1 }}
        As you didn't complete the second round, you are paid for round 1.
        In that round you earned {{player.payoff}}.
    {{ elif player.participant.timedout == 0 }}
        Round {{player.paidfor}} has been randomly selected for your reward.
        In that round you earned {{player.payoff}}.
    {{endif}}
{{endif}}
```

### How payment per outcome is computed

`paymentpressure/outro/__init__.py`, `Demographics.before_next_page` reads
`timedout` and sets the payoff accordingly:

```python
def before_next_page(self, timeout_happened):
    if self.participant.timedout == 1:          # dropped after round 1
        self.finished = 1
        if self.participant.payoff_r1 == 66:    # 66 = sentinel "no round 1"
            self.payoff = C.drop_bonus
            self.participant.earned = self.payoff + C.showup
            self.paidfor = 3
        else:
            self.payoff = self.participant.payoff_r1
            self.participant.earned = self.payoff + C.showup
            self.paidfor = 1
    elif self.participant.timedout == 3:        # never paired
        self.finished = 1
        self.payoff = 0
        self.paidfor = 3
        self.participant.earned = C.showup
    else:                                        # normal completion
        self.paidfor = random.choice([1, 2])
        if self.paidfor == 1:
            self.payoff = self.participant.payoff_r1
        elif self.paidfor == 2:
            self.payoff = self.participant.payoff_r2
        self.participant.earned = self.payoff + C.showup
        self.finished = 1
```

### Two ways to implement "different finish screens"

There are two complementary techniques; PP uses both.

**(A) One Results page, branch the *content* and the *code*.**
Simplest. A single final page; the `{{if}}` blocks above choose the text and
`js_vars` chooses the Prolific code. Good when all endings are structurally
the same "thank-you + return" page.

**(B) Separate pages with `is_displayed`, and skip the experiment with
`app_after_this_page`.** Use when an ending must appear *before* the rest of
the study (e.g. screen-out, no-consent, never-paired) so the participant
should not walk through the remaining apps at all.

PP routes never-paired / timed-out participants straight to the final app
from the matching wait page (`paymentpressure/pp/__init__.py`):

```python
class RoundStartWaitPage(WaitPage):
    group_by_arrival_time = True
    template_name = 'pp/mywaitpage_rematch.html'
    @staticmethod
    def is_displayed(self):
        return self.participant.remain == 0
    def app_after_this_page(player, upcoming_apps):
        if player.participant.timedout == 1:
            return upcoming_apps[-1]      # jump directly to the last app (outro)
```

`app_after_this_page` returning an app name **skips all apps in between** and
sends the participant straight there. `upcoming_apps[-1]` is the last app in
the sequence (the outro). Inside an app, `is_displayed` on individual pages
(returning `False`) hides pages that don't apply to that participant's
outcome.

### Putting it together — a finish-screen map

For the template, decide your outcomes and fill in a table like this, then
implement each row:

| Outcome | How it's detected | State set | Where routed | Prolific code | Ending shown |
|---------|-------------------|-----------|--------------|---------------|--------------|
| Normal completion | reaches end of `outro` | `timedout=0` | last page of outro | `cc_code` | "Thank you, you earned …" |
| No consent | `consent == False` on entry page | `timedout=2` (new) | `app_after_this_page` → outro, skip everything | `noconsent_code` (new) | "You chose not to take part." |
| Mobile / device fail | `is_mobile == True` | blocked in `error_message` | inline link, never enters | `error_code` | inline "return submission" link |
| Inactivity / never paired | wait-page timeout (§1.6) | `timedout=3` | `app_after_this_page` → outro | `error_code` | "We could not pair you in time." |
| Dropped mid-study | timeout after round 1 | `timedout=1` | `app_after_this_page` → outro | `cc_code` (partial bonus) | "Paid for round 1." |
| AI-safety disqualified | tab-switch monitor (Part 2) | `ai_safety_disqualified=True` | `is_displayed` chain → Disqualified page | `dq_code` (new) | "Your participation has ended." |

## 1.6 Inactivity / dropout handling (needed for matched games)

Because the template's game pairs two players, online you cannot assume both
arrive at once. PP handles this with arrival-time grouping plus a timeout
that converts a lone waiter into a single-player group and routes them to a
finish screen.

Timestamp on entry (already shown in §1.4): `before_next_page` sets
`self.participant.wait_page_arrival = time.time()`.

Timeout check (`paymentpressure/pp/__init__.py`):

```python
def waiting_too_long(player):
    participant = player.participant
    import time
    # assumes you set wait_page_arrival in PARTICIPANT_FIELDS.
    return time.time() - participant.wait_page_arrival > C.drop_timer * 60
```

Arrival-time grouping that makes a single-player group on timeout
(`paymentpressure` `wait` app):

```python
class Constants(BaseConstants):
    timeout = 1  # in minutes

def group_by_arrival_time_method(self, waiting_players):
    if len(waiting_players) >= 2:
        return waiting_players[:2]
    for player in waiting_players:
        if player.waiting_too_long():
            player.participant.vars["too_long"] = True
            return [player]          # single-player group → will be routed out
        else:
            player.participant.vars["too_long"] = False

class Player(BasePlayer):
    timeout = models.FloatField()
    time_hidden = models.FloatField()
    def waiting_too_long(self):
        import time
        timespent = time.time() - self.participant.vars["wait_page_arrival"]
        self.time_hidden = (100 * timespent) / (60 * Constants.timeout)
        return timespent > Constants.timeout * 60
```

The wait page tells the participant what will happen
(`paymentpressure/pp/__init__.py` `RoundStartWaitPage.body_text`):

> "Waiting to pair you with someone. If we do not find a match within 5
> minutes, you will automatically proceed to the final questionnaire. In this
> case, your bonus payment will be 1) £0.50 if you haven't played round 1, or
> 2) your round 1 payoff if you have played round 1. You can also manually
> refresh the page if nothing is happening."

**Template change:** add `wait_page_arrival`, `timedout` (and any timing
fields you need) to `PARTICIPANT_FIELDS`; add a `group_by_arrival_time`
wait page to the game app with the timeout logic above; set `timedout`
appropriately and use `app_after_this_page` to route timed-out participants
to the outro.

## 1.7 Production settings

PP runs in production mode (`paymentpressure/settings.py` /
`paymentpressure/Procfile`):

```python
DEBUG = False
```

```
# Procfile
web: otree prodserver1of2
worker: otree prodserver2of2
```

Postgres is configured via env vars (the template already has a Postgres
`DATABASES` block in `settings.py`). For Prolific you also:

- Set `DEBUG = False`.
- Replace lab `ROOMS` with a self-serve session-wide URL (create the session
  in the oTree admin and use the **session-wide link**, which lets each
  Prolific participant start themselves). You can keep a room if you prefer
  room-based links, but lab seat identification is not used online.
- Make sure `participant.label` / `prolific_id` is captured (§1.4) so you can
  match oTree data to Prolific submissions for approval and bonusing.

## 1.8 Part 1 checklist (what to change in the template)

- [ ] `settings.py`: add `cc_code` / `error_code` (and any extra outcome
      codes) to each session config; set `DEBUG = False`; switch from lab
      `ROOMS` to a session-wide link.
- [ ] `settings.py`: add `wait_page_arrival`, `timedout` (and timing fields)
      to `PARTICIPANT_FIELDS`.
- [ ] Entry app (`before` / new `phonecheck`): capture `prolific_id`, run a
      mobile check (`is_mobile` hidden field + JS), record `consent`,
      stamp `wait_page_arrival`, init `timedout = 0`. Block / route
      non-consenters and mobile users with the right code.
- [ ] Game app: add `group_by_arrival_time` wait page + timeout logic; set
      `timedout` and use `app_after_this_page` to skip to outro on dropout.
- [ ] `outro`: **remove** bank / BIC / SEPA fields and logic. Add a
      `Results`-style final page that (a) branches its text on `timedout`,
      and (b) builds `completionlink` in `js_vars` from the appropriate
      config code, with a "Back to Prolific" button.
- [ ] Implement each row of the finish-screen map (§1.5) as either branched
      content (technique A) or a dedicated `is_displayed` page (technique B).

---

# PART 2 — Tab-switching / AI-safety monitor

## 2.1 What it is and its current state

`prolific/tab-switch monitor.txt` is a **draft spec, not wired in**.
It is a `.txt` (not `.js`), nothing in the template references it, and the
server-side pieces it assumes **do not exist yet**:

- It says *"Keep these constants in sync with `intro/__init__.py`"* — those
  `AI_SAFETY` constants are **not** in `intro/__init__.py`.
- It calls an oTree `live_method` (`focus_live_method`) bound to every
  monitored page — that handler **does not exist**.
- It redirects disqualified participants to a **Disqualified** page in
  `outro` — that page **does not exist**.
- It reads/writes a participant field `ai_safety_disqualified` — **not
  declared**.

So Part 2 is: build the three missing server pieces, add a consent/arming
page, add the Disqualified finish screen (ties into Part 1), and include the
JS.

## 2.2 What it does (behaviour)

Goal: stop participants tabbing away (e.g. to an AI tool) on tasks meant to
measure their own ability. Two-strikes, server-authoritative.

- **Arming:** runs only after the participant agrees on an AI-safety page
  that sets `sessionStorage.aiSafetyAgreed = '1'`. Disabled on `/outro/`
  pages so people can tab away to copy their Prolific code without penalty.
- **Detection:** `window.blur`, `visibilitychange` (tab hidden), focus loss.
  In-page mouse clicks are filtered out to avoid false positives.
- **Grace + violation:** on leaving, a red full-screen overlay appears after
  `OVERLAY_DELAY_MS` (400 ms) with a 4 s countdown; if the participant does
  not return within `THRESHOLD_MS` (4 s) a violation is recorded.
- **Two strikes:** 1st violation → warning modal; on the
  `MAX_VIOLATIONS`-th (2nd) → disqualification.
- **Client is not trusted:** every violation is sent to the server via
  `liveSend({type:'focus_loss', event_id, ...})`. The server keeps the
  authoritative count (deduped by `event_id`) and sets
  `participant.ai_safety_disqualified`. On disqualification the server pushes
  `{action:'disqualified'}`, the page reloads, and every monitored page's
  `is_displayed` returns `False`, so the participant lands on the
  Disqualified page in outro.

All the client constants and the full client logic already exist in
`prolific/tab-switch monitor.txt` — read that file; it is the
implementation, not pseudo-code. The constants are:

```js
const AI_SAFETY = {
    MAX_VIOLATIONS: 2,        // disqualify on the 2nd recorded violation
    THRESHOLD_MS: 4000,       // continuous away-time before a violation
    OVERLAY_DELAY_MS: 400,    // grace before the red overlay appears
};
```

## 2.3 Client side — what to do with the JS

1. Rename `prolific/tab-switch monitor.txt` → e.g.
   `_static/global/js/ai_safety_monitor.js`.
2. Include it on every monitored page. The template's monitored pages render
   through `_static/global/html/template.html`, which already pulls in
   `global/js/global.js`:

   ```html
   <script src="{% static 'global/js/global.js' %}"></script>
   ```

   Add alongside it:

   ```html
   <script src="{% static 'global/js/ai_safety_monitor.js' %}"></script>
   ```

   (Or append the monitor's contents into `global.js`.) Note the monitor
   already self-guards: it only runs once `sessionStorage.aiSafetyAgreed`
   is set and never on `/outro/` pages, so including it globally is safe.
3. The JS expects oTree's live-page globals `liveSend` / `liveRecv` to be
   present — these exist automatically on any page that defines a
   `live_method` (see §2.5). The monitor sets `window.liveRecv` to handle the
   `{action:'disqualified'}` push.

## 2.4 The arming page (consent → set sessionStorage flag)

Add a page (e.g. in `intro`, before the monitored tasks) that explains the
AI-safety rule and, on agreement, sets the flag client-side:

```html
<script>
    document.querySelector('input[type="submit"]').addEventListener('click', function () {
        try { sessionStorage.setItem('aiSafetyAgreed', '1'); } catch (e) {}
    });
</script>
```

Without this flag set, the monitor stays dormant. Use it to mark exactly the
boundary where monitoring should begin.

## 2.5 Server side — the missing pieces to build

### (a) Participant field

In `settings.py`, add to `PARTICIPANT_FIELDS`:

```python
PARTICIPANT_FIELDS = [..., 'ai_safety_disqualified', 'focus_loss_count', 'focus_event_ids']
```

- `ai_safety_disqualified` (bool) — authoritative disqualification flag.
- `focus_loss_count` (int) — authoritative count.
- `focus_event_ids` (list) — seen `event_id`s for server-side dedup.

### (b) Constants — mirror the JS

In `intro/__init__.py` (the spec says to keep these in sync with the JS):

```python
class C(BaseConstants):
    ...
    AI_SAFETY_MAX_VIOLATIONS = 2
    AI_SAFETY_THRESHOLD_MS = 4000
    AI_SAFETY_OVERLAY_DELAY_MS = 400
```

### (c) The `live_method` handler, mixed into every monitored page

oTree calls a page's `live_method` when the client does `liveSend(...)`. The
return value is a dict keyed by `id_in_group` (or `0` to broadcast); oTree
delivers it to that player's `liveRecv`. Implement a shared handler and
attach it to each monitored page:

```python
def focus_live_method(player, data):
    if not isinstance(data, dict) or data.get('type') != 'focus_loss':
        return
    event_id = data.get('event_id')
    seen = player.participant.focus_event_ids or []
    if event_id in seen:                      # dedup — count each real loss once
        return
    seen.append(event_id)
    player.participant.focus_event_ids = seen
    player.participant.focus_loss_count = (player.participant.focus_loss_count or 0) + 1

    if player.participant.focus_loss_count >= C.AI_SAFETY_MAX_VIOLATIONS:
        player.participant.ai_safety_disqualified = True
        return {player.id_in_group: dict(action='disqualified')}
```

Bind it on each monitored page:

```python
class SomeTaskPage(Page):
    live_method = focus_live_method
    ...
    @staticmethod
    def is_displayed(player):
        return not player.participant.ai_safety_disqualified
```

Every monitored page needs **both**: `live_method = focus_live_method` (so
`liveSend`/`liveRecv` exist and violations are recorded) and the
`is_displayed` guard (so once disqualified, the page chain skips forward).

The client's `liveRecv` (already in the JS) reacts to the broadcast:

```js
window.liveRecv = function (data) {
    if (data && data.action === 'disqualified') {
        try { sessionStorage.removeItem('aiSafetyAgreed'); } catch (e) {}
        isNavigatingAway = true;
        cancelLeaveTimer();
        window.location.reload();   // is_displayed chain now lands on Disqualified
    }
};
```

### (d) The Disqualified finish screen (ties to Part 1)

Add a `Disqualified` page in `outro` that is the **only** page shown to a
disqualified participant, and route them to it. Because every monitored page
returns `is_displayed = False` once `ai_safety_disqualified` is set, the
participant falls through to outro on reload. There:

```python
class Disqualified(Page):
    @staticmethod
    def is_displayed(player):
        return player.participant.ai_safety_disqualified

    def js_vars(player):
        code = player.session.config["dq_code"]   # add a dq_code to settings
        return dict(completionlink="https://app.prolific.co/submissions/complete?cc=" + str(code))

# and guard the normal endings so they DON'T show to disqualified participants:
class Demographics(Page):
    @staticmethod
    def is_displayed(player):
        return not player.participant.ai_safety_disqualified

class Results(Page):
    @staticmethod
    def is_displayed(player):
        return not player.participant.ai_safety_disqualified

page_sequence = [Disqualified, Demographics, Results]
```

The `Disqualified.html` is a finish screen exactly like §1.3: a short
explanation plus a "Back to Prolific" button using `js_vars.completionlink`
(built from a dedicated `dq_code`). This is why Part 1 comes first — the
disqualification path reuses the same completion-redirect machinery.

## 2.6 Part 2 checklist

- [ ] Rename `prolific/tab-switch monitor.txt` → `_static/global/js/ai_safety_monitor.js`
      and include it on monitored pages (alongside `global.js`).
- [ ] Add an arming page that sets `sessionStorage.aiSafetyAgreed = '1'` on
      agreement.
- [ ] `settings.py`: add `ai_safety_disqualified`, `focus_loss_count`,
      `focus_event_ids` to `PARTICIPANT_FIELDS`; add a `dq_code` to each
      session config.
- [ ] `intro/__init__.py`: add the `AI_SAFETY_*` constants (mirror the JS).
- [ ] Add the `focus_live_method` handler; set `live_method` **and** the
      `is_displayed` guard on every monitored page.
- [ ] `outro`: add a `Disqualified` page (with `dq_code` redirect) at the top
      of `page_sequence`, and guard the normal endings with
      `is_displayed = not ai_safety_disqualified`.
- [ ] Verify the JS↔server constants stay in sync and that `liveSend`/
      `liveRecv` are present on monitored pages.

---

## Reference files in PP (for the worker — cannot be opened directly)

All paths under `Perceived Value-for-Money (TI-Thesis)/paymentpressure/`.
Every relevant snippet from these has been reproduced above.

- `settings.py` — `cc_code` / `error_code` in session configs;
  `PARTICIPANT_FIELDS` incl. `timedout`, `wait_page_arrival`;
  `DEBUG=False`; production-style config.
- `phonecheck/__init__.py` — entry app: `prolific_id`, `is_mobile`,
  `consent`, mobile screen-out with error-code link, arrival timestamp.
- `outro/__init__.py` — `Results.js_vars` builds the completion link;
  `Demographics.before_next_page` computes payoff per `timedout` value.
- `outro/Results.html` — branched ending text + "Back to Prolific" button.
- `pp/__init__.py` — `waiting_too_long`, `RoundStartWaitPage` with
  `group_by_arrival_time` and `app_after_this_page` skip-to-outro routing.
- `wait stuff` — `group_by_arrival_time_method` making single-player groups
  on timeout, `waiting_too_long` on the Player.

## Reference files in the template

- `prolific/tab-switch monitor.txt` — the complete client-side monitor (the
  implementation to rename/include for Part 2).
- `_static/global/html/template.html` — where `<script>` includes live.
- `_static/global/js/global.js` — existing global JS.
- `before/__init__.py`, `before/welcome+consent.html` — current consent /
  entry flow to convert.
- `intro/__init__.py` — where AI-safety constants go.
- `outro/__init__.py`, `outro/Results.html` — current single ending +
  bank/SEPA payment flow to replace.
