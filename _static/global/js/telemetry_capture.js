/* BEHAVIOUR CAPTURE — the ONE shared module (measure B3, §D of the bot spec).
   Included on the WELCOME and QUIZ pages only. It records raw passive page
   behaviour and writes it, as a JSON string, into an explicit hidden input on
   the page's OWN form, so it rides the normal page POST — the same reliable
   mechanism as client_ms, never a side request that can fail silently.

   RE-AUTHORED, NOT PASTED, from the documented behaviour of Mission Possible's
   trackers/ (generalTracker.htm + keylog.js), which is UNLICENSED — so this is
   a fresh implementation of the plain-DOM-event APPROACH, never a copy of their
   code. It captures the SAME field family: time on page, mouse moves, clicks,
   scrolls, keystrokes, paste/copy, tab-hidden and window-blur, a timestamped
   event log, keydown timings (for typing cadence) and the largest single-input
   length jump (the paste-without-paste-event signal). It does NOT truncate:
   oTree's LongStringField has no embedded-data byte cap, unlike Qualtrics, so
   the whole blob is stored.

   IT ONLY CAPTURES AND STORES. No derivation happens here — the AI-likelihood
   flags (typing median <= 75 ms, paste, input jump, the counts) are computed
   EX-POST in scripts/format_session_data.py, exactly as Mission Possible derives
   them downstream in Cleaning_Tracker.R. So this file must stay a recorder.

   CONFIG comes from js_vars.TELEMETRY_CONFIG (like tab_monitor.js reads
   TAB_MONITOR_CONFIG and device_capture.js reads DEVICE_UA_RULES — one pattern,
   no private copy): { target: '<hidden field id/name>', page: '<name>',
   fields?: ['<control ids to label>'] }. The quiz passes `fields` (its per-item
   radios + the re-read button) so per-control input jumps are labelled; the
   welcome page has no such structure and passes none.

   A SEPARATE OBSERVER, like focus_trace.js: its own listeners and its own state,
   it never touches the tab-monitor or focus-trace variables. The whole body is
   wrapped — instrumentation must NEVER break the page (CLAUDE.md). A no-op on
   any page without the target hidden input (so it records only where the server
   rendered it). */
(function () {
    'use strict';
    try {
        var cfg = (window.js_vars || {}).TELEMETRY_CONFIG;
        if (!cfg || !cfg.target) { return; }
        var target = document.getElementById(cfg.target)
                     || document.querySelector('[name="' + cfg.target + '"]');
        if (!target) { return; }        // not a page that records this

        var MAX_KEY_TIMES = 400;        // bound the blob; ample for a quiz
        var MAX_EVENTS = 200;

        function now() {
            return (window.performance && performance.now)
                ? performance.now() : Date.now();
        }
        var start = now();

        var state = {
            page: cfg.page || '',
            t_start_epoch_ms: Date.now(),
            mouse_move_count: 0,
            click_count: 0,
            scroll_event_count: 0,
            keydown_count: 0,
            paste_detected: false,
            copy_detected: false,
            tab_hidden: false,          // was the tab ever hidden
            window_blurred: false,      // did the window ever lose focus
            // Raw keydown timestamps (ms since load). Downstream diffs them into
            // inter-keystroke intervals and takes the median (bot_typing_*).
            key_times: [],
            // The largest single-input length increase seen on any field, and
            // per-field detail when config named the fields. Downstream flags
            // max_input_jump > 50 as a paste-without-paste-event (bot_input_jump).
            max_input_jump: 0,
            field_max_jump: {},
            event_log: []               // [{e, t}] timestamped notable events
        };

        function logEvent(name) {
            if (state.event_log.length < MAX_EVENTS) {
                state.event_log.push({ e: name, t: Math.round(now() - start) });
            }
        }

        // Previous value length per input, to size each input event's jump.
        var prevLen = {};

        function fieldKey(el) {
            return (el && (el.name || el.id)) || '';
        }

        function write() {
            try {
                state.time_on_page_ms = Math.round(now() - start);
                target.value = JSON.stringify(state);
            } catch (e) { /* leave whatever was last written */ }
        }

        document.addEventListener('mousemove', function () {
            state.mouse_move_count += 1;
        }, true);
        document.addEventListener('click', function () {
            state.click_count += 1;
        }, true);
        document.addEventListener('scroll', function () {
            state.scroll_event_count += 1;
        }, true);
        document.addEventListener('keydown', function () {
            state.keydown_count += 1;
            if (state.key_times.length < MAX_KEY_TIMES) {
                state.key_times.push(Math.round(now() - start));
            }
        }, true);
        document.addEventListener('paste', function () {
            state.paste_detected = true;
            logEvent('PASTE');
        }, true);
        document.addEventListener('copy', function () {
            state.copy_detected = true;
            logEvent('COPY');
        }, true);
        // Size each input event's length change; a big single jump with no
        // matching keystrokes is the paste-without-paste-event signal.
        document.addEventListener('input', function (ev) {
            try {
                var el = ev.target;
                if (!el || typeof el.value !== 'string') { return; }
                var key = fieldKey(el);
                var len = el.value.length;
                var was = prevLen[key] || 0;
                var jump = len - was;
                prevLen[key] = len;
                if (jump > state.max_input_jump) { state.max_input_jump = jump; }
                if (jump > (state.field_max_jump[key] || 0)) {
                    state.field_max_jump[key] = jump;
                }
            } catch (e) { /* non-fatal */ }
        }, true);

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                state.tab_hidden = true;
                logEvent('TAB_HIDDEN');
            } else {
                logEvent('TAB_VISIBLE');
            }
        });
        window.addEventListener('blur', function () {
            state.window_blurred = true;
            logEvent('WINDOW_BLUR');
        });
        window.addEventListener('focus', function () { logEvent('WINDOW_FOCUS'); });

        // Write on submit (rides the POST), on pagehide, and periodically so a
        // reload/timeout still carries a recent snapshot.
        document.addEventListener('submit', write, true);
        window.addEventListener('pagehide', write);
        setInterval(write, 2000);
        write();   // a page with no interaction still posts a valid blob
    } catch (e) { /* never let behaviour capture break the page */ }
})();
