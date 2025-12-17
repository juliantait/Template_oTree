# oTree-Template
 This is a template for oTree experimental app useful for running experiments in the lab. 

## App Timeline
- before (welcome + consent)
    - 
- intro (instrucitons)
- main (expeirmental game)
- outro (demographics + payment)

## How to use and edit this template
- Instructions content: edit `intro/instructions_text.html`. Each `<div class="instruction-block">` is shown as one page to participants. Add, edit, or reorder blocks there to change the instruction pages.
- Quiz questions: edit `intro/quiz_items.py`. Define `QUIZ_ITEMS` entries with `field`, `prompt`, `choices`, and `answer`. The intro quiz reads directly from this file.
- Treatment assignment: edit `before/treatment_assignment.py`. Treatments are assigned when the session is created (via `creating_session` in the `before` app). Adjust `assign_treatments` to set the treatment groups you need.
- Experimental Payoff: edit `outro/payment_rule.py` to determine how participants are actually paid. The logic inside this file controls which rounds and payoffs are selected for payment at the end.

## Pages by app (edit guidance)
- before
  - `before/startpage.html`: waiting page while participants take a seat; usually leave as-is unless you need different holding text.
  - `before/welcome+consent.html`: welcome and consent; should be edited to match your approved consent language.
- intro
  - `intro/instructions_text.html`: only file to edit for instructions; each `<div class="instruction-block">` you add here is displayed as its own page automatically.
  - `intro/quiz_items.py`: edit questions, choices, and correct answers; updates flow into the quiz automatically.
  - `intro/templates/` (`instructing.html`, `quiz.html`): template shells; typically do not edit.
- main
  - `main/`: This folder contains the core logic and code for your experimental task. Place the main game code, task logic, and any files that control the experiment's core flow here.
- outro
  - `outro/Results.html`: built-in results summary showing per-round payoffs and total payment; generally leave untouched. To update how payment is calculated, edit the function in `outro/payment_rule.py`.
  - `outro/Demographics.html`: collects and verifies IVAN numbers and other basic demographic questions; edit here if you need to change the questionnaire.



## Other Files 
- set_up_otree.bat : program to start oTree on the experimenter's PC in the lab
- format_session_data.py : program to turn raw SENSITIVE data into i) csv for payment, ii) csv with anonymised experiment data, and iii) send that file to REDACTED_EMAIL

