    function nexttask() {
            if (getTaskAttribute('taskType')== 'doubleColor'){
                // Record end time for the current task
                if (doubleNum == 1){
                    console.log("double task number 2")
                    updateTextAndColor(2)
                    doubleNum++
                    console.log(doubleNum)
                } else {
                    if (taskNumber >= ww.numTasks) {
                        // If the current task is the last one, submit the form
                        taskEndTimes.push(new Date().toISOString());
                        setValue('bigtimeout', 0);
                        submit();
                        } else if (taskNumber < ww.numTasks) {
                        taskEndTimes.push(new Date().toISOString());
                        // Increase the task number and load the next task
                        taskNumber++;
                        loadTaskContent();
                        taskStartTimes.push(new Date().toISOString());
                        } else {
                        console.log("Unexpected case");
                        }
                }
            } else {
                if (taskNumber >= ww.numTasks) {
                    taskEndTimes.push(new Date().toISOString());
                    setValue('bigtimeout', 0);
                    submit()
                    // If the current task is the last one, submit the form
                } else if (taskNumber < ww.numTasks) {
                    taskEndTimes.push(new Date().toISOString());
                    // Increase the task number and load the next task
                    taskNumber++;
                    loadTaskContent();
                    taskStartTimes.push(new Date().toISOString());
                } else {
                }
            }
    }

    // SUBMIT PAGE
    function submit() {
        // Add timing data to hidden fields
        document.getElementById('task_start_times').value = JSON.stringify(taskStartTimes);
        document.getElementById('task_end_times').value = JSON.stringify(taskEndTimes);
        document.getElementById('mistakeList').value = JSON.stringify(mistakeList);
        calculateEndTimeAndDuration();
        sendData();
        document.getElementById('submitButton').click();
    }

    function submitSmall() {
        // Add timing data to hidden fields
        document.getElementById('submitButton').click();
    }

    // CAPTURE TIMESTAMP
    function captureTimestamp(fieldName) {
        // Capture the current timestamp
        let timestamp = new Date().toISOString();
        // Store the timestamp in the corresponding hidden input field
        document.getElementById(fieldName).value = timestamp;
    }

    function taskReady(){
        document.getElementById('ready').style.display = 'none';
        document.getElementById('tasking').style.display = 'block';
        taskStartTimes.push(new Date().toISOString());
        console.log(ww.taskList)
    }

    function startTimer(){
        var bigtimer = ww.timerTime; // Set bigtimer from dynamic value
        var bigtime = ww.timerTime;
        var display = document.getElementById('timer');
        setStartTime();
        startCountdown(bigtimer, display); // Start the countdown
        setTimeout(function() {
            // Hide the taskDiv
            if (ww.practice == 1){
                // console.log("auto-submitting")
                submitSmall()
            } else if (ww.practice == 0){
                console.log("out of time, not autosubmitting")
                document.getElementById('tasking').style.display = 'none';
                document.getElementById('timeup').style.display = 'block';
            }
        }, bigtime * 1000); // Convert seconds to milliseconds
    }
    
    // COUNTDOWN
    function startCountdown(bigtimer, display) {
        var timer = bigtimer -1 ; // Start from bigtimer value
        var interval = setInterval(function () {
            display.textContent = timer + " ";
            if (timer <= 0) {
                clearInterval(interval); // Stops the timer when it reaches zero
                display.textContent = "0";
            }
            timer--;
        }, 1000);
    }

    function focusInputField(field) {
        const inputField = document.getElementById(field);
        inputField.focus();
    }

    // CHECK FOR TIMEOUT MISTAKES
    function checkAndSetMistakeTimeout() {
        // Generate mistake field IDs based on ww.numTasks
        const mistakeIds = Array.from({length: ww.numTasks}, (_, i) => `mistake_${i + 1}`);
    
        // Initialize a counter for empty fields
        let emptyFieldCount = 0;
    
        // Helper function to check and count empty fields
        function checkEmptyField(fieldId, defaultValue) {
            var element = document.getElementById(fieldId);
            if (element && element.value === "") {
                element.value = defaultValue;
                emptyFieldCount++; // Increment the empty field counter
            }
        }
    
        // Check the mistake fields and set to 1 if empty
        mistakeIds.forEach(function(id) {
            checkEmptyField(id, 333);
        });
        if (refresh == 1){
            setValue('bigtimeout', 333);
            // console.log(`Checked ${mistakeIds.length} mistake fields. But you refreshed the page.`); // debugging
            submit()
        } else if (refresh == 0){
            setValue('bigtimeout', emptyFieldCount);
            // console.log(`Checked ${mistakeIds.length} mistake fields. Empty fields: ${emptyFieldCount}`); // debugging
            submit()
        } else {
            console.log('something went wrong');
        }
    }

    function setStartTime() {
        totalStartTime = Date.now();
    }
    
    // Function to calculate and store end time and total time taken
    function calculateEndTimeAndDuration() {
        if (typeof totalStartTime !== 'undefined') {
          totalEndTime = Date.now();
          totalTimeTaken = (totalEndTime - totalStartTime) / 1000;
          // console.log("Total time taken (seconds):", totalTimeTaken);
        } else {
            totalTimeTaken = -333
        }
      }