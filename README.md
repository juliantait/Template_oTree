# oTree-Template
 This is a template for oTree experimental apps useful for running experiments in the lab. See `template.html` for an example of the pre-coded design and how to use it.

## App Timeline
- before (welcome + consent)
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
  - `before/startpage.html`: waiting page while participants take a seat; experimenter must move participants beyond; usually leave as-is unless you need different holding text.
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
- format_session_data.py : program to turn raw SENSITIVE data into i) csv for payment, ii) csv with anonymised experiment data, and iii) optionally draft an email with the anonymised file attached (recipient configurable via `--email` or `$SESSION_DATA_EMAIL`)

## Template HTML Layout
The file [`_static/global/html/template.html`](./_static/global/html/template.html) serves as the core visual template for most experimental pages. It is located in the `_static/global/html/` directory of your project. This template demonstrates and defines how all of the pre-defined CSS sections will look and behave, providing a live preview of your main screen layout.

- **Header Section**: Shows how the experimental screen header appears, including the title and subtitle, styled using the shared CSS (`global/style.css` and the imports in that file).
- **Main Content Area**: Contains a section for page headings and standard paragraph text, both vertically and horizontally centered within a card. This section uses classes such as `.experimental-content`, `.section-title`, and `.section-text` to illustrate their styling.
- **Navigation Buttons**: Displays the "Back" and "Next" buttons with their associated styles (`.button-row`, `.next-button`).
- **Logos Section**: Includes a common logos area displayed at the bottom of the intro and outro screens.

By editing or viewing this file in your browser, you can see how the different visual building blocks (as defined in the referenced CSS) are applied. When creating new pages, structure your content to fit inside this card layout by extending or including this template, ensuring consistency across experimental screens.
