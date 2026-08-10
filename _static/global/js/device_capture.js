// Device / screen capture module.
//
// Fills two hidden fields on the entry page's OWN form (no side requests):
//   - #is_mobile           : "True"/"False" — MEASUREMENT ONLY; it never blocks
//                            anyone. Screening phones out is the server-side
//                            `mobile_screenout` gate's job (before/__init__.py),
//                            because it must decide before consent is rendered,
//                            i.e. before this script has ever run.
//   - #device_info_json    : a JSON blob of screen/browser facts
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

    function deviceInfo() {
        var s = window.screen || {};
        return {
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
