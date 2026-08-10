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