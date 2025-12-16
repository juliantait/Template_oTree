// Generate the table content and fill it
function loadTable() {  
        // Console log the entire taskList
        console.log("Task List:", taskList);

        function getColorName(color) {
            return colorNames[color] || 'UNKNOWN COLOUR';
        }

        function createWordDisplay(correctColor, distractionColor, font) {
            var wordColor = font === 1 ? correctColor : distractionColor;
            var textColor = font === 1 ? distractionColor : correctColor;
            var displayWord = getColorName(textColor);
            var fontDescription = font === 1 ? 'Font Colour' : 'Spelled-out Colour';

            return '<div class="word-display">' +
                   '<span class="font-description">Click the <span>' + fontDescription + '</span></span>' +
                   '<div class="word-and-box">' +
                   '<span style="color: ' + wordColor + ';">' + displayWord + '</span>' +
                   '<span class="color-box" style="background-color: ' + correctColor + '"></span>' +
                   '</div>' +
                   '</div>';
        }

        taskList.forEach(function(task, index) {
            var row = $('<tr>');
            var content = '';

            content += '<td class="task-type">Task ' + (index + 1) + '</td>';
            content += '<td class="solution">';

            if (task.taskType === 'sum' || task.taskType === 'multiply') {
                var operation = task.taskType === 'sum' ? 'Sum' : 'Multiply';
                content += operation + ' ' + task.x + ' and ' + task.y + ' = ';
                content += '<span class="correct-answer">' + task.correctAnswer + '</span>';
            } else if (task.taskType === 'doubleColor') {
                content += '<div class="colour-words">';
                content += createWordDisplay(task.correctAnswer, task.distraction, task.font);
                content += createWordDisplay(task.correctAnswer2, task.distraction2, task.font2);
                content += '</div>';
            } else if (task.taskType === 'color') {
                content += '<div class="colour-words">';
                content += createWordDisplay(task.correctAnswer, task.distraction, task.font);
                content += '</div>';
            }

            content += '</td>';
            row.html(content);
            table.append(row);
        });
    // }
    }

function startSolutionCountdown(){
        var bigtime = ww.timerTime;
        setTimeout(function() {
                document.getElementById('tasking').style.display = 'none';
                document.getElementById('timeup').style.display = 'block';
        }, bigtime * 1000); // Convert seconds to milliseconds
    }
    
