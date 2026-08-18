//GLOBAL
    // (The cookie helpers that used to open this file are gone — Julian,
    // 2026-08-13: clearAllCookies, which the payoff/Ended/Results pages called
    // on load, is no longer needed and was removed along with its call sites;
    // the other cookie helpers had already been removed by an earlier review.)

    // Helper to set hidden form values
    function setValue(id, val) {
        const el = document.getElementById(id);
        if (el) {
            el.value = val;
        }
    }

    // Paint the shared `.submit-veil` (base.css) over the whole page. Used
    // whenever a script has to TOUCH FORM CONTROLS before submitting — the
    // DEBUG skip-quiz fill, the re-read route-back, and anything similar added
    // later.
    //
    // WHY: the browser keeps the CURRENT page visible for the whole navigation
    // round-trip, so controls set just before submit are on screen for a
    // moment — the participant sees radios flicking to the answers. Painting the
    // veil in the SAME synchronous task as the fill means no intermediate frame
    // is ever rendered: the veil is all that shows.
    //
    // Use `submitFormBehindVeil` below rather than calling this directly.
    function showSubmitVeil(label) {
        if (document.querySelector('.submit-veil')) { return; }
        const veil = document.createElement('div');
        veil.className = 'submit-veil';
        veil.textContent = label || 'One moment…';
        document.body.appendChild(veil);
    }

    // Fill a form and submit it without the participant seeing the controls
    // change. `fill` runs behind the veil, in the same task, then the form is
    // submitted.
    //
    // Pass a form to have it submitted here. Omit it when the caller is already
    // a submit control (an onclick on <input type="submit">, which submits
    // natively straight after the handler) — the veil still goes up first.
    function submitFormBehindVeil(form, fill) {
        showSubmitVeil();
        if (typeof fill === 'function') { fill(); }
        // ⚠ form.submit() DOES NOT FIRE SUBMIT EVENT LISTENERS. Anything doing
        // real work in a 'submit' handler is skipped, silently, with no error:
        //   * tab_monitor.js's markNavigatingAway — the flag that stops a
        //     navigation being counted as a tab-monitor violation (it is also
        //     set by beforeunload/pagehide, so today that one is covered twice);
        //   * main/game.html's client_ms timing listener, which fills its hidden
        //     field ON SUBMIT — bypassed, it posts empty and the telemetry is
        //     just missing for that participant.
        // If a listener MUST run, use form.requestSubmit(), which fires them.
        //
        // WHY THIS IS A WARNING AND NOT A BUG TODAY: both current callers
        // (quiz.js) pass `form` as null and let the submit control fire
        // natively, so this line is unreached. That is a property of the CALL
        // SITES, not of this helper — pass a real form and the two listeners
        // above stop firing for that page, with nothing to tell you.
        if (form) { form.submit(); }
    }

    // Run `fn` once the page's own markup exists. NOT OPTIONAL, even though
    // every template now links this file at the foot of the body (normalised
    // 2026-08-13; it used to sit at the TOP on the instructions and results
    // pages, where anything querying the card at script time silently found
    // nothing — the scroll affordance below was dead on the instructions page
    // for exactly this reason). Deferring keeps the file position-independent,
    // so the next template that links it somewhere else cannot resurrect that
    // bug. Do not remove as a pointless delay.
    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    // Enable/disable every forward control on the card in one call. Used
    // whenever a modal is open: the Enter handler below binds to the first
    // ENABLED forward control, so without this an Enter meant for the dialog
    // would submit the page from behind it. One implementation, shared by the
    // warning modal here and the quiz's re-read dialog (quiz.js).
    function setForwardControlsDisabled(state) {
        try {
            var els = document.querySelectorAll(
                '.screen-card input[type="submit"], .screen-card button.next-button');
            for (var i = 0; i < els.length; i++) { els[i].disabled = !!state; }
        } catch (e) { /* never block a page */ }
    }

    // --- WARNING MODAL (shared) ---------------------------------------------
    // ALL WARNINGS ARE CENTRED, SCREEN-DIMMING MODALS, never a banner that
    // pushes the page down under the participant. oTree renders a validation
    // failure as `.otree-form-errors` ABOVE the card; this takes that text,
    // hides the banner and shows the same words in the shared warning-modal
    // chrome (base.css). It is generic on purpose — consent, demographics, the
    // quiz and any page a study adds get the behaviour with no page code.
    //
    // PROGRESSIVE ENHANCEMENT, exactly like the scroll fade: with scripts
    // blocked the banner simply stays visible and the page still works. The
    // whole block is wrapped so instrumentation can never break a page.
    //
    // A page that ships its OWN warning modal marks it `data-warning-modal`
    // (the lab's quiz-failure dialogs do). Then the banner is still hidden —
    // nothing may push the page down — but this helper stays silent and lets
    // that better-worded dialog speak, rather than stacking two modals.
    //
    // The text is inserted with textContent, NEVER innerHTML: framework and
    // field-derived strings are not trusted markup (the escaping rule).
    onReady(function initWarningModal() {
        try {
            var banner = document.querySelector('.otree-form-errors');
            if (!banner) { return; }
            var message = (banner.textContent || '').trim();
            if (!message) { return; }

            banner.hidden = true;
            banner.style.display = 'none';
            if (document.querySelector('[data-warning-modal]')) { return; }

            var backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop popup popup--modal';  // tier 2
            backdrop.id = 'warning-modal-backdrop';

            var card = document.createElement('div');
            card.className = 'modal-card modal-card--warning';
            card.setAttribute('role', 'alertdialog');
            card.setAttribute('aria-modal', 'true');
            card.setAttribute('aria-labelledby', 'warning-modal-title');
            card.setAttribute('aria-describedby', 'warning-modal-text');

            var title = document.createElement('h3');
            title.className = 'modal-title';
            title.id = 'warning-modal-title';
            title.textContent = 'Please check your answers';

            var text = document.createElement('p');
            text.className = 'modal-text';
            text.id = 'warning-modal-text';
            text.textContent = message;

            var actions = document.createElement('div');
            actions.className = 'modal-actions';

            var ok = document.createElement('button');
            ok.type = 'button';
            ok.className = 'modal-ok-button';
            ok.textContent = 'OK';

            var releaseTrap = null;
            function close() {
                backdrop.hidden = true;
                if (releaseTrap) { try { releaseTrap(); } catch (e) {} releaseTrap = null; }
                setForwardControlsDisabled(false);
                var first = document.querySelector(
                    '.screen-card input:not([type="hidden"]), .screen-card select, '
                    + '.screen-card textarea');
                if (first) { try { first.focus(); } catch (e) {} }
            }

            ok.addEventListener('click', close);
            backdrop.addEventListener('click', function (event) {
                if (event.target === backdrop) { close(); }
            });
            document.addEventListener('keydown', function (event) {
                if (backdrop.hidden) { return; }
                if (event.key === 'Escape' || event.key === 'Enter') {
                    event.preventDefault();
                    close();
                }
            });

            actions.appendChild(ok);
            card.appendChild(title);
            card.appendChild(text);
            card.appendChild(actions);
            backdrop.appendChild(card);
            document.body.appendChild(backdrop);
            setForwardControlsDisabled(true);
            releaseTrap = popupTrapFocus(card);   // tier-2 focus trap (shared)
            ok.focus();
        } catch (e) { /* never block a page */ }
    });

    // Allow Enter key to activate the primary forward action (Next/Submit).
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') {
            return;
        }

        const targetTag = (event.target.tagName || '').toLowerCase();
        if (targetTag === 'textarea') {
            return; // keep multiline entry unaffected
        }

        // Prefer explicit next button if present (e.g., instructions flow).
        const nextButton =
            document.getElementById('nextBtn') ||
            document.querySelector('button.next-button:not([disabled])') ||
            document.querySelector('input.next-button[type="submit"]:not([disabled])') ||
            document.querySelector('.next-button:not([disabled])') ||
            document.querySelector('input[type="submit"]:not([disabled])');

        if (nextButton) {
            event.preventDefault();
            nextButton.click();
        }
    });
    // --- SCROLL AFFORDANCE (progressive enhancement) -------------------------
    // Marks every scroll region with `is-scrollable-up` / `is-scrollable-down`
    // so base.css can fade the CONTENT toward whichever edge still has more
    // behind it (a mask; a background can only paint behind the text, which is
    // why a clipped line used to look sliced rather than continued).
    //
    // This only ever ADDS: with the script blocked no class is ever set, no mask
    // applies, and the styled scrollbar plus the background shadows still say
    // the region scrolls. The whole block is wrapped so instrumentation can
    // never break a page (docs/conventions.md).
    onReady(function initScrollAffordance() {
        try {
            var EPS = 2;
            var regions = document.querySelectorAll(
                '.experimental-content, .instruction-wrapper');
            if (!regions.length) { return; }

            function sync(el) {
                var hidden = el.scrollHeight - el.clientHeight;
                el.classList.toggle('is-scrollable-up', el.scrollTop > EPS);
                el.classList.toggle('is-scrollable-down',
                    hidden > EPS && el.scrollTop < hidden - EPS);
            }

            function syncAll() {
                Array.prototype.forEach.call(regions, sync);
            }

            Array.prototype.forEach.call(regions, function (el) {
                sync(el);
                el.addEventListener('scroll', function () { sync(el); },
                                    { passive: true });
                // Content can change size after first paint (images, fonts, a
                // revealed instruction slide), which changes whether there is
                // anything to scroll to.
                if (window.ResizeObserver) {
                    var ro = new ResizeObserver(syncAll);
                    ro.observe(el);
                    Array.prototype.forEach.call(el.children, function (child) {
                        ro.observe(child);
                    });
                }
            });
            window.addEventListener('resize', syncAll);
            window.addEventListener('load', syncAll);
        } catch (e) { /* never block a page */ }
    });

    // --- SINGLE-PAGE FIT (Mode 2, progressive enhancement) ------------------
    // The consent welcome page and the tab-monitor agreement opt in by marking
    // their .screen-card with data-single-page. On a DESKTOP only, shrink the
    // card's body font within a narrow band — from the base scale down to
    // --single-page-font-floor — and let base.css's `.single-page-fit` tighten
    // the spacing, so all the content fits ONE viewport with no scroll. Pick the
    // LARGEST font at which it fits. If it fits at or above the floor: one centred
    // screen. If even the floor will not fit: GIVE UP and fall back to plain
    // Mode 1 whole-window scroll (the safe default).
    //
    // This only ever ENHANCES: with the script blocked no class is added and the
    // page is plain Mode 1; on a phone it never runs (phones are always Mode 1).
    // The whole block is wrapped so instrumentation can never break a page. The
    // decision controls are NEVER pinned — this touches font/spacing only, never
    // the layout order, so accept/decline/acknowledge stay after the content.
    onReady(function initSinglePageFit() {
        try {
            var card = document.querySelector('.screen-card[data-single-page]');
            if (!card) { return; }
            var PHONE = 520;         // matches base.css's phone breakpoint
            var STEP = 0.5;          // px granularity of the font search

            function clearFit() {
                card.classList.remove('single-page-fit');
                card.style.removeProperty('--single-page-font');
            }
            // The whole document must sit inside the viewport with no scroll.
            function fits() {
                return document.documentElement.scrollHeight
                    <= window.innerHeight + 1;
            }
            function floorPx() {
                var f = parseFloat(getComputedStyle(card)
                    .getPropertyValue('--single-page-font-floor'));
                return f > 0 ? f : 15;
            }

            function fit() {
                clearFit();
                // Phones are always Mode 1: single-page never applies.
                if (window.innerWidth <= PHONE) { return; }
                // The card's inherited body font, measured with no override.
                var base = parseFloat(getComputedStyle(card).fontSize) || 16;
                var floor = floorPx();
                if (base <= floor) { return; }   // no band to work within
                card.classList.add('single-page-fit');
                var chosen = null;
                for (var f = base; f >= floor - 0.001; f -= STEP) {
                    card.style.setProperty('--single-page-font',
                        f.toFixed(2) + 'px');
                    if (fits()) { chosen = f; break; }
                }
                // Even at the floor it does not fit -> give up, plain Mode 1.
                if (chosen === null) { clearFit(); }
            }

            fit();
            // Late layout shifts (web-safe font swap is none here, but logos and
            // a retracting URL bar both change height) and any viewport change
            // re-decide the fit; debounced so a drag does not thrash it.
            var t;
            function schedule() { clearTimeout(t); t = setTimeout(fit, 150); }
            window.addEventListener('resize', schedule);
            window.addEventListener('load', fit);
        } catch (e) { /* never block a page */ }
    });

    // --- POPUP LADDER (shared) ----------------------------------------------
    // The behaviour half of the four notification tiers catalogued in base.css
    // ("THE NOTIFICATION TIER LADDER"). ONE implementation, keyed off the
    // `popup--*` classes and `data-popup-*` attributes, so a study author writes
    // MARKUP ONLY and gets the tier's ARIA + keyboard + dismissal for free:
    //
    //   tier 0 anchored : <button data-popup-open="ID" aria-controls="ID">…</button>
    //                     <div id="ID" class="popup popup--anchored" role="dialog" hidden>…
    //   tier 1 toast    : <button data-popup-toast="ID">…</button>
    //                     <div id="ID" class="popup popup--toast" role="status"
    //                          aria-live="polite" hidden>…
    //   tier 2 modal    : <button data-popup-open="ID">…</button>
    //                     <div id="ID" class="popup popup--modal" role="alertdialog"
    //                          aria-modal="true" hidden>… <button data-popup-close>…
    //                     Add `popup--acknowledge` to the panel for button-only
    //                     dismissal (no Escape, no backdrop click).
    //   tier 3 takeover : opened programmatically or via data-popup-open; NEVER
    //                     give it a close control (that would make it a modal).
    //
    // PROGRESSIVE ENHANCEMENT, like every other block in this file: with scripts
    // blocked nothing opens and the page still works. Everything is wrapped so a
    // popup can never break a page (docs/conventions.md).
    //
    // The tiers 2/3 that already shipped (the warning modal above, the quiz
    // dialogs in quiz.js, the tab monitor) keep their own JS; this block does not
    // rewire them. It powers NEW popups and the specimens in template.html, and
    // shares its focus trap (popupTrapFocus) with them.

    function popupById(id) {
        try { return id ? document.getElementById(id) : null; } catch (e) { return null; }
    }
    function popupTierOf(el) {
        if (!el || !el.classList) { return null; }
        if (el.classList.contains('popup--anchored')) { return 'anchored'; }
        if (el.classList.contains('popup--toast')) { return 'toast'; }
        if (el.classList.contains('popup--modal')) { return 'modal'; }
        if (el.classList.contains('popup--takeover')) { return 'takeover'; }
        return null;
    }
    function popupFocusables(container) {
        var sel = 'a[href], button:not([disabled]), '
            + 'input:not([disabled]):not([type="hidden"]), select:not([disabled]), '
            + 'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
        var out = [];
        try {
            var all = container.querySelectorAll(sel);
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                if (el.offsetWidth || el.offsetHeight || el.getClientRects().length) {
                    out.push(el);
                }
            }
        } catch (e) { /* return what we have */ }
        return out;
    }

    // Shared tier-2/3 focus trap. Keeps Tab inside `container` while it is open,
    // and returns a release() the caller MUST call on close. Exposed at file
    // scope so quiz.js reuses this one implementation (like setForwardControlsDisabled).
    function popupTrapFocus(container) {
        function onKey(e) {
            if (e.key !== 'Tab' || !container) { return; }
            var f = popupFocusables(container);
            if (!f.length) { e.preventDefault(); return; }
            var first = f[0], last = f[f.length - 1];
            var active = document.activeElement;
            if (e.shiftKey && (active === first || !container.contains(active))) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && (active === last || !container.contains(active))) {
                e.preventDefault(); first.focus();
            }
        }
        document.addEventListener('keydown', onKey, true);
        return function release() {
            document.removeEventListener('keydown', onKey, true);
        };
    }
    window.popupTrapFocus = popupTrapFocus;

    // TIER 1 — show a toast and let it clear itself. Never dismissed by hand.
    function popupToast(idOrEl, ms) {
        try {
            var el = (typeof idOrEl === 'string') ? popupById(idOrEl) : idOrEl;
            if (!el) { return; }
            var timeout = ms;
            if (typeof timeout !== 'number') {
                timeout = parseInt(el.getAttribute('data-popup-timeout'), 10);
                if (!(timeout > 0)) { timeout = 4000; }  // the one allowed literal
            }
            el.hidden = false;
            // force a frame so the opacity transition runs from 0
            void el.offsetWidth;
            el.classList.add('is-visible');
            if (el._popupToastTimer) { clearTimeout(el._popupToastTimer); }
            el._popupToastTimer = setTimeout(function () {
                el.classList.remove('is-visible');
                el._popupToastTimer = setTimeout(function () { el.hidden = true; }, 200);
            }, timeout);
        } catch (e) { /* never block a page */ }
    }
    window.popupToast = popupToast;

    onReady(function initPopupLadder() {
        try {
            // TIER 0 — anchored panels. A trigger toggles its panel; an outside
            // click or Escape closes it; focus moves into the panel on open and
            // back to the trigger on close. Non-modal: no focus trap, no page lock.
            var anchoredTriggers = document.querySelectorAll(
                '[data-popup-open]');
            Array.prototype.forEach.call(anchoredTriggers, function (trigger) {
                var panel = popupById(trigger.getAttribute('data-popup-open'));
                if (!panel) { return; }
                var tier = popupTierOf(panel);
                if (tier === 'anchored') { wireAnchored(trigger, panel); }
                else { wireModalTrigger(trigger, panel); }  // modal / takeover
            });

            // TIER 1 — toast triggers.
            var toastTriggers = document.querySelectorAll('[data-popup-toast]');
            Array.prototype.forEach.call(toastTriggers, function (trigger) {
                trigger.addEventListener('click', function () {
                    popupToast(trigger.getAttribute('data-popup-toast'));
                });
            });
        } catch (e) { /* never block a page */ }
    });

    function wireAnchored(trigger, panel) {
        function isOpen() { return !panel.hidden; }
        function open() {
            panel.hidden = false;
            trigger.setAttribute('aria-expanded', 'true');
            var f = popupFocusables(panel);
            try { (f[0] || panel).focus(); } catch (e) {}
        }
        function close(returnFocus) {
            panel.hidden = true;
            trigger.setAttribute('aria-expanded', 'false');
            if (returnFocus) { try { trigger.focus(); } catch (e) {} }
        }
        if (!panel.hasAttribute('tabindex')) { panel.setAttribute('tabindex', '-1'); }
        trigger.setAttribute('aria-expanded', 'false');
        trigger.addEventListener('click', function (e) {
            e.stopPropagation();   // don't let this click reach the outside-click handler
            if (isOpen()) { close(true); } else { open(); }
        });
        document.addEventListener('click', function (e) {
            if (!isOpen()) { return; }
            if (e.target === trigger || trigger.contains(e.target)
                || panel.contains(e.target)) { return; }
            close(false);
        });
        document.addEventListener('keydown', function (e) {
            if (!isOpen()) { return; }
            if (e.key === 'Escape' || e.key === 'Esc') { close(true); }
        });
    }

    // TIER 2 / 3 — generic modal/takeover open+close for NEW popups (and the
    // specimens). Escape and backdrop-click dismiss a modal BY DEFAULT; a modal
    // marked `popup--acknowledge`, and every takeover, are button-only (a takeover
    // should carry no close control at all — if it needs one it is a modal). A
    // `data-popup-close` control inside the panel always closes it.
    function wireModalTrigger(trigger, panel) {
        trigger.addEventListener('click', function () { openPopupModal(panel, trigger); });
    }
    function openPopupModal(panel, opener) {
        try {
            if (!panel.hidden) { return; }
            var tier = popupTierOf(panel);
            var acknowledge = panel.classList.contains('popup--acknowledge')
                || tier === 'takeover';
            panel._popupOpener = opener || document.activeElement;
            panel.hidden = false;
            setForwardControlsDisabled(true);
            panel._popupRelease = popupTrapFocus(panel);
            var f = popupFocusables(panel);
            try { (f[0] || panel).focus(); } catch (e) {}

            panel._popupOnKey = function (e) {
                if (panel.hidden) { return; }
                if ((e.key === 'Escape' || e.key === 'Esc') && !acknowledge) {
                    e.preventDefault();
                    closePopupModal(panel);
                }
            };
            document.addEventListener('keydown', panel._popupOnKey);

            panel._popupOnClick = function (e) {
                if (e.target === panel && !acknowledge) { closePopupModal(panel); }
            };
            panel.addEventListener('click', panel._popupOnClick);

            var closers = panel.querySelectorAll('[data-popup-close]');
            Array.prototype.forEach.call(closers, function (c) {
                if (c._popupCloseWired) { return; }
                c._popupCloseWired = true;
                c.addEventListener('click', function () { closePopupModal(panel); });
            });
        } catch (e) { /* never block a page */ }
    }
    function closePopupModal(panel) {
        try {
            panel.hidden = true;
            if (panel._popupRelease) { panel._popupRelease(); panel._popupRelease = null; }
            if (panel._popupOnKey) {
                document.removeEventListener('keydown', panel._popupOnKey);
                panel._popupOnKey = null;
            }
            if (panel._popupOnClick) {
                panel.removeEventListener('click', panel._popupOnClick);
                panel._popupOnClick = null;
            }
            setForwardControlsDisabled(false);
            var opener = panel._popupOpener;
            if (opener) { try { opener.focus(); } catch (e) {} }
        } catch (e) { /* never block a page */ }
    }
    window.openPopupModal = openPopupModal;
    window.closePopupModal = closePopupModal;
