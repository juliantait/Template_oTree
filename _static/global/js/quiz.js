(function initQuizSolutions() {
    if (!window.quizSolutions) {
        var el = document.getElementById('quiz-solutions-data');
        if (el && el.textContent) {
            try {
                window.quizSolutions = JSON.parse(el.textContent);
            } catch (e) {
                window.quizSolutions = [];
            }
        } else {
            window.quizSolutions = [];
        }
    }
})();

// Both auto-fill paths below go through global.js's submitFormBehindVeil, which
// paints the shared `.submit-veil` in the SAME synchronous task as the fill, so
// the participant never sees radios flicking to the answers during navigation.
// There is deliberately no second implementation of that trick here — a local
// copy is how the flash bug came back last time.
//
// Both callers are onclick handlers on <input type="submit">, so the form
// submits natively straight after the handler returns; the helper is called
// WITHOUT a form argument so it does not also submit (which would double-submit).

// Testing-only helper: the button that calls this is only rendered under
// settings.DEBUG, and window.quizSolutions is only populated then.
function skipQuiz() {
    submitFormBehindVeil(null, function () {
        if (Array.isArray(window.quizSolutions)) {
            setFormValues(window.quizSolutions);
        }
        setValue('redoinstructions', 0);
    });
}

// Quiz-failure modal (lab re-read / experimenter notice). The server decides
// WHICH modal is in the page (or none); this only reveals and dismisses it.
// Wrapped so a JS failure can never break the page — the quiz itself works
// without the modal.
(function initQuizModal() {
    try {
        var backdrop = document.getElementById('quiz-modal-backdrop');
        if (!backdrop) return;
        backdrop.hidden = false;
        var primary = backdrop.querySelector('.modal-actions .next-button');
        if (primary) primary.focus();
    } catch (e) { /* never block the quiz */ }
})();

function dismissQuizModal() {
    try {
        var backdrop = document.getElementById('quiz-modal-backdrop');
        if (backdrop) backdrop.hidden = true;
    } catch (e) { /* never block the quiz */ }
}

function redoInstructions() {
    submitFormBehindVeil(null, function () {
        if (Array.isArray(window.quizSolutions)) {
            setFormValues(window.quizSolutions);
        }
        setValue('redoinstructions', 1);
    });
}

// --- the at-will re-read dialog (ONLINE ONLY; see quiz.vars_for_template) ----
// The server decides whether the dialog is in the page at all; this only opens
// and closes it. Everything is wrapped so a JS failure can never break the quiz:
// with the script blocked the dialog simply never opens and the quiz still
// works (the same progressive-enhancement rule as the scroll fade).
//
// WHILE THE DIALOG IS OPEN EVERY SUBMIT CONTROL IS DISABLED. That is not
// decoration: global.js binds Enter to the first enabled forward control on the
// page, so without this an Enter meant to dismiss the dialog would submit the
// quiz from behind it. Disabling them makes global.js's handler find nothing,
// and the handler below then closes the dialog instead.
function _rereadSetSubmitsDisabled(state) {
    // ONE implementation, in global.js (which every page loads before this
    // file). The fallback exists only so this file cannot break if that load
    // order is ever changed.
    if (typeof setForwardControlsDisabled === 'function') {
        setForwardControlsDisabled(state);
        return;
    }
    var els = document.querySelectorAll(
        '.screen-card input[type="submit"], .screen-card button.next-button');
    for (var i = 0; i < els.length; i++) { els[i].disabled = !!state; }
}

function openReread() {
    try {
        var backdrop = document.getElementById('reread-backdrop');
        if (!backdrop) return;
        backdrop.dataset.returnFocus = 'rereadOpen';
        backdrop.hidden = false;
        _rereadSetSubmitsDisabled(true);
        var close = document.getElementById('rereadClose');
        if (close) close.focus();
        var body = document.getElementById('reread-body');
        if (body) body.scrollTop = 0;
    } catch (e) { /* never block the quiz */ }
}

function closeReread() {
    try {
        var backdrop = document.getElementById('reread-backdrop');
        if (!backdrop) return;
        backdrop.hidden = true;
        _rereadSetSubmitsDisabled(false);
        var back = document.getElementById(backdrop.dataset.returnFocus || '');
        if (back) back.focus();
    } catch (e) { /* never block the quiz */ }
}

(function initReread() {
    try {
        var backdrop = document.getElementById('reread-backdrop');
        var openBtn = document.getElementById('rereadOpen');
        if (!backdrop || !openBtn) return;
        openBtn.addEventListener('click', openReread);
        var close = document.getElementById('rereadClose');
        if (close) close.addEventListener('click', closeReread);
        // A click on the dimmed backdrop itself (not on the card) closes it.
        backdrop.addEventListener('click', function (event) {
            if (event.target === backdrop) { closeReread(); }
        });
        document.addEventListener('keydown', function (event) {
            if (backdrop.hidden) { return; }
            if (event.key === 'Escape' || event.key === 'Enter') {
                event.preventDefault();
                closeReread();
            }
        });
    } catch (e) { /* never block the quiz */ }
})();

function setFormValues(solutions) {
    solutions.forEach(function (item) {
        if (!item || !item.name) return;
        var inputs = document.querySelectorAll('input[name="' + item.name + '"]');
        inputs.forEach(function (input) {
            if (String(input.value) === String(item.value)) {
                input.checked = true;
            }
        });
    });
}