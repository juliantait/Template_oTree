"""GROUP-MATCHING REFERENCE — CODE FROM A DIFFERENT STUDY. NOT TEMPLATE
MACHINERY, AND NOT ADAPTABLE BY UNCOMMENTING.

Moved here from main/group_matching.py on 2026-08-13 (Julian, main-review item
J3): main/ holds only things that are either used or clearly labelled foreign,
and this file was neither — it wore a "verbatim reference block you can
uncomment and adapt" badge while being verbatim code from ANOTHER study.

WHAT IT ACTUALLY IS. A RoundStartWaitPage with per-treatment grouping
strategies (random matching, group persistence, perfect-stranger rotation for
manager+two-worker triads), copied unchanged from the study it was written
for. It references names THIS TEMPLATE DOES NOT HAVE — C.numTaskRounds,
C.x_high / C.x_low, player.matched, group.stakes_high, participant.manager,
participant.treatment_group as used here, and
session.vars['treatment_group_manager'] — so "uncomment and adapt" really
means PORT FROM A DIFFERENT CODEBASE: uncommented as-is it raises NameError on
the first round. It also predates this template's conventions (print-based
debugging, no safe config accessor).

WHAT IT IS STILL GOOD FOR: the SHAPE of a solution — how perfect-stranger
matching keeps per-treatment group histories in session.vars, how matched and
unmatched players are regrouped differently, and where a wait page does that
work. Whoever builds real grouping should read it for that and write fresh
code in this template's idiom.

READ FIRST, in TODO.md: the "Group matching" entry (and the
"Move treatment randomisation" entry it is deliberately filed next to — the
two cannot be designed independently, because role-mixed groups force the
first matching to happen at role assignment), plus the "Wait-page dropout
detection" entry, which is where a wait page like this one meets its failure
mode.
"""

# from otree.api import WaitPage
# import random
# import itertools
# 
# class RoundStartWaitPage(WaitPage):
#     wait_for_all_groups = True
# 
#     def after_all_players_arrive(self):
#         subsession = self.subsession
#         session = self.session
#         treatment_group_manager = session.vars['treatment_group_manager']
#         
#         print(f"\nStarting RoundStartWaitPage process for Round {self.round_number}")
#         
#         # Set player attributes
#         for player in subsession.get_players():
#             treatment_group = player.participant.treatment_group
#             round_data = treatment_group_manager.get_round_data(treatment_group, self.round_number)
#             
#             player.matched = 1 if round_data.team else 0
#             player.group.stakes_high = 1 if round_data.stakes else 0
#             player.group.X = C.x_high if player.group.stakes_high == 1 else C.x_low
#             
#             print(f"Player {player.id_in_subsession} - matched: {player.matched}, stakes_high: {player.group.stakes_high}, X: {player.group.X}")
# 
#         print("Player attributes set")
# 
#         # Grouping logic
#         if self.round_number in [1, C.numTaskRounds + 1, 2 * C.numTaskRounds + 1]:
#             print(f"Grouping randomly; start of block {(self.round_number - 1) // C.numTaskRounds + 1}")
#             self.group_randomly(subsession.get_players())
#         else:
#             # First, maintain groups for matched players
#             subsession.group_like_round(self.round_number - 1)
#             print("Groups initially maintained from previous round")
#             
#             # Then, regroup unmatched players
#             unmatched_players = [p for p in subsession.get_players() if not p.matched]
#             if unmatched_players:
#                 print("Regrouping unmatched players")
#                 self.group_randomly(unmatched_players)
#             else:
#                 print("All players matched, groups remain unchanged")
# 
#         # Record the current grouping for this round
#         current_groups = [[p.id_in_subsession for p in g.get_players()] for g in subsession.get_groups()]
#         if 'past_groups' not in session.vars:
#             session.vars['past_groups'] = []
#         session.vars['past_groups'].append(current_groups)
#         
#         print(f"Final groups for Round {self.round_number}: {current_groups}")
#         # print(current_groups) # debuggin groups
#         # print(f"Total recorded rounds: {len(session.vars['past_groups'])}") # debugging
# 
#     def group_randomly(self, players_to_group):
#         subsession = self.subsession
#         round_number = self.round_number
# 
#         print(f"\n--- Starting grouping for Round {round_number} ---")
# 
#         # Categorize players by exact treatment group and manager status
#         def categorize_players(players):
#             categories = {}
#             for p in players:
#                 key = (p.participant.treatment_group, p.participant.manager)
#                 if key not in categories:
#                     categories[key] = []
#                 categories[key].append(p)
#             return categories
# 
#         player_categories = categorize_players(players_to_group)
#         print("\nInitial player categories:")
#         for (treatment_group, is_manager), players in player_categories.items():
#             print(f"Treatment: {treatment_group}, Manager: {is_manager}, Count: {len(players)}")
# 
#         new_groups = []
#         for (treatment_group, is_manager), players_in_category in player_categories.items():
#             if is_manager:
#                 print(f"\nProcessing treatment group: {treatment_group}")
#                 managers = players_in_category
#                 workers = player_categories.get((treatment_group, 0), [])
#                 print(f"Managers: {len(managers)}, Workers: {len(workers)}")
# 
#                 if treatment_group.startswith('matched_'):
#                     print(f"Applying '{treatment_group}' grouping strategy")
#                     if round_number == 1 or round_number == C.numTaskRounds + 1:
#                         print("Implementing perfect stranger matching")
#                         new_groups.extend(self.perfect_stranger_matching(managers, workers, treatment_group))
#                     else:
#                         print("Keeping groups from previous round")
#                         previous_subsession = subsession.in_round(round_number - 1)
#                         previous_matrix = previous_subsession.get_group_matrix()
#                         for group in previous_matrix:
#                             if previous_subsession.get_players()[group[0] - 1].participant.treatment_group == treatment_group:
#                                 new_groups.append(group)
#                     print(f"Groups for {treatment_group}: {new_groups[-len(managers):]}")
#                 elif treatment_group.startswith('random_'):
#                     print(f"Applying '{treatment_group}' grouping strategy")
#                     random.shuffle(managers)
#                     random.shuffle(workers)
#                     new_groups.extend(self.form_groups(managers, workers))
#                     print(f"Groups for {treatment_group}: {new_groups[-len(managers):]}")
# 
#         print(f"\nTotal new groups formed: {len(new_groups)}")
# 
#         # Get the existing group matrix
#         matrix = subsession.get_group_matrix()
#         print(f"Existing matrix groups: {len(matrix)}")
# 
#         # Remove players who are being regrouped from the existing matrix
#         players_to_group_ids = set(p.id_in_subsession for p in players_to_group)
#         matrix = [[p for p in group if p not in players_to_group_ids] for group in matrix]
#         matrix = [group for group in matrix if group]  # Remove any empty groups
#         print(f"Matrix groups after removal: {len(matrix)}")
# 
#         # Add the new groups to the matrix
#         matrix.extend(new_groups)
# 
#         print(f"Final matrix groups: {len(matrix)}")
# 
#         # Set the new group matrix
#         subsession.set_group_matrix(matrix)
# 
#         print("\nGrouping for Players Successful")
#         print(format_group_info(matrix, self.round_number))
#         print("--- Grouping completed ---\n")
#         
#     def perfect_stranger_matching(self, managers, workers, treatment_group):
#         session = self.session
#         # Use a dictionary to store past groups for each treatment
#         past_groups_by_treatment = session.vars.get('past_groups_by_treatment', {})
#         past_groups = past_groups_by_treatment.get(treatment_group, [])
# 
#         # If there are less than three teams, use random matching
#         if len(managers) < 3:
#             return self.form_groups(managers, workers)
# 
#         num_teams = len(managers)
# 
#         if not past_groups:
#             # For the first matching, create initial groups
#             initial_groups = self.form_groups(managers, workers)
#             past_groups.append(initial_groups)
#             past_groups_by_treatment[treatment_group] = past_groups
#             session.vars['past_groups_by_treatment'] = past_groups_by_treatment
#             return initial_groups
# 
#         # Get the most recent grouping for this treatment
#         last_grouping = next((groups for groups in reversed(past_groups) if len(groups) == num_teams), None)
# 
#         if not last_grouping:
#             # If no previous grouping found, create a new one
#             new_groups = self.form_groups(managers, workers)
#         else:
#             # Perform perfect stranger matching
#             new_groups = []
#             for i, old_group in enumerate(last_grouping):
#                 manager = old_group[0]
#                 worker1 = last_grouping[(i + 1) % num_teams][1]
#                 worker2 = last_grouping[(i + 2) % num_teams][2]
#                 new_groups.append([manager, worker1, worker2])
# 
#         # Store the new groups for this treatment
#         past_groups.append(new_groups)
#         past_groups_by_treatment[treatment_group] = past_groups
#         session.vars['past_groups_by_treatment'] = past_groups_by_treatment
# 
#         print(f'these are the new groups for treatment {treatment_group}: {new_groups}')
#         return new_groups
# 
#     def form_groups(self, managers, workers):
#         groups = []
#         for manager in managers:
#             if len(workers) < 2:
#                 raise ValueError(f"Not enough workers to form a group with manager")
#             workers_pair = workers[:2]
#             new_group = [manager.id_in_subsession] + [w.id_in_subsession for w in workers_pair]
#             groups.append(new_group)
#             workers = workers[2:] # Remove the paired workers from the pool
#         return groups


