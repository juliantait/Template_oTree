// Device / screen capture module.
//
// Fills two hidden fields on the entry page's OWN form (no side requests):
//   - #is_mobile           : "True"/"False" — MEASUREMENT ONLY; it never blocks
//                            anyone. Screening devices out is the server-side
//                            `prolific_allowed_devices` gate's job (before/__init__.py),
//                            because it must decide before consent is rendered,
//                            i.e. before this script has ever run.
//   - #device_info_json    : a JSON blob of screen/browser facts, INCLUDING the
//                            client's own `device_type` guess (see below)
// Both submit with the page, so the values land in the same POST as consent.
//
// Enabled by the `telemetry_device_capture` (and `prolific_capture_participant_id`) session flags;
// this script is only included on the page when one of them is on
// (`captures_device` — one predicate, in before._captures_device).
//
// =============================================================================
// THERE IS NO PATTERN LIST IN THIS FILE. THAT IS THE POINT.
// =============================================================================
// The User-Agent rules come from the SERVER, through js_vars
// (`before.welcome.js_vars` -> `common.device_ua_rules`), and are applied here.
// This script used to carry its own copy of them, and the copies had already
// drifted: `Mobile/\d`, `BB10` and `Nexus 7|9|10` were server-only, and the
// computer test here was an unanchored `Linux` where the server's excludes
// Android. So an iOS in-app browser (a Prolific participant opening the study
// from a messaging app) was recorded as "server says phone, client says
// unknown" — INDISTINGUISHABLE from the genuine client/server disagreement this
// measurement exists to expose.
//
// One list removes that cause of disagreement entirely. What remains is kept
// APART and each state is named in the JSON (full argument in
// common.device_ua_rules):
//
//   ua_rules            'server'      the rules arrived and were applied
//                       'unavailable' they did not — and we then classify
//                                     NOTHING rather than falling back to a
//                                     private copy, because a silent fallback
//                                     is exactly the second list this removes
//   device_type_ua      this browser's OWN navigator.userAgent under the
//                       server's rules. Should equal the server's
//                       `entry_device_type`; if it does not, the browser is
//                       reporting a different User-Agent than the request
//                       header carried (extension, proxy, client hints)
//   device_type         the FINAL client answer: device_type_ua refined by
//                       signals the server cannot see (touch, viewport)
//   device_type_signals which of those signals fired, so a difference between
//                       the last two is attributable rather than mysterious
//
// It still cannot tell a laptop from a desktop — nothing in a browser can, so
// both are 'computer' here too (see the note in settings.py). And it is
// RECORDED, NEVER ENFORCED: the gate has already run server-side by the time
// this executes, and anything a client reports can be edited by whoever is
// sitting at it.
(function captureDevice() {
    var UNAVAILABLE = 'unavailable';

    // The server's rules, or null if they did not reach this page.
    function serverRules() {
        try {
            var r = (window.js_vars || {}).DEVICE_UA_RULES;
            if (!r || !r.order || !r.patterns) return null;
            for (var i = 0; i < r.order.length; i++) {
                if (typeof r.patterns[r.order[i]] !== 'string') return null;
            }
            return r;
        } catch (e) {
            return null;
        }
    }

    // The server's own classify_device, applied to this browser's UA. Same
    // order, same "not usable at all" tests, same vocabulary — because it is
    // the same rules, not a reimplementation of them.
    function classifyWithRules(ua, rules) {
        try {
            if (!ua || !ua.trim()) return rules.undetermined;
            if (rules.max_len && ua.length > rules.max_len) return rules.undetermined;
            if (rules.illegal && new RegExp(rules.illegal).test(ua)) return rules.undetermined;
            for (var i = 0; i < rules.order.length; i++) {
                var name = rules.order[i];
                if (new RegExp(rules.patterns[name], 'i').test(ua)) return name;
            }
            return rules.unknown;
        } catch (e) {
            return rules.undetermined;
        }
    }

    // THE CLIENT-ONLY REFINEMENT: what this browser knows and the header does
    // not. Each signal is named in `device_type_signals`, so a client/server
    // difference can be attributed to the signal that caused it.
    function refine(base, ua) {
        var signals = [];
        var type = base;
        try {
            var touch = (navigator.maxTouchPoints || 0) > 1;
            // iPadOS 13+ reports itself as a Macintosh; the touch points give
            // it away. The server sees only the UA and honestly records
            // 'computer' — this is the disagreement worth having.
            if (touch && /Macintosh/i.test(ua) && type === 'computer') {
                type = 'tablet';
                signals.push('ipados_touch');
            }
        } catch (e) { /* leave the base answer alone */ }
        return { type: type, signals: signals };
    }

    function narrowViewport() {
        try {
            var w = Math.min(window.innerWidth || 0,
                             window.screen ? window.screen.width : 0);
            return w > 0 && w < 720;
        } catch (e) {
            return false;
        }
    }

    function coarsePointer() {
        try { return window.matchMedia('(pointer: coarse)').matches; } catch (e) { return false; }
    }

    // `is_mobile`: "small screen, and it looks like a hand-held". Its own
    // measurement with its own definition — deliberately NOT the same question
    // as the four-way device type (the server's is_mobile_user_agent ignores
    // the viewport, which this cannot, being in a real browser). It takes the
    // UA half from the SAME server rules rather than a third pattern list.
    function isMobile(uaType) {
        var narrow = narrowViewport();
        var uaMobile = (uaType === 'phone' || uaType === 'tablet');
        return (uaMobile && narrow) || (coarsePointer() && narrow);
    }

    function deviceInfo() {
        var s = window.screen || {};
        var ua = navigator.userAgent || '';
        var rules = serverRules();
        var uaType = rules ? classifyWithRules(ua, rules) : UNAVAILABLE;
        var refined = rules ? refine(uaType, ua)
                            : { type: UNAVAILABLE, signals: [] };
        return {
            // The client's FINAL answer; the server's is authoritative.
            device_type: refined.type,
            // The same UA under the server's rules, before client-only signals.
            device_type_ua: uaType,
            device_type_signals: refined.signals,
            ua_rules: rules ? 'server' : UNAVAILABLE,
            user_agent: ua,
            platform: navigator.platform || '',
            language: navigator.language || '',
            screen_w: s.width || null,
            screen_h: s.height || null,
            avail_w: s.availWidth || null,
            avail_h: s.availHeight || null,
            viewport_w: window.innerWidth || null,
            viewport_h: window.innerHeight || null,
            device_pixel_ratio: window.devicePixelRatio || null,
            touch_points: navigator.maxTouchPoints || 0,
            timezone_offset_min: new Date().getTimezoneOffset(),
        };
    }

    function fill() {
        var info = null;
        try { info = deviceInfo(); } catch (e) { info = null; }
        var mobileEl = document.getElementById('is_mobile');
        if (mobileEl) {
            var uaType = info ? info.device_type_ua : UNAVAILABLE;
            mobileEl.value = isMobile(uaType) ? 'True' : 'False';
        }
        var infoEl = document.getElementById('device_info_json');
        if (infoEl) {
            try { infoEl.value = info ? JSON.stringify(info) : ''; } catch (e) { infoEl.value = ''; }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fill);
    } else {
        fill();
    }
})();
