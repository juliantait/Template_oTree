function redoInstructions(){
    if (roundNumber>=maxRounds){
        pass
    } else {
        setFormValues(); 
        setValue('redoinstructions',1);
    }
}

function setFormValues() {
    // Set the values of form fields here
    document.querySelector('input[name="quiz1"][value="€2.00"]').checked = true;
    document.querySelector('input[name="quiz2"][value="€4.00"]').checked = true;
    if (stakesHigh) {
        document.querySelector('input[name="quiz3"][value="€20.00"]').checked = true;
        } 
    else {
        document.querySelector('input[name="quiz3"][value="€10.00"]').checked = true;
        }
    document.querySelector('input[name="quiz4"][value="€2.00"]').checked = true;
    document.querySelector('input[name="quiz5"][value="True"]').checked = true;
    document.querySelector('input[name="quiz6"][value="The worker can choose whether or not to report this to the team"]').checked = true;
    document.querySelector('input[name="quiz7"][value="The Ambituous project always fails"]').checked = true;
    document.querySelector('input[name="quiz8"][value="There is still a chance that the Ambituous project can fail"]').checked = true;
}