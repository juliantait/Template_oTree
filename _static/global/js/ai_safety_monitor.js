// ── AI-safety / tab-switch monitor ───────────────────────────────────────────
// Client half of the integrity module. Server authority is
// participant.tab_monitor_disqualified, set by common.focus_live_method (bound
// on every monitored page by participant_tab_monitor.MonitoredPage — pages are monitored
// BY DEFAULT after the agreement screen; see participant_tab_monitor.py).
//
// CREDITED TO NICOLAS ORLINK (original client logic).
//
// Activates ONLY when BOTH of these hold:
//   * the participant agreed on the AI-safety arming page, which sets
//     sessionStorage.aiSafetyAgreed = '1';
//   * THIS page's js_vars carry AI_SAFETY_CONFIG (common.monitor_js_vars —
//     absent when the tab_monitor module is off, and absent on a page that
//     opted out with `monitored = False`). The config is REQUIRED: there is
//     deliberately NO defaults fallback any more — the old fallback was a
//     second copy of settings.SESSION_CONFIG_DEFAULTS that had to be kept in
//     sync by a comment, i.e. exactly the two-implementations drift this
//     template hunts. No config, no monitor, silently — that is the server
//     saying this page is not monitored.
//
// THE PHASE ASYMMETRY (Julian, 2026-08-13): AI_SAFETY_CONFIG.ejects says
// whether violations on this page can END the participation (intro + main:
// true) or are RECORDED ONLY (outro: false — the task is over and the data
// collected, so a completer is never ejected). In record-only mode this
// script still counts and reports over the live socket, but shows NO overlay
// and NO warning modal: the modal's threat ("will end your participation")
// would be a lie where nothing ejects.
//
// The config is read from the js_vars global oTree emits into the page —
// lazily, at start time, because this script may be parsed before that
// <script> block depending on where the shared bundle sits in the template.
(function () {
    function readConfig() {
        try {
            if (typeof js_vars !== 'undefined' && js_vars
                    && js_vars.AI_SAFETY_CONFIG) {
                return js_vars.AI_SAFETY_CONFIG;
            }
        } catch (e) { /* fall through: no config, no monitor */ }
        return null;
    }

    function aiSafetyArmed() {
        try { return sessionStorage.getItem('aiSafetyAgreed') === '1'; }
        catch (e) { return false; }
    }

    // NB: there is no path-based "unmonitored section" check any more. The
    // outro used to be disarmed here by matching '/outro/' in the URL — a
    // second spelling of "which pages are monitored" that the server now owns
    // outright: a page without AI_SAFETY_CONFIG in its js_vars is not
    // monitored, wherever it lives.

    // Build the two full-screen pieces. APPENDED TO <body> ON PURPOSE: they are
    // position:fixed and must cover the whole viewport, not the card. The card is
    // height-capped with a scrolling middle region, so anything appended inside
    // it would be clipped by that scroll box.
    //
    // ALL STYLING LIVES IN _static/global/css/tabmonitor.css — do not reintroduce
    // inline style strings here. They cannot follow the design tokens, they
    // hardcoded colours that were in neither palette, and they made the monitor's
    // chrome unreachable from CSS. Visibility is a CLASS (.is-visible), so the
    // stylesheet owns the display value too.
    function buildTabMonitorDom(AI_SAFETY) {
        if (document.getElementById('tabmon-overlay')) return;
        var thresholdSec = Math.ceil(AI_SAFETY.THRESHOLD_MS / 1000);

        var overlay = document.createElement('div');
        overlay.id = 'tabmon-overlay';
        overlay.className = 'tabmon-overlay';
        overlay.innerHTML = ''
          + '<div class="tabmon-overlay__box">'
          +   '<p class="tabmon-overlay__title">Return to the study</p>'
          +   '<p class="tabmon-overlay__msg">The study page is no longer active.<br>'
          +     'Return within <strong>' + thresholdSec + '&nbsp;seconds</strong> to avoid a recorded violation.</p>'
          +   '<div id="tabmon-countdown" class="tabmon-countdown">' + thresholdSec + '</div>'
          + '</div>';
        document.body.appendChild(overlay);

        var modal = document.createElement('div');
        modal.id = 'tabmon-modal';
        modal.className = 'tabmon-modal';
        modal.innerHTML = ''
          + '<div class="tabmon-modal__box">'
          +   '<p id="tabmon-modal-text" class="tabmon-modal__text"></p>'
          +   '<button type="button" id="tabmon-modal-btn" class="tabmon-modal__btn">'
          +     'Understood — continue</button>'
          + '</div>';
        document.body.appendChild(modal);

        document.getElementById('tabmon-modal-btn').addEventListener('click', function () {
            modal.classList.remove('is-visible');
            window._tabmonModalOpen = false;
        });
    }

    function startTabMonitor() {
        var cfg = readConfig();
        if (!cfg) return;   // no server config: this page is not monitored
        var AI_SAFETY = {
            MAX_VIOLATIONS: cfg.max_violations,
            THRESHOLD_MS: cfg.threshold_ms,
            OVERLAY_DELAY_MS: cfg.overlay_delay_ms,
            // false = record-only phase (outro): count and report, no UI.
            EJECTS: !!cfg.ejects,
        };
        if (!aiSafetyArmed() || window._tabmonStarted) return;
        window._tabmonStarted = true;
        // RECORD-ONLY MODE BUILDS NO UI AT ALL: no overlay, no modal — the
        // nulls below make every show/hide a no-op, and counting + liveSend
        // carry on untouched.
        if (AI_SAFETY.EJECTS) buildTabMonitorDom(AI_SAFETY);

        var overlay = document.getElementById('tabmon-overlay');
        var modal = document.getElementById('tabmon-modal');
        var countdownEl = document.getElementById('tabmon-countdown');
        var modalText = document.getElementById('tabmon-modal-text');

        var count = parseInt(sessionStorage.getItem('focusLossCount') || '0', 10);
        var leaveTimer = null;
        var overlayTimer = null;
        var countdownInterval = null;
        var overlayVisible = false;
        var clickedInside = false;
        var isNavigatingAway = false;
        window._tabmonModalOpen = false;

        function showOverlay() {
            if (!overlay || overlayVisible || isNavigatingAway) return;
            overlayVisible = true;
            overlay.classList.add('is-visible');
            var remaining = Math.ceil(
                (AI_SAFETY.THRESHOLD_MS - AI_SAFETY.OVERLAY_DELAY_MS) / 1000
            );
            countdownEl.textContent = remaining;
            countdownInterval = setInterval(function () {
                remaining -= 1;
                countdownEl.textContent = Math.max(remaining, 0);
                if (remaining <= 0) { clearInterval(countdownInterval); countdownInterval = null; }
            }, 1000);
        }

        function hideOverlay() {
            if (!overlay || !overlayVisible) return;
            overlayVisible = false;
            overlay.classList.remove('is-visible');
            if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null; }
        }

        function showModal(text) {
            if (!modal) return;   // record-only mode: no UI exists
            window._tabmonModalOpen = true;
            modalText.textContent = text;
            modal.classList.add('is-visible');
        }

        function recordViolation() {
            hideOverlay();
            if (window._tabmonModalOpen) return;
            count += 1;
            try { sessionStorage.setItem('focusLossCount', String(count)); } catch (e) {}
            var event_id = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
            if (typeof liveSend === 'function') {
                try {
                    liveSend({ type: 'focus_loss', event_id: event_id, count: count,
                               timestamp: Date.now(), page: window.location.pathname });
                } catch (e) {}
            }
            // The warning is EJECT-MODE ONLY: in the record-only phase its
            // threat ("will end your participation") would be a lie, so
            // nothing is shown at all — the violation is still counted and
            // reported above.
            if (AI_SAFETY.EJECTS && count < AI_SAFETY.MAX_VIOLATIONS) {
                showModal(
                    'Warning ' + count + ' of ' + AI_SAFETY.MAX_VIOLATIONS +
                    ': we recorded that the study tab was inactive. One more such ' +
                    'event will end your participation and you may no longer be ' +
                    'eligible for payment or bonus compensation.'
                );
            }
        }

        function startLeaveTimer() {
            if (!aiSafetyArmed() || isNavigatingAway) return;
            if (leaveTimer || window._tabmonModalOpen) return;
            overlayTimer = setTimeout(function () { overlayTimer = null; showOverlay(); }, AI_SAFETY.OVERLAY_DELAY_MS);
            leaveTimer = setTimeout(function () { leaveTimer = null; recordViolation(); }, AI_SAFETY.THRESHOLD_MS);
        }

        function cancelLeaveTimer() {
            if (overlayTimer) { clearTimeout(overlayTimer); overlayTimer = null; }
            if (leaveTimer)   { clearTimeout(leaveTimer);   leaveTimer   = null; }
            hideOverlay();
        }

        if (overlay) {
            overlay.addEventListener('click', function () { cancelLeaveTimer(); });
        }
        document.addEventListener('mousedown', function () { clickedInside = true; });
        document.addEventListener('mouseup',   function () { setTimeout(function () { clickedInside = false; }, 300); });
        window.addEventListener('blur', function () { if (clickedInside) return; startLeaveTimer(); });
        window.addEventListener('focus', function () { cancelLeaveTimer(); });
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) startLeaveTimer(); else cancelLeaveTimer();
        });

        // Server-driven redirect on disqualification.
        window.liveRecv = function (data) {
            if (data && data.action === 'disqualified') {
                try { sessionStorage.removeItem('aiSafetyAgreed'); } catch (e) {}
                isNavigatingAway = true;
                cancelLeaveTimer();
                window.location.reload();  // is_displayed chain now lands on the ending
            }
        };

        function markNavigatingAway() { isNavigatingAway = true; cancelLeaveTimer(); }
        document.addEventListener('submit', markNavigatingAway, true);
        window.addEventListener('beforeunload', markNavigatingAway);
        window.addEventListener('pagehide', markNavigatingAway);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startTabMonitor);
    } else {
        startTabMonitor();
    }
})();
