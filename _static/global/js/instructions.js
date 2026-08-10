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

    // Return to the top of the slide when the step changes. The card is height-
    // capped and .instruction-wrapper is the element that scrolls (see
    // instructions.css), so scroll THAT — the window itself usually has nothing
    // to scroll now. The window call is kept as a harmless fallback for any page
    // that is taller than the viewport anyway.
    const scrollToTop = () => {
        if (wrapper) {
            wrapper.scrollTo({ top: 0, behavior: 'smooth' });
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

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

        // NB: this used to set wrapper.style.minHeight to the current slide's
        // scrollHeight, to stop the controls jumping between slides. Do NOT put
        // that back. The wrapper is now the card's scroll region, and an inline
        // min-height equal to the content height makes it impossible for the
        // region to shrink — it would never scroll and the card would overflow
        // its max-height instead. Constant control position is handled in CSS by
        // the flex fill (see .instruction-wrapper in instructions.css).

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
                counter.textContent = `Page ${currentNumber} of ${total}`;
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
