/* DOT-BI visual bot gate — browser half (server half: before.DotBiGate +
   dot_bi.py). PROGRESSIVE ENHANCEMENT: the challenge needs JavaScript (to time
   the answer, to record that JS ran, and to enforce the answer field), so the
   page ships with the challenge HIDDEN and a no-JS fallback SHOWN (static CSS in
   base.css). This script's ONE structural job is to add `.dotbi-ready` to the
   wrapper, which flips them — reveal the challenge, hide the fallback.

   WHY THE "JS RAN" FLAG MATTERS. A participant whose script never ran submits
   #bot_dotbi_js empty; the server reads that as "no JavaScript" and routes them
   to the GENTLE no_javascript (-6) return, never a bot code. So this file MUST
   set the flag, and it must do so only when it actually runs.

   The answer input is NOT HTML-required in the markup — this script adds
   `required` — so a no-JS submit is never blocked by browser validation on a
   field it cannot see. A blank answer UNDER JS is re-prompted server-side
   (DotBiGate.error_message), a nudge, not an ejection.

   The whole body is wrapped: instrumentation must NEVER break the page
   (CLAUDE.md). The number is graded ONLY on the server; nothing here reads or
   knows the answer. */
(function () {
    'use strict';
    try {
        var wrap = document.querySelector('.dotbi-wrap');
        if (!wrap) { return; }          // not the DOT-BI page

        // Reveal the challenge / hide the fallback (the CSS is static; this just
        // toggles the class it keys on).
        wrap.classList.add('dotbi-ready');

        var jsEl = document.getElementById('bot_dotbi_js');
        var msEl = document.getElementById('bot_dotbi_ms');
        var answerEl = document.getElementById('bot_dotbi_answer');

        // Mark that JS ran — the whole point of the flag.
        if (jsEl) { jsEl.value = '1'; }

        // Enforce the answer only now that JS is present (see the header).
        if (answerEl) {
            try { answerEl.required = true; } catch (e) { /* non-fatal */ }
            try { answerEl.focus(); } catch (e) { /* non-fatal */ }
        }

        function now() {
            return (window.performance && performance.now)
                ? performance.now() : Date.now();
        }
        var start = now();

        function snapshot() {
            if (msEl) {
                try { msEl.value = (now() - start).toFixed(1); } catch (e) {}
            }
        }
        // Capture-phase submit listener, like focus_trace.js: writes the elapsed
        // ms onto the hidden carrier as the form leaves.
        document.addEventListener('submit', snapshot, true);
    } catch (e) { /* never let the visual check break the page */ }
})();
