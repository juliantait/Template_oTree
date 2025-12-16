    // Start button commands
    function runstart() {
        // Show the task div and hide the start div
        document.getElementById(`startDiv`).style.display = 'none';
        document.getElementById(`taskDiv`).style.display = 'block';
    }

    function checkColor(selectedColor) {
        let correctColor = getTaskAttribute('correctAnswer');
        let correctColor2 = getTaskAttribute('correctAnswer2');
        const type = getTaskAttribute('taskType');
        
        if (type == 'doubleColor') {
            if (doubleNum == 1) {
                let mistakePartOne;
                if (selectedColor === correctColor) {
                    console.log("Correct!");
                    mistakePartOne = 0;
                } else {
                    console.log("Incorrect!");
                    mistakePartOne = 1;
                }
                console.log('mistake part one is: ' + mistakePartOne);
                
                // Store mistakePartOne for the second part
                localStorage.setItem('mistakePartOne', mistakePartOne);
                
            } else if (doubleNum == 2) {
                // Retrieve mistakePartOne from storage
                let mistakePartOne = parseInt(localStorage.getItem('mistakePartOne'));
                
                if (selectedColor == correctColor2 && mistakePartOne == 0) {
                    setValue('mistake_' + taskNumber, 0);
                    console.log("Correct!");
                } else if (selectedColor != correctColor2) {
                    setValue('mistake_' + taskNumber, 1);
                    console.log("Incorrect!");
                    recordMistake();
                } else if (selectedColor == correctColor2) {
                    setValue('mistake_' + taskNumber, 1);
                    console.log("Correct color, but there was a mistake in part one");
                    recordMistake();
                } else {
                    console.log("strange answer!");
                    setValue('mistake_' + taskNumber, 2);
                    recordMistake();
                }
                
                // Clear the stored value after use
                localStorage.removeItem('mistakePartOne');
            } else {
                console.log("bad 547");
            }
        } else {
            if (selectedColor === correctColor) {
                console.log("Correct!");
                setValue('mistake_' + taskNumber, 0);
            } else {
                console.log("Incorrect!");
                setValue('mistake_' + taskNumber, 1);
                recordMistake();
            }
        }
        nexttask();
    }

    function updateTextAndColor(i) {
        let startDivText, wordDivText, font, correctColor, distractionColor;
        let doubleTask = getTaskAttribute('taskType') === 'doubleColor' ? 1 : 0;
        if (i == 1) {
            font = getTaskAttribute('font');
            correctColor = getTaskAttribute('correctAnswer');
            distractionColor = getTaskAttribute('distraction');
        } else if (i == 2) {
            font = getTaskAttribute('font2');
            correctColor = getTaskAttribute('correctAnswer2');
            distractionColor = getTaskAttribute('distraction2');
        }
        startDivText = document.querySelector('#startDivText h3');
        endDivText = document.querySelector('#endDivText h3');
        wordDivText = document.querySelector('#wordDiv h1');
        
        // Update instruction text
        let font1 = getTaskAttribute('font');
        let font2 = getTaskAttribute('font2');
        let instructionsMessages = generateInstructions(font1, font2, doubleTask);
            if (doubleTask == 1) {
                const startDivMessage = 'For the first word <br> <b>' + instructionsMessages.part1 + '</b';
                const endDivMessage = 'For the second word <br> <b>' + instructionsMessages.part2 + '</b';
                
                // Use innerHTML to interpret the <br> tags
                startDivText.innerHTML = startDivMessage;
                endDivText.innerHTML = endDivMessage;
            } else {
                // For single tasks, we can still use textContent if there's no HTML
                startDivText.innerHTML = '<b>' + instructionsMessages.part1 + '</b';
                
                // Clear the endDivText if it exists
                if (endDivText) {
                    endDivText.textContent = '';
                }
            }

        // Function to get color name
        const getColorName = (color) => ww.colorDict[color] || 'UNKNOWN COLOR';

        // Update word and color
        if (font == 1) {
            wordDivText.style.color = correctColor;
            wordDivText.textContent = getColorName(distractionColor);
        } else {
            wordDivText.style.color = distractionColor;
            wordDivText.textContent = getColorName(correctColor);
        }

        // Generate color buttons
        generateColorButtons(i);
    }

    function generateInstructions(font1, font2,doubleTask) {
        let part1, part2
        if (doubleTask == 0){
            part1 = font1 === 1 ? 'Click the Font-Color' : 'Click the Spelled-Out Color';
            part2 = ''
        } else {
            part1 = font1 === 1 ? 'Click the Font-Color' : 'Click the Spelled-Out Color';
            part2 = font2 === 1 ? 'Click the Font-Color' : 'Click the Spelled-Out Color';
        }
        return {
            part1: part1,
            part2: part2
        };
    }

    function generateColorButtons(i) {
        // Parse colors if they're in string format
        let colors = ww.colors;
        if (typeof colors === 'string') {
            colors = colors.replace(/^\[|\]$/g, '').split(',')
                .map(color => color.trim().replace(/^'|'$/g, ''));
        }
    
        if (!Array.isArray(colors)) {
            console.error("Error: colors is not an array after parsing");
            return;
        }
    
        // Get task attributes
        let correctColor,distractionColor,colorNumbers
        if (i == 1) {
            colorNumbers = parseInt(getTaskAttribute('buttons'));
            correctColor = getTaskAttribute('correctAnswer');
            distractionColor = getTaskAttribute('distraction');
        } else if (i == 2) {
            colorNumbers = parseInt(getTaskAttribute('buttons2'));
            correctColor = getTaskAttribute('correctAnswer2');
            distractionColor = getTaskAttribute('distraction2');
        }
        // Filter and select colors
        const availableColors = colors.filter(color => color !== correctColor && color !== distractionColor);
        if (availableColors.length < colorNumbers - 2) {
            console.error("Error: Not enough available colors");
            return;
        }
    
        const randomColors = availableColors
            .sort(() => 0.5 - Math.random())
            .slice(0, colorNumbers - 2);
    
        // Combine and shuffle colors
        let selectedColors = [correctColor, distractionColor, ...randomColors]
            .sort(() => 0.5 - Math.random());
    
        // Generate and append buttons
        let buttonContainer
        buttonContainer = document.getElementById('colorButtons');
        if (!buttonContainer) {
            console.error("Error: Button container not found");
            return;
        }
        buttonContainer.innerHTML = '';
    
        selectedColors.forEach(color => {
            const button = document.createElement('button');
            button.style.backgroundColor = color;
            button.onclick = () => checkColor(color);
            button.type = "button";
            button.style.cssText = `width: 50px; height: 50px; margin: 5px; background-color: ${color};`;
            buttonContainer.appendChild(button);
        });
    
        // Ensure exactly colorNumbers buttons are visible
        const allButtons = buttonContainer.querySelectorAll('button');
        const buttonsToHide = allButtons.length - colorNumbers;
        const shuffledButtons = Array.from(allButtons).sort(() => 0.5 - Math.random());
    
        shuffledButtons.slice(0, buttonsToHide).forEach(button => {
            if (button.style.backgroundColor !== correctColor && 
                button.style.backgroundColor !== distractionColor) {
                button.style.display = 'none';
            }
        });
    
        // console.log("Button generation complete. Total buttons:", allButtons.length, "Visible buttons:", colorNumbers);
    }