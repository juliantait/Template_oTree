/* Behaviour for the SLIDER ELICITATION component (_static/global/css/slider.css,
   markup in main/game.html and the specimen in
   _static/global/html/template.html).

   ONE implementation, wiring EVERY `.slider-elicit` on the page by the ids/
   classes each widget defines within its own root, so a page may carry more
   than one. It is behaviour only: it records nothing and knows nothing about
   the study — it just manages the readout, the no-starting-value rule, and how
   an untouched slider posts EMPTY.

   PROGRESSIVE ENHANCEMENT, LOAD-BEARING. The server renders a plain, fully
   usable named range with NO `value` attribute. THIS FILE is what turns it into
   a no-starting-value control:
     * on load it adds `.is-unset` (the stylesheet hides the thumb) and shows
       the em-dash readout — so nothing reads as a pre-made answer;
     * on the first move it removes `.is-unset` and shows the live value;
     * on submit, if the slider was never moved, it STRIPS THE NAME so the field
       posts empty (a range with no value attribute otherwise posts the midpoint
       of min..max — a value nobody chose). The name is restored on the next
       tick, so a cancelled or failed submit leaves a working control behind.
   A participant whose scripts never run therefore meets an ordinary range with
   a visible thumb, and the SERVER stores whatever it posts (the field is
   blank=True / field_maybe_none) — never a 500. Never move the locking into the
   template: it must degrade to the plain control.

   Wrapped end to end: instrumentation and enhancement must never break a page
   (CLAUDE.md). */
(function () {
    function initOne(root) {
        try {
            var slider = root.querySelector('input[type="range"]');
            if (!slider) { return; }
            var valueEl = root.querySelector('.slider-value');
            var UNSET = root.getAttribute('data-unset-display') || '—';
            var NAME = slider.getAttribute('name') || '';

            // touched = the participant has moved the slider at least once. Until
            // then there is no chosen value: the thumb is hidden and the readout
            // is the em-dash.
            var touched = false;

            function showUnset() {
                root.classList.add('is-unset');
                if (valueEl) { valueEl.textContent = UNSET; }
                slider.setAttribute('aria-valuetext', 'No value set yet');
            }
            function showValue() {
                root.classList.remove('is-unset');
                if (valueEl) { valueEl.textContent = String(slider.value); }
                slider.setAttribute('aria-valuetext', String(slider.value));
            }

            showUnset();

            slider.addEventListener('input', function () {
                touched = true;
                showValue();
            });

            // STRIP THE NAME so an untouched slider posts nothing. The form is
            // serialised AFTER submit listeners run, so removing the name here
            // makes this field carry no value; error-tolerant server code then
            // stores it as empty (field_maybe_none). Restored next tick so a
            // submit that does not navigate leaves the control usable.
            function onSubmit() {
                if (!touched && NAME) {
                    slider.removeAttribute('name');
                    setTimeout(function () { slider.setAttribute('name', NAME); }, 0);
                }
            }
            var form = document.getElementById('form') || document.querySelector('form');
            if (form) { form.addEventListener('submit', onSubmit); }
        } catch (e) { /* never let the enhancement break the page */ }
    }

    function init() {
        try {
            var roots = document.querySelectorAll('.slider-elicit');
            for (var i = 0; i < roots.length; i++) { initOne(roots[i]); }
        } catch (e) { /* never let the enhancement break the page */ }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    // Exposed in case a page swaps a widget in after load.
    window.initSliderElicit = init;
})();
