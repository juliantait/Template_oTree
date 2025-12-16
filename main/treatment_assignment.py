from otree.api import BaseSubsession


def creating_session(subsession: BaseSubsession):
    """
    Entry point invoked from main/__init__.py.

    For now, this simply logs that the session was created. The full treatment
    assignment logic previously commented in main/__init__.py can be moved
    into this function when ready.
    """
    if subsession.round_number == 1:
        print("Session Created")

    # Placeholder for future treatment assignment logic:
    # -------------------------------------------------
    # session = subsession.session
    # if subsession.round_number == 1:
    #     # Define possible treatments
    #     possible_treatments = ['random_low','random_high','matched_low','matched_high']
    #     two_strangers = session.config.get('twoStrangers')
    #     two_partners = session.config.get('twoPartners')
    #     one_each_high = session.config.get('oneEachHigh')
    #     one_each_low = session.config.get('oneEachLow')
    #     one_stranger_low = session.config.get('oneStrangerLow')
    #     one_partner_low = session.config.get('onePartnerLow')
    #     one_stranger_high = session.config.get('oneStrangerHigh')
    #     one_partner_high = session.config.get('onePartnerHigh')
    #     pilot = session.config.get('pilot')
    #
    #     # Determine group assignments by session variables
    #     if two_strangers == 1:
    #         treatments = ['random_low', 'random_high']
    #     elif two_partners == 1:
    #         treatments = ['matched_low', 'matched_high']
    #     elif one_each_high == 1:
    #         treatments = ['random_high', 'matched_high']
    #     elif one_each_low == 1:
    #         treatments = ['random_low', 'matched_low']
    #     elif one_stranger_low == 1:
    #         treatments = ['random_low']
    #     elif one_partner_low == 1:
    #         treatments = ['matched_low']
    #     elif one_stranger_high == 1:
    #         treatments = ['random_high']
    #     elif one_partner_high == 1:
    #         treatments = ['matched_low']
    #     else:
    #         treatments = ['random_high', 'matched_low']
    #
    #     # Treatment cycle
    #     import itertools
    #     treatment_cycle = itertools.cycle(treatments)
    #
    #     for group in subsession.get_groups():
    #         treatment = next(treatment_cycle)
    #         for player in group.get_players():
    #             player.participant.treatment_group = treatment
    #             if player.id_in_group == 1:
    #                 player.participant.manager = 1
    #             else:
    #                 player.participant.manager = 0
    #
    #     # Initialize participant variables
    #     for group in subsession.get_groups():
    #         for player in group.get_players():
    #             player.participant.payoff_r1 = []
    #             player.participant.payoff_r2 = []
    #             player.participant.payoff_r3 = []
    #             player.participant.payoff_r4 = []
    #             player.participant.failed_attempts = 0
    #             player.participant.all_task_times = []
    #             player.participant.reports = []
    #             player.participant.round_timers = []
    #             player.participant.temp_data = []

