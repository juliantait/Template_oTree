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

function redoInstructions() {
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