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

// Paint an opaque full-page overlay so the participant never sees the radio
// buttons being programmatically checked before the form submits and
// navigates away. The overlay covers the same synchronous frame in which the
// inputs are filled, so the checked state never becomes visible.
function showTransitionOverlay() {
    if (document.getElementById('quiz-transition-overlay')) return;
    var overlay = document.createElement('div');
    overlay.id = 'quiz-transition-overlay';
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.zIndex = '2147483647';
    overlay.style.background = '#ffffff';
    document.body.appendChild(overlay);
}

// Testing-only helper: the button that calls this is only rendered under
// settings.DEBUG, and window.quizSolutions is only populated then.
function skipQuiz() {
    showTransitionOverlay();
    if (Array.isArray(window.quizSolutions)) {
        setFormValues(window.quizSolutions);
    }
    setValue('redoinstructions', 0);
}

function redoInstructions() {
    showTransitionOverlay();
    if (Array.isArray(window.quizSolutions)) {
        setFormValues(window.quizSolutions);
    }
    setValue('redoinstructions', 1);
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