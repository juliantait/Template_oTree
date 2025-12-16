# Exp_Hidden-Mistakes
 This is the oTree folder for Hidden Mistakes. It contains 6 apps. Intro (instructions, consent) and outro (demographics and results) are as the names suggest. *main* has all the code for the game (including round rematching and treatment allocation). *mainX* replicates the *main* app completely for the other subsessions

## Timeline
There are 4 subsessions, each of which contains 8 rounds of the task/admit/reward game. 

## Treatment Allocation
- *stakes_high* alternates between subsessions. 
- *participant.stakes_high* determines which the experiment starts with; currently assigned randomly at the start of experiment.

## Participant Labels
Add '?participant_label=Bob' to the end of the URL provided to join the session.

## Quizzes
- quiz 1 has option to go back to redo instructions (i.e. forward to app *intro2*)
- quiz 2 has option to read instructions at bottom of the page. Answers must be correct to move on from this
- within intro and intro2 'reread instructions' takes people straight onto the next round to read them in the same app again. 


# Variables
## block
Description: block number

## round
Description: round number with-in block

## mistake
Description: binary, worker mistake in that round

## mistake_other
Description: binayr, co-worker made a mistake in that round

## report
Description: binary, worker reported their mistake

## report_other
Description: binary, co-worker reported their mistake

## payoff
Description: eur, project payoff

## punish
Description: eur, worker punishment, positive is a punishment

## punish_other
Description: eur, co-worker punishment, positive is a punishment

## stakes_high
Description: binary, high-stakes treatment

## team_mistake
Description: binary, mistake made by at least one worker in team

## timeouts
Description: num, tasks timedout on in that round

## errors
Description: num, total errors on tasks in that round

## mistakes
Description: num, total mistakes on tasks in that round (errors + timeouts)

## time
Description: time, average time per task in that round

## matched
Description: binary, matched treatment

## bigtimeout
Description: [Add your description here]

## participant_id
Description: unique participant ID

## manager
Description: binary, manager role

## gender
Description: string, gender

## age
Description: int, age

## earned
Description: eur, total earned in session

## round_abs
Description: int, absolute round number from beginning

## project_A
Description: binary, project choice

## past_punish
Description: int, total times worker has been punished in *past rounds* in the session

## past_punish_prop
Description: int, share of *past rounds* worker was punished in the session

## mistaken_rounds
Description: int, number of rounds with *at least one* mistake in that block

## reported_rounds
Description: int, number of reported mistakes in that block

## reported_prop
Description: num, share of total mistakes admitted to in block