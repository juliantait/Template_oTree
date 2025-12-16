# Models
from otree.api import *
import random
import json
import math
import itertools
from datetime import datetime
from typing import List, Tuple, Dict

doc = """
Intro
"""
class C(BaseConstants):
    NAME_IN_URL = 'Introduction'
    PLAYERS_PER_GROUP = 3



class Subsession(BaseSubsession):
    randomization_done = models.BooleanField(initial=False)
    counter_done = models.BooleanField(initial=False)
    round_done = models.BooleanField(initial=False)
      
class Group(BaseGroup):
    stakes_high = models.BooleanField()
    X = models.IntegerField()

class Player(BasePlayer):
    participant_label = models.StringField()
    redoinstructions = models.BooleanField(initial=0,blank=True)
    skiptoquiz = models.BooleanField(initial=0,blank=True)
    num_failed_attempts = models.IntegerField(initial=0)

    quiz1 = models.StringField(
        label='What is the largest punishment the manager can hand out to one worker at the end of each round?',
        widget=widgets.RadioSelect,
        choices=[cu(C.punish_max), cu(0.50), cu(5.00)])
    quiz2 = models.StringField(
        label='How much does project B pay?',
        widget=widgets.RadioSelect,
        choices=[cu(4), cu(1), cu(0.5)])
    quiz3 = models.StringField(
        label='What is the maximum amount that the Ambitious project pays to each team member when none of the workers made a mistake?',
        widget=widgets.RadioSelect,
        choices=[cu(2), cu(10), cu(20)])
    quiz4 = models.StringField(
        label='What is the maximum amount that the Ambitious project pays to each team member when one or both workers made a mistake?',
        widget=widgets.RadioSelect,
        choices=[cu(2), cu(10), cu(20)])
    quiz5 = models.StringField(
        label='True or false: If one or more workers report a mistake, then the Backup project is guaranteed to pay more than the Ambituous project.',
        widget=widgets.RadioSelect,
        choices=[ 'False','True'])

# FUNCTIONS 
def common_template_vars(session, group):
    return {
        'bonus': cu(C.bonus),
        'x_high': cu(C.x_high),
        'x_low': cu(C.x_low),
        'y': cu(C.y),
        'x': cu(group.X),
        'showup': cu(C.showup),
        'roundreward': 2,
        'tasks': 5,
        'fail': cu(2),
        'nrreward':2,
        'lowpunish':cu(1),
        'highpunish':cu(2),
        'bigtimer': C.bigtime,
        'low': C.timer_bounds['low'],
        'high': C.timer_bounds['high'],
        'runds':  C.roundnumbers,
    }  

# PAGES    
class instr_M1(Page):
    def is_displayed(player):
        return player.id_in_group == 1
    
    def before_next_page(player, timeout_happened):
        session = player.session
        treatment_group_manager = session.vars['treatment_group_manager']
        treatment_group = player.participant.treatment_group
        round_data = treatment_group_manager.get_round_data(treatment_group, player.round_number)

        # Set player and group attributes
        player.matched = 1 if round_data.team else 0
        player.group.stakes_high = 1 if round_data.stakes else 0
        player.group.X = C.x_high if player.group.stakes_high == 1 else C.x_low  
        player.stakes_high = 1 if round_data.stakes else 0
        player.manager = player.participant.manager

    def vars_for_template(self):
        return {
        'showup': cu(C.showup),
        'tasks': 20,
        'roundreward': C.numrewarded,
        'runds':  C.roundnumbers,
    }     
    
class instr_W1(Page):
    def is_displayed(player):
        return player.id_in_group != 1
    
    def before_next_page(player, timeout_happened):
        session = player.session
        treatment_group_manager = session.vars['treatment_group_manager']
        treatment_group = player.participant.treatment_group
        round_data = treatment_group_manager.get_round_data(treatment_group, player.round_number)

        # Set player and group attributes
        player.matched = 1 if round_data.team else 0
        player.group.stakes_high = 1 if round_data.stakes else 0
        player.group.X = C.x_high if player.group.stakes_high == 1 else C.x_low  
        player.stakes_high = 1 if round_data.stakes else 0
        player.manager = player.participant.manager

    def vars_for_template(self):


        return {
        'showup': cu(C.showup),
        'tasks': 'random',
        'roundreward': C.numrewarded,
        'runds':  C.roundnumbers,

    }  
    
class prequiz(Page):
    form_model = 'player'
    form_fields = ['redoinstructions']
    def is_displayed(player):
        return player.group.round_number == 1
        
class quiz(Page):
    form_model = 'player'
    def get_form_fields(self):
        # Show quiz3m if participant is a manager, otherwise show quiz3w
            return ['quiz1','quiz2','quiz3','quiz4','quiz5','quiz6','quiz7','quiz8','redoinstructions']
    def is_displayed(player):
        return player.redoinstructions ==0
    def error_message(player, values):
        player.stakes_high = player.group.stakes_high
        fail = str(cu(C.fail))
        if player.stakes_high == 1:
            solutions = dict(quiz1='€2.00', quiz2='€4.00', quiz3='€20.00', quiz4='€2.00', quiz5='True', quiz6='The worker can choose whether or not to report this to the team', quiz7='The Ambituous project always fails', quiz8='There is still a chance that the Ambituous project can fail')
        elif player.stakes_high == 0:
            solutions = dict(quiz1='€2.00', quiz2='€4.00', quiz3='€10.00', quiz4='€2.00', quiz5='True', quiz6='The worker can choose whether or not to report this to the team', quiz7='The Ambituous project always fails', quiz8='There is still a chance that the Ambituous project can fail')  
        print(values)
        print(solutions)  
        if values['quiz1'] != solutions['quiz1'] or values['quiz2'] != solutions['quiz2'] or values['quiz3'] != solutions['quiz3'] or values['quiz4'] != solutions['quiz4'] or values['quiz5'] != solutions['quiz5'] or values['quiz6'] != solutions['quiz6'] or values['quiz7'] != solutions['quiz7'] or values['quiz8'] != solutions['quiz8']:
            player.num_failed_attempts += 1
            player.participant.failed_attempts += 1
            if player.num_failed_attempts >=2:
                return "One or more quiz answers are wrong. Try re-reading the instructions."
            else:
                    return "One or more quiz answers are wrong."
  
    def before_next_page(player,timeout_happened):
        if player.participant.failed_attempts == 0:
            player.participant.quiz_beast = 1
        else:
            player.participant.quiz_beast = 0

    def vars_for_template(self):
        return {
        'stakes_high': 1 if self.stakes_high else 0,
        'manager': self.participant.manager,
    }  
    def app_after_this_page(player, app_sequence):
        if player.redoinstructions ==0  and player.participant.manager ==1 :
            return app_sequence[0]

class prepractice (Page):
    template_name = 'intro/prepractice.html'
    
    def is_displayed(player):
        return player.participant.manager == 0 and player.redoinstructions == 0  
 
    def vars_for_template(self):
        # Example data to pass to the template
        return {
            'bigtime': C.bigtime,
        }

    def before_next_page(player, timeout_happened):
        pass

class practiceTask (Page):
    template_name = 'main1/taskP.html'  # Use the same template as taskP
    form_model = 'player'
    form_fields = ['mistakeList','bigtimeout','task_start_times','task_end_times',  'mistake_1','mistake_2','mistake_3','mistake_4','mistake_5','mistake_6','mistake_7','mistake_8','mistake_9','mistake_10','mistake_11','mistake_12','mistake_13','mistake_14','mistake_15','mistake_16','mistake_17','mistake_18','mistake_19','mistake_20'] 
    def vars_for_template(self):
        practice_tasks = json.loads(self.session.vars['practiceTasks'])
        return {
            'bigtime': C.bigtime,  # Set a practice time limit
            'round_count': 'Practice',
            'taskList_json': json.dumps(practice_tasks),
            'colors': C.colors,
            'colorNames_json': json.dumps(C.color_names),
            'numTasks': len(practice_tasks),
            'task_start_times': [],
            'task_end_times': [],
            'variablesOfInterest': json.dumps([]),  # No variables to track for practice
        }
    def live_method(player, data):
        player.participant.vars['temp_data'] = data
    def is_displayed(player):
        return player.participant.manager == 0 and player.redoinstructions == 0
    def before_next_page(player,timeout_happened):
        data = player.participant.temp_data
        if data == []:
            pass
        else:
            for variable, value in data.items():
                print(f"Set '{variable}': '{value}'")  # debugging
                setattr(player, variable, value)
        
        numTasks = 20
        player.mistake = 1  # Start with the assumption that there is a mistake
        all_zero = True  # Flag to check if all mistake fields are zero
        for i in range(1, numTasks + 1):
            mistake_value = player.field_maybe_none(f'mistake_{i}')
            if mistake_value is not None and mistake_value != 0:
                all_zero = False
                break  # Exit the loop as soon as we find a non-zero mistake
            mistake_value = player.field_maybe_none(f'mistake_{i}')
            if mistake_value is not None and mistake_value != 0:
                all_zero = False
                break  # Exit the loop as soon as we find a non-zero mistake

        # If all mistake fields are zero, set player.mistake to 0
        if all_zero:
            player.mistake = 0

        if player.mistake == 0:
            player.mistakes = 0
        elif player.mistake == 1:
            player.mistakes = sum(1 for i in range(1, numTasks + 1) if getattr(player, f'mistake_{i}', 0) != 0)
        player.errors = player.mistakes - player.bigtimeout

class postpractice (Page):
    template_name = 'intro/postpractice.html'
    def vars_for_template(self):
        # Example data to pass to the template
        return {
            'bigtime': C.bigtime,
            'errors': self.errors,
            'mistakes': self.mistakes,
            'timeouts': self.bigtimeout,
            **common_template_vars(self.session, self.group),
            'colors': C.colors,
            'colorNames_json': json.dumps(C.color_names),
        } 
    
    def is_displayed(player):
        return player.participant.manager == 0 and player.redoinstructions == 0
    
    def app_after_this_page(player, app_sequence):
        if player.redoinstructions ==0:
            return app_sequence[0]
        
page_sequence = [instr_M1, instr_W1, prequiz, quiz, prepractice, practiceTask, postpractice]

