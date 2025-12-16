    // CHECK MATHEMATICS
    function checkmath(){

        let ans = parseInt(document.getElementById('answer_input').value);
        let correct = getTaskAttribute('correctAnswer')
        if (ans == correct){
            setValue('mistake_' + taskNumber,0);
            console.log("NO mistake!!");
            }
        else {
            setValue('mistake_' + taskNumber,1);
            console.log("MISTAKE!!");    
            recordMistake();
            }
        nexttask();
        }

    function updateEquation() {
        const type = getTaskAttribute('taskType')
        const textElement = document.querySelector('#equation');
        let x = getTaskAttribute('x');
        let y = getTaskAttribute('y');

            if (type == 'sum'){
                textElement.innerHTML = ` <h1> Sum ${x} and ${y} </h1>`;
            } else if (type == 'multiply'){
                textElement.innerHTML = `<h1>Multiply ${x} by ${y}</h1>`;
            }
            focusInputField('answer_input')
        }

    // PREVENT ENTER KEY
    $(document).ready(function() {
        $(document).keydown(function(event) {
            if (event.keyCode === 13) { // 13 is the key code for Enter
                event.preventDefault(); // Prevent default Enter key behavior
                $("#mathNext").click(); // Trigger click on the button with id "mathNext"
                return false;
            }
        });
    });