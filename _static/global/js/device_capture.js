// Device / screen capture module.
//
// Fills two hidden fields on the entry page's OWN form (no side requests):
//   - #is_mobile           : "True"/"False" — MEASUREMENT ONLY; it never blocks
//                            anyone. Screening devices out is the server-side
//                            `allowed_devices` gate's job (before/__init__.py),
//                            because it must decide before consent is rendered,
//                            i.e. before this script has ever run.
//   - #device_info_json    : a JSON blob of screen/browser facts, INCLUDING the
//                            client's own `device_type` guess (see below)
// Both submit with the page, so the values land in the same POST as consent.
//
// Enabled by the `device_capture` (and `capture_participant_id`) session flags;
// this script is only included on the page when one of them is on.
(function captureDevice() {
    function isMobile() {
        // Combine a coarse-pointer/UA check with a viewport-width heuristic.
        var ua = navigator.userAgent || '';
        var uaMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
        var coarse = false;
        try { coarse = window.matchMedia('(pointer: coarse)').matches; } catch (e) {}
        var narrow = Math.min(window.innerWidth || 0, window.screen ? window.screen.width : 0) < 720;
        // Treat as mobile only when the UA looks mobile AND the screen is small,
        // OR the pointer is coarse and the screen is small (tablets/phones),
        // so a small desktop window is not misclassified.
        return (uaMobile && narrow) || (coarse && narrow);
    }

    // THE CLIENT'S OWN CLASSIFICATION, mirroring the server's four types
    // (common.detect_device_type): 'phone' | 'tablet' | 'computer' | 'unknown'.
    // It is RECORDED, NEVER ENFORCED — the gate has already run server-side by
    // the time this executes, and anything a client reports can be edited by
    // whoever is sitting at it. Its value is keeping the two side by side in
    // the export, so a disagreement (an iPadOS tablet claiming to be a Mac, a
    // stripped User-Agent) is visible rather than invisible.
    //
    // It can use signals the server cannot: touch points and viewport size. It
    // still cannot tell a laptop from a desktop — nothing in a browser can, so
    // both are 'computer' here too (see the note in settings.py).
    function deviceType() {
        var ua = navigator.userAgent || '';
        if (!ua) return 'unknown';
        var touch = (navigator.maxTouchPoints || 0) > 1;
        // iPadOS 13+ reports itself as a Macintosh; the touch points give it away.
        if (/iPad/i.test(ua) || (/Macintosh/i.test(ua) && touch)) return 'tablet';
        if (/Android/i.test(ua) && !/Mobile/i.test(ua)) return 'tablet';
        if (/Tablet|Kindle|Silk|PlayBook/i.test(ua)) return 'tablet';
        if (/iPhone|iPod|Android.*Mobile|webOS|BlackBerry|IEMobile|Opera Mini|Windows Phone|Mobile Safari/i.test(ua)) {
            return 'phone';
        }
        if (/Windows NT|Macintosh|Mac OS X|X11|CrOS|Linux|FreeBSD|OpenBSD/i.test(ua)) {
            return 'computer';
        }
        return 'unknown';
    }

    function deviceInfo() {
        var s = window.screen || {};
        return {
            device_type: deviceType(),   // client's guess; the server's is authoritative
            user_agent: navigator.userAgent || '',
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
        var mobileEl = document.getElementById('is_mobile');
        if (mobileEl) mobileEl.value = isMobile() ? 'True' : 'False';
        var infoEl = document.getElementById('device_info_json');
        if (infoEl) {
            try { infoEl.value = JSON.stringify(deviceInfo()); } catch (e) { infoEl.value = ''; }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fill);
    } else {
        fill();
    }
})();
