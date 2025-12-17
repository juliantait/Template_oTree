document.addEventListener('DOMContentLoaded', () => {
    const allBlocks = Array.from(document.querySelectorAll('.instruction-block'));
    const instructionBlocks = allBlocks.filter(
        (block) => !block.classList.contains('prequiz-block')
    );
    const prequizBlock = allBlocks.find((block) =>
        block.classList.contains('prequiz-block')
    );
    const blocks = prequizBlock ? instructionBlocks.concat(prequizBlock) : instructionBlocks;

    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const counter = document.getElementById('instruction-counter');
    const form = nextBtn ? nextBtn.closest('form') || document.querySelector('form') : null;
    const wrapper = document.getElementById('instruction-wrapper');

    if (!blocks.length || !prevBtn || !nextBtn) {
        return;
    }

    let current = 0;
    const sectionState = {
        current: 'instructions',
    };

    const scrollToTop = () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // Fix container height so controls don't jump when the pre-quiz block shows.
    if (wrapper && blocks.length) {
        let maxHeight = 0;
        blocks.forEach((block) => {
            const previousDisplay = block.style.display;
            block.style.display = 'block';
            const h = block.scrollHeight;
            maxHeight = Math.max(maxHeight, h);
            block.style.display = previousDisplay;
        });
        const min33vh = Math.floor(window.innerHeight * 0.33);
        const targetHeight = Math.max(maxHeight, min33vh);
        wrapper.style.minHeight = `${targetHeight}px`;
    }

    const setPrevDisabled = (shouldDisable) => {
        prevBtn.disabled = shouldDisable;
        if (shouldDisable) {
            prevBtn.setAttribute('aria-disabled', 'true');
        } else {
            prevBtn.removeAttribute('aria-disabled');
        }
    };

    const isAtPrequiz = () => prequizBlock && blocks[current] === prequizBlock;

    const goPrev = () => {
        if (current === 0) return;
        current -= 1;
        updateView();
        scrollToTop();
    };

    const goNext = () => {
        if (current < blocks.length - 1) {
            current += 1;
            updateView();
            scrollToTop();
        }
    };

    const submitForm = () => {
        if (form) {
            form.submit();
        }
    };

    const updateView = () => {
        blocks.forEach((block, idx) => {
            block.style.display = idx === current ? 'block' : 'none';
        });

        const atFirst = current === 0;
        const atPrequiz = isAtPrequiz();

        sectionState.current = atPrequiz ? 'prequiz' : 'instructions';

        // Disable Back only on the very first instruction, never on prequiz screen.
        setPrevDisabled(atFirst && !atPrequiz);

        prevBtn.style.display = 'inline-block';
        nextBtn.style.display = 'inline-block';

        if (atPrequiz) {
            prevBtn.textContent = 'Re-read instructions';
            nextBtn.textContent = 'Go to quiz';
            nextBtn.dataset.action = 'submit';

            if (counter) {
                counter.textContent = '';
                counter.style.visibility = 'hidden';
            }
        } else {
            prevBtn.textContent = 'Back';
            nextBtn.textContent = 'Next';
            nextBtn.dataset.action = 'next';

            if (counter) {
                const total = instructionBlocks.length || 1;
                const currentNumber = Math.min(current + 1, total);
                counter.textContent = `Instruction ${currentNumber} of ${total}`;
                counter.style.visibility = 'visible';
            }
        }
    };

    prevBtn.addEventListener('click', () => {
        if (isAtPrequiz()) {
            current = 0;
            updateView();
            scrollToTop();
            return;
        }
        goPrev();
    });

    nextBtn.addEventListener('click', () => {
        if (isAtPrequiz()) {
            submitForm();
            return;
        }
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
            if (isAtPrequiz()) {
                prevBtn.click();
            } else {
                goPrev();
            }
        } else {
            if (isAtPrequiz()) {
                nextBtn.click();
            } else {
                goNext();
            }
        }
    });

    updateView();
});
