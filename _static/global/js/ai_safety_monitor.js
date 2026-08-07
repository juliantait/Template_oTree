// ── AI-safety / tab-switch monitor ───────────────────────────────────────────
// Client half of the integrity module. Server authority is
// participant.ai_safety_disqualified, set by common.focus_live_method (bound as
// live_method on each monitored page).
//
// CREDITED TO NICOLAS ORLINK (original client logic).
//
// Activates ONLY after the participant agreed on the AI-safety arming page,
// which sets sessionStorage.aiSafetyAgreed = '1'. Thresholds come from
// window.AI_SAFETY_CONFIG (set server-side via js_vars from the session config),
// falling back to the defaults below. Keep those defaults in sync with
// settings.SESSION_CONFIG_DEFAULTS.
(function () {
    var cfg = (window.AI_SAFETY_CONFIG || {});
    var AI_SAFETY = {
        MAX_VIOLATIONS: cfg.max_violations || 2,
        THRESHOLD_MS: cfg.threshold_ms || 4000,
        OVERLAY_DELAY_MS: cfg.overlay_delay_ms || 400,
    };

    function aiSafetyArmed() {
        try { return sessionStorage.getItem('aiSafetyAgreed') === '1'; }
        catch (e) { return false; }
    }

    // Outro pages (survey, payment, thank-you, disqualified) are post-experiment;
    // disable the monitor there so copying a completion code isn't penalised.
    function inUnmonitoredSection() {
        try { return /\/outro\//i.test(window.location.pathname); }
        catch (e) { return false; }
    }

    function buildTabMonitorDom() {
        if (document.getElementById('tabmon-overlay')) return;
        var thresholdSec = Math.ceil(AI_SAFETY.THRESHOLD_MS / 1000);

        var overlay = document.createElement('div');
        overlay.id = 'tabmon-overlay';
        overlay.style.cssText = [
            'display:none', 'position:fixed', 'inset:0', 'z-index:9000',
            'background:rgba(198,40,40,0.92)', 'color:white',
            'flex-direction:column', 'align-items:center', 'justify-content:center',
            'text-align:center', 'padding:24px',
            'font-family:Arial, Helvetica, sans-serif',
            'backdrop-filter:blur(2px)', 'cursor:pointer',
        ].join(';');
        overlay.innerHTML = ''
          + '<div style="background:rgba(255,255,255,0.08); border:2px solid white;'
          + ' border-radius:12px; padding:28px 36px; max-width:520px;">'
          +   '<p style="font-size:24px; font-weight:bold; margin:0 0 10px 0;">Return to the study</p>'
          +   '<p style="font-size:15px; margin:0 0 14px 0;">The study page is no longer active.<br>'
          +     'Return within <strong>' + thresholdSec + '&nbsp;seconds</strong> to avoid a recorded violation.</p>'
          +   '<div id="tabmon-countdown" style="font-size:52px; font-weight:bold; line-height:1;">' + thresholdSec + '</div>'
          + '</div>';
        document.body.appendChild(overlay);

        var modal = document.createElement('div');
        modal.id = 'tabmon-modal';
        modal.style.cssText = [
            'display:none', 'position:fixed', 'inset:0', 'z-index:9999',
            'background:rgba(0,0,0,0.75)',
            'align-items:center', 'justify-content:center', 'padding:20px',
            'font-family:Arial, Helvetica, sans-serif',
        ].join(';');
        modal.innerHTML = ''
          + '<div style="background:white; color:#1a1a2e; padding:28px 32px;'
          + ' border-radius:10px; max-width:480px; text-align:center;">'
          +   '<p id="tabmon-modal-text" style="font-size:15px; line-height:1.55; margin:0 0 18px 0;"></p>'
          +   '<button id="tabmon-modal-btn" style="padding:10px 26px; background:#1a1a2e;'
          +     ' color:white; border:none; border-radius:4px; font-size:15px; cursor:pointer;">'
          +     'Understood — continue</button>'
          + '</div>';
        document.body.appendChild(modal);

        document.getElementById('tabmon-modal-btn').addEventListener('click', function () {
            modal.style.display = 'none';
            window._tabmonModalOpen = false;
        });
    }

    function startTabMonitor() {
        if (inUnmonitoredSection()) {
            try { sessionStorage.removeItem('aiSafetyAgreed'); } catch (e) {}
            return;
        }
        if (!aiSafetyArmed() || window._tabmonStarted) return;
        window._tabmonStarted = true;
        buildTabMonitorDom();

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
            if (overlayVisible || isNavigatingAway) return;
            overlayVisible = true;
            overlay.style.display = 'flex';
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
            if (!overlayVisible) return;
            overlayVisible = false;
            overlay.style.display = 'none';
            if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null; }
        }

        function showModal(text) {
            window._tabmonModalOpen = true;
            modalText.textContent = text;
            modal.style.display = 'flex';
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
            if (count < AI_SAFETY.MAX_VIOLATIONS) {
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

        overlay.addEventListener('click', function () { cancelLeaveTimer(); });
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
