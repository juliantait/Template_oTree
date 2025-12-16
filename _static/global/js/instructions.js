document.addEventListener('DOMContentLoaded', () => {
    const blocks = Array.from(document.querySelectorAll('.instruction-block'));
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const counter = document.getElementById('instruction-counter');
    const form = nextBtn ? nextBtn.closest('form') || document.querySelector('form') : null;

    if (!blocks.length || !prevBtn || !nextBtn) {
        return;
    }

    let current = 0;

    const updateView = () => {
        blocks.forEach((block, idx) => {
            block.style.display = idx === current ? 'block' : 'none';
        });

        const atFirst = current === 0;
        const atLast = current === blocks.length - 1;

        prevBtn.disabled = atFirst;
        prevBtn.classList.toggle('disabled', atFirst);

        nextBtn.textContent = atLast ? 'Go to quiz' : 'Next';
        nextBtn.dataset.action = atLast ? 'submit' : 'next';

        if (counter) {
            counter.textContent = `Instruction ${current + 1} of ${blocks.length}`;
        }
    };

    prevBtn.addEventListener('click', () => {
        if (current > 0) {
            current -= 1;
            updateView();
        }
    });

    nextBtn.addEventListener('click', () => {
        if (nextBtn.dataset.action === 'submit') {
            if (form) {
                form.submit();
            }
            return;
        }
        if (current < blocks.length - 1) {
            current += 1;
            updateView();
        }
    });

    updateView();
});
