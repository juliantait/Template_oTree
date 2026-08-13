/* The results page's payout-table disclosure (outro/Results.html).
 *
 * ENHANCEMENT ONLY. Nothing on the way out of the study depends on JavaScript:
 * the "Back to Prolific" control is a plain link (see the ending footer
 * include), and with scripts off the table simply keeps its server-rendered
 * initial state (open in the lab, collapsed online — Results.vars_for_template
 * sets aria-expanded, the caret's .open class and the wrapper's .is-hidden from
 * the one `results_open` value). This file only lets the participant flip that
 * state; all three descriptions of it are driven together here exactly as they
 * are server-side, so a screen reader is never told the opposite of what is on
 * screen.
 *
 * addEventListener, never a window.onload assignment: the page loads more than
 * one script and an onload= would silently clobber the other's handler.
 */
(function () {
    'use strict';

    window.addEventListener('load', function () {
        var toggle = document.getElementById('results-toggle');
        var wrapper = document.getElementById('results-table-wrapper');
        var arrow = document.getElementById('results-arrow');

        if (!toggle || !wrapper) return;

        function handleToggle() {
            var nowHidden = wrapper.classList.toggle('is-hidden');
            toggle.setAttribute('aria-expanded', (!nowHidden).toString());
            if (arrow) {
                arrow.classList.toggle('open', !nowHidden);
            }
        }

        toggle.addEventListener('click', handleToggle);
        toggle.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleToggle();
            }
        });
    });
})();
