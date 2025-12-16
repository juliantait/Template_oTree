from otree.api import BaseSubsession
import itertools


def assign_treatments(subsession: BaseSubsession):
    """
    Example treatment assignment:
    - Define a list of possible treatments.
    - Cycle through that list and assign each participant a treatment_group.
    This keeps a stable, reproducible order across groups and players.
    """
    if subsession.round_number != 1:
        return

    possible_treatments = ['random_low', 'random_high', 'matched_low', 'matched_high']
    treatment_cycle = itertools.cycle(possible_treatments)

    for group in subsession.get_groups():
        for player in group.get_players():
            player.participant.treatment_group = next(treatment_cycle)

    print("Session Created with treatment assignment for all participants")

