/* Per-page PASSIVE FOCUS TRACE — browser half (server half: the focus_trace_*
   fields on main.Player + the wiring in main/__init__.py).

   Ported from exp_pilots (focustrace.js) as NET-NEW passive MEASUREMENT. It
   records, for THIS page only: how many times the window lost focus or the tab
   was hidden (a DEPARTURE count), and the total ms the page spent unfocused or
   hidden. The two values ride the page's own form submit as hidden inputs
   (#focus_trace_departures / #focus_trace_unfocused_ms) — the SAME reliable
   mechanism as the passive client_ms field, never a side request that can fail
   silently.

   ── A SEPARATE OBSERVER FROM THE TAB MONITOR, DELIBERATELY ──────────────────
   tab_monitor.js is the LIVE DISQUALIFICATION path (violation counting against
   tab_monitor_max_violations, the warning modal, the red overlay, the reload
   that routes to the ending). That behaviour must stay EXACTLY as it is; it is
   separately fuzz-tested. This file therefore does NOT touch it:

     * it is its OWN file — tab_monitor.js is unchanged, byte for byte;
     * it adds only its OWN listeners and keeps only its OWN state;
     * it NEVER calls preventDefault, NEVER calls liveSend, NEVER reads or
       writes any tab-monitor variable, and NEVER reports anything to the
       server outside the page's own form post — so it can never disqualify
       anyone, never move a violation count, and never trip the overlay/modal.

   DOM listeners are ADDITIVE: two independent listeners on the same `blur` /
   `visibilitychange` event cannot cancel or interfere with each other, so the
   monitor's counting, thresholds, warnings and disqualification route are
   untouched by anything here. The two also MEASURE DIFFERENT THINGS — the tab
   monitor counts only departures longer than tab_monitor_threshold_ms on
   monitored pages for a participant who armed it; this counts EVERY departure
   on a page carrying the hidden inputs, regardless of length or arming. A
   participant can have a positive trace with zero tab-monitor violations.

   A NO-OP on any page WITHOUT the hidden inputs, so it records only where the
   server rendered them (the task screen, when telemetry_focus_trace is on). The
   whole body is wrapped: instrumentation must NEVER be able to break the page
   (CLAUDE.md). */
(function () {
    'use strict';
    try {
        var countEl = document.getElementById('focus_trace_departures');
        var msEl = document.getElementById('focus_trace_unfocused_ms');
        if (!countEl && !msEl) { return; }   // not a page that records this

        // A mousedown inside the page can blur the window for an instant (a
        // control, a select, an embedded widget): ignore a blur that lands
        // within this grace window after one. This mirrors the INTENT of the tab
        // monitor's own in-page-click guard, but with its OWN state — nothing is
        // shared between the two observers.
        var CLICK_GRACE_MS = 300;

        var count = 0;
        var awayMs = 0;
        var awaySince = null;       // timestamp of the currently-open away interval
        var lastMouseDown = 0;
        var navigatingAway = false;

        function now() {
            return (window.performance && performance.now)
                ? performance.now() : Date.now();
        }

        function write() {
            // Include any interval STILL OPEN, so a submit made while the page is
            // (somehow) unfocused still accounts for the time away.
            var total = awayMs + (awaySince === null ? 0 : (now() - awaySince));
            if (countEl) { countEl.value = count; }
            if (msEl) { msEl.value = total.toFixed(1); }
        }

        // One DEPARTURE = one focus loss, however the browser reports it. A tab
        // switch fires blur AND visibilitychange; the open-interval guard
        // (awaySince !== null) makes that pair count once.
        function leave(fromBlur) {
            if (navigatingAway || awaySince !== null) { return; }
            if (fromBlur && (now() - lastMouseDown) < CLICK_GRACE_MS) { return; }
            awaySince = now();
            count += 1;
            write();
        }

        function back() {
            if (awaySince === null) { return; }
            awayMs += now() - awaySince;
            awaySince = null;
            write();
        }

        document.addEventListener('mousedown', function () { lastMouseDown = now(); });
        window.addEventListener('blur', function () { leave(true); });
        window.addEventListener('focus', back);
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) { leave(false); } else { back(); }
        });

        // Normal navigation is NOT a departure.
        function markNavigating() { navigatingAway = true; write(); }
        document.addEventListener('submit', markNavigating, true);
        window.addEventListener('pagehide', markNavigating);

        // Exposed so a task page's own submit handler can take a final snapshot
        // alongside its other hidden fields. Not required — the capture-phase
        // submit listener above already writes on submit — but kept for parity
        // with the passive client_ms capture and any study that wants to force a
        // snapshot at a custom moment.
        window.captureFocusTrace = write;
        write();   // a page with no focus loss still posts 0 / 0.0
    } catch (e) { /* never let the focus trace break the page */ }
})();
