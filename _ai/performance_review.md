# Performance review: does the added JS / instrumentation slow the participant?

**Headline verdict: No. The overhead is negligible.** Nothing the template adds
does continuous work, per-frame work, or layout thrash during a round, and the
slider drag stays smooth. Page weight is dominated by oTree's own
jQuery + Bootstrap bundle (~331 KB), which is downloaded once and then served
from cache for every subsequent round; the template's own scripts and CSS add
~26 KB on top of that (~36 KB on the Prolific task page), i.e. under ~10 %, and
almost all of that is the CSS design system, not the instrumentation JS.

Measured on this machine: oTree 6.0.15 devserver, throwaway SQLite DB (the real
`db.sqlite3` was set aside and restored), task page driven to over real HTTP.

---

## How this was measured

- Booted `otree devserver_inner` on a fresh database; created a `test`-config
  session via the REST API and drove a participant through consent → instructions
  → quiz to the real task page (`/p/<code>/main/GameStart/<round>`) over HTTP.
- Timed the task page with `curl` (25 repeats): **TTFB and full document time**.
- Fetched **every** stylesheet/script the rendered page references and recorded
  raw transfer size; measured cold full-load wall time (sequential and 6-way
  parallel) and confirmed warm-cache behaviour.
- Read every JS file on the participant path and judged interaction cost by
  inspection (a headless browser is not available here; where a number could not
  be measured that is stated explicitly).

**Caveats on the numbers.** (1) Localhost RTT is ~0, so the wall-clock load times
below are best-case; the *payload* and *request-count* figures are what travels
regardless of network, and are the honest basis for judging a real Prolific
participant on a ~50–100 ms link. (2) The devserver serves assets
**uncompressed** (it ignores `Accept-Encoding`); a real deployment behind
Cloudflare (as in `MACMINI_HOSTING.md`) would gzip/brotli the text assets ~3–4×,
so the ~365 KB cold payload below is roughly ~110–130 KB compressed in
production.

---

## (a) Asset inventory per page

Sizes are raw bytes as served. "Blocking" = in `<head>` with no `defer`/`async`
(blocks first paint); "body" = late in `<body>` (blocks little); the whole set
is byte-identical across rounds and cached after round 1.

### oTree framework baseline (on **every** page, template can't easily remove)

| Asset | Size | Placement |
|---|---:|---|
| `bootstrap5/css/bootstrap.min.css` | 155.6 KB | **head, render-blocking** |
| `otree/js/jquery-3.2.1.min.js` | 86.7 KB | **head, render-blocking** |
| `bootstrap5/js/bootstrap.bundle.min.js` | 78.7 KB | body |
| `otree/js/reconnecting-websocket-iife.min.js` | 8.7 KB | **head, render-blocking** |
| `otree/css/theme2.css` | 2.6 KB | **head, render-blocking** |
| `otree/js/{common_user_facing,formInputs,live,page-websocket-redirect,back_button,internet-explorer}.js` | ~6.0 KB total | head + body |
| **oTree baseline subtotal** | **~331 KB** | |

### Template-owned assets

| Asset | Size | Where it loads | Placement |
|---|---:|---|---|
| `global/style.css` bundle (see below) | **23.4 KB** | task, instructions, quiz (all) | body, render-blocking |
| `global/js/global.js` | 2.7 KB | task, instructions, quiz, payoff | body |
| `global/js/ai_safety_monitor.js` | 9.3 KB | task + payoff **only when `tab_monitor` on** | body |
| `global/js/instructions.js` | 4.6 KB | instruction page only | body |
| `global/js/quiz.js` | 2.0 KB | quiz page only | body |
| `global/js/device_capture.js` | 2.5 KB | welcome/consent page only | body |
| passive-capture inline (`client_ms`) | ~0.4 KB | task page only when `passive_capture` on | body |

The `style.css` bundle is a single link that `@import`s 5 files:
`base.css` 16.4 KB · `instructions.css` 2.3 KB · `results.css` 1.3 KB ·
`quiz.css` 1.8 KB · `demographics.css` 1.3 KB (+236 B wrapper) = **23.4 KB**.
On the task page, ~7 KB of that (instructions/results/quiz/demographics CSS) is
loaded but unused.

### Totals per page (cold, uncompressed)

| Page | Cold total | Of which template-owned |
|---|---:|---:|
| **Task page** (`test`, modules off) | **~365 KB** | ~26 KB |
| **Task page** (`prolific`: tab_monitor + passive on) | **~374 KB** | ~36 KB |
| Instruction page | ~370 KB | ~31 KB |
| Quiz page | ~367 KB | ~28 KB |

Round 2 onward: every asset above returns **304 Not Modified** (etag present),
so the participant re-downloads only the ~7 KB HTML document per round.

## (b) Measured load timing (task page, over HTTP)

| Metric | Value |
|---|---|
| HTML document size | 7.2 KB |
| **TTFB** (25 reps) | median **6.9 ms**, max 11.1 ms |
| Full document time | median 7.0 ms |
| Cold full-load, all 18 subresources, 6-way parallel | **56 ms** (localhost) |
| Cold full-load, sequential (1 connection) | 156 ms (localhost) |
| Warm load (rounds 2–24) | HTML only; all subresources 304, ~0 body |

TTFB includes oTree binding the `live_method` websocket handler — no measurable
penalty (~7 ms). The 56 ms cold figure is localhost; the real cost on a
participant's link is ~one RTT for the HTML plus a parallel fetch of ~110–130 KB
compressed static, **once**, then effectively free for the remaining rounds.

## (c)/(d) Interaction cost during a round

Read of every script on the task path. Looked specifically for: `mousemove`/
`scroll` listeners, continuous timers/rAF, synchronous work in the slider
handler, layout reads (`offsetWidth`/`getBoundingClientRect`) inside drag/resize
handlers, per-keystroke/per-step work, and `visibilitychange` work.

| Component | Cost at load | Cost during interaction | Verdict |
|---|---|---|---|
| **Tab-switch monitor** (`ai_safety_monitor.js`) | 9.3 KB parse, one-time DOM build of two hidden overlays | Listeners are `mousedown`/`mouseup`/`blur`/`focus`/`visibilitychange`/`submit`/`beforeunload`/`pagehide` — **no `mousemove`, no `scroll`**. `mousedown`/`mouseup` set one boolean (mouseup arms a single 300 ms timeout). `visibilitychange` only sets/clears two timers, and only fires on a real tab switch, not continuously. The `setInterval` runs **only while the "return to study" overlay is showing** (i.e. after the participant already left) — never during normal play. A `liveSend` websocket message fires **only on an actual violation**, not per frame. | **Fine** |
| **Passive capture** (inline) | ~0.4 KB; records `Date.now()` at load | One `submit` listener that writes one field on navigation. Zero cost during the round. | **Fine** |
| **Device capture** (`device_capture.js`) | Runs once at DOMContentLoaded — **on the consent page, not the task page** | None (not present during rounds) | **Fine** |
| **`global.js`** | 2.7 KB | One `keydown` listener that early-returns unless the key is Enter. No per-keystroke work of note. | **Fine** |
| **`instructions.js`** | 4.6 KB, instruction page only | Reads `scrollHeight`/`innerHeight` **only in `updateView()` on a nav click**, never in a drag/resize handler (there is no resize listener). Arrow-key handler early-returns on non-arrow keys. | **Fine** |
| **Elicitation widget** (`elicit.js`, pilot snapshot — the 24× slider) | 2.5 KB | Slider `input` handler does: one `parseInt`, two `style.width` writes, two `textContent` writes, one `setAttribute`. **No layout reads** (`offsetWidth`/`getBoundingClientRect`) — so **no forced synchronous layout / no layout thrash**. Pure writes the browser batches; work per step is microseconds. | **Fine — drag stays smooth** |
| **CSS design system** (`style.css` @import bundle) | 23.4 KB, render-blocking; **5-file `@import` waterfall** (imports discovered only after `style.css` parses → +1 RTT cold) | None during interaction | **Fine at load; @import chain is a minor, optional cleanup** |
| **Cache-busted static includes** | `?v=` query on each include | None | **Fine** |

### Specific answer on the slider (the 24× interaction)

**The drag stays smooth.** `elicit.js`'s `input` handler is write-only and touches
no geometry APIs, so it cannot cause the read-after-write layout thrash that
makes sliders janky. There is no `requestAnimationFrame` loop, no throttling
needed, and no work proportional to drag distance beyond a constant handful of
DOM writes per step. Note this widget currently lives only in
`_ai/pilot_snapshot/` — the shipped `main/game.html` task page is a stub with no
slider — but when the widget is ported in, its handler is already cheap. *(This
one is reasoned from code inspection, not measured, because the widget isn't on
the live task page yet and no headless browser is available here.)*

---

## Recommendations (only where a real cost exists)

There is **no must-fix and no should-fix**. Two optional, low-value cleanups:

1. **CSS `@import` waterfall / unused CSS on the task page** *(cosmetic).*
   `style.css` serially `@import`s 5 files; the browser can't discover them until
   `style.css` arrives, adding one round trip on the first cold load, and ~7 KB
   of the bundle (instructions/results/quiz CSS) is unused on the task page.
   If ever trimming first-paint matters, concatenate the imports into one file
   (or `<link>` them directly so they fetch in parallel) and split out the task
   page's CSS. Payoff is one RTT on round 1 only — genuinely marginal.

2. **Add `Cache-Control: max-age` to static assets** *(deployment concern, not
   code).* Assets currently ship with `etag`/`last-modified` but no explicit
   max-age, so each later page issues a conditional request per asset (returns
   304, ~0 bytes, but still a round trip on a high-latency link). A far-future
   `Cache-Control` on `/static/` at the proxy — the `?v=` query already busts the
   cache on deploy — removes those revalidations. Cloudflare in front of the Mac
   mini deployment already mitigates this.

**Bottom line:** the instrumentation is not a performance problem. The heavy part
of every page is oTree's own jQuery + Bootstrap, downloaded once per session; the
template's additions are small, non-blocking in practice, do no work between
interactions, and keep the slider drag smooth. Do not optimise.
