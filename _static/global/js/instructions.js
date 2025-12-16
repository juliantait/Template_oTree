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

    const setPrevDisabled = (shouldDisable) => {
        prevBtn.disabled = shouldDisable;
        if (shouldDisable) {
            prevBtn.setAttribute('aria-disabled', 'true');
        } else {
            prevBtn.removeAttribute('aria-disabled');
        }
    };

    const goPrev = () => {
        if (current === 0) return;
        current -= 1;
        updateView();
    };

    const goNext = () => {
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
    };

    const updateView = () => {
        blocks.forEach((block, idx) => {
            block.style.display = idx === current ? 'block' : 'none';
        });

        const atFirst = current === 0;
        const atLast = current === blocks.length - 1;

        // Always grey out Back on the first block, whether initial load or after returning.
        setPrevDisabled(atFirst);

        nextBtn.textContent = atLast ? 'Go to quiz' : 'Next';
        nextBtn.dataset.action = atLast ? 'submit' : 'next';

        if (counter) {
            counter.textContent = `Instruction ${current + 1} of ${blocks.length}`;
        }
    };

    prevBtn.addEventListener('click', goPrev);

    nextBtn.addEventListener('click', () => {
        goNext();
    });

    document.addEventListener('keydown', (event) => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) {
            return;
        }

        const targetTag = (event.target.tagName || '').toLowerCase();
        if (['input', 'textarea', 'select', 'button'].includes(targetTag)) {
            return;
        }

        event.preventDefault();
        if (event.key === 'ArrowLeft') {
            goPrev();
        } else {
            goNext();
        }
    });

    updateView();
});
