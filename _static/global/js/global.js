//GLOBAL
    // Function to log to console
    function cl(print) {
      console.log(print)
    }

    // COOKIES
      // Function to get the value of a cookie by name
    function getCookie(name) {
      let cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
          let cookie = cookies[i].trim();
          if (cookie.indexOf(name + '=') === 0) {
              return cookie.substring(name.length + 1);
          }
      }
      return null;
    }

    // Function to set a cookie
    function setCookie(name, value, minutes) {
        let expires = "";
        if (minutes) {
            let date = new Date();
            date.setTime(date.getTime() + (minutes * 60 * 1000));
            expires = "; expires=" + date.toUTCString();
        }
        document.cookie = name + "=" + value + expires + "; path=/";
    }

    // Function to get the value of all cookies
    function printCookies() {
        let cookies = document.cookie;
        console.log("Cookies: ", cookies); // Prints cookies in browser console
    }

    // Function to clear all cookies
    function clearAllCookies() {
        // Get all cookies
        const cookies = document.cookie.split(";");

        // Iterate over the cookies and set each one to expire
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i];
            const equalPos = cookie.indexOf("=");
            const name = equalPos > -1 ? cookie.substr(0, equalPos) : cookie;
            // Set the cookie to expire in the past
            document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
        }
    }

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
        if (form) { form.submit(); }
    }

    // Run `fn` once the page's own markup exists. NOT OPTIONAL: this file is
    // linked at DIFFERENT POINTS in different templates — at the END of the
    // body on the consent and quiz pages, but at the TOP on the instructions
    // and results pages, before their card is parsed. Anything that queries the
    // card at script time therefore silently found nothing on those pages (the
    // scroll affordance below was dead on the instructions page for exactly
    // this reason). Deferring costs nothing and makes the file
    // position-independent.
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
            backdrop.className = 'modal-backdrop';
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

            function close() {
                backdrop.hidden = true;
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
    // never break a page (conventions.md).
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
