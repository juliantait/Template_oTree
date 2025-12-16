# oTree-Template
 This is a template for oTree experimental app useful for running experiments in the lab. 

## App Timeline
- before (welcome + consent)
- intro (instrucitons)
- main (expeirmental game)
- outro (demographics + payment)

## How to use and edit this template
- Instructions content: edit `intro/instructions_text.html`. Each `<div class="instruction-block">` is shown as one page to participants. Add, edit, or reorder blocks there to change the instruction pages.
- Quiz questions: edit `intro/quiz_items.py`. Define `QUIZ_ITEMS` entries with `field`, `prompt`, `choices`, and `answer`. The intro quiz reads directly from this file.
- Treatment assignment: edit `before/treatment_assignment.py`. Treatments are assigned when the session is created (via `creating_session` in the `before` app). Adjust `assign_treatments` to set the treatment groups you need.

## Other Files 
- set_up_otree.bat : program to start oTree on the experimenter's PC in the lab
- format_session_data.py : program to turn raw SENSITIVE data into i) csv for payment, ii) csv with anonymised experiment data, and iii) send that file to REDACTED_EMAIL

