# Models
from otree.api import *
import random
import json
import math
import itertools
from datetime import datetime
from typing import List, Tuple, Dict
from collections import defaultdict
import copy

doc = """
tasks
"""
manager = None
task_manager = None

class C(BaseConstants):
    NAME_IN_URL = 'main1'
    PLAYERS_PER_GROUP = 3
    #FINANCES
    players = 100
    prob = 0.8
    x_low = 10
    x_high = 20
    y = 4
    bonus = 1.00
    showup = 5
    punish_max = 2
    fail = 2
    numrewarded = 2
    colors = [
        '#1E90FF',  # Bright Blue (replacing #3498db)
        '#e74c3c',  # Red
        '#2ecc71',  # Green
        '#f39c12',  # Orange
        '#8A2BE2',  # Purple
        '#FFF700',  # Yellow
        '#000000',  # Black
        '#7f8c8d'   # Gray
    ]

    color_names = {
        '#1E90FF': 'BLUE',    # Updated Blue
        '#e74c3c': 'RED',
        '#2ecc71': 'GREEN',
        '#f39c12': 'ORANGE',
        '#8A2BE2': 'PURPLE',
        '#FFF700': 'YELLOW',
        '#000000': 'BLACK',
        '#7f8c8d': 'GRAY'
    }
    colorNumbers = 4
    bigtime = 25
    task_counts = {'doubleColor': 10, 'sum': 5, 'multiply': 5}
    taskTypes = ['doubleColor','color','multiply', 'sum']
    numTaskRounds = 10
    numBlocks = 2
    NUM_ROUNDS = numTaskRounds * numBlocks
    timer_bounds = {'low': 60, 'high': 75}
    timer_solutions = 75

class Subsession(BaseSubsession):
    randomization_done = models.BooleanField(initial=False)
    counter_done = models.BooleanField(initial=False)
    round_done = models.BooleanField(initial=False)
    
class Group(BaseGroup):
    report_p2 = models.BooleanField()
    report_p3 = models.BooleanField()
    project = models.StringField()
    payoff = models.FloatField()
    X = models.IntegerField()
    bonus_p2 = models.FloatField()
    bonus_p3 = models.FloatField()
    stakes_high = models.BooleanField()
    mistake = models.BooleanField()
    mistake_p2 = models.BooleanField()
    mistake_p3 = models.BooleanField()
    timer = models.IntegerField(blank=True)

class Player(BasePlayer):
    totalTimeTaken = models.FloatField()
    thisContent = models.StringField()
    matched = models.BooleanField(blank=True)
    task_times = models.StringField(blank=True)  # This will store the JSON string of task times
    task_start_times = models.StringField()
    tasks = models.StringField(blank=True)
    mistakeList = models.StringField(blank=True)
    task_end_times = models.StringField(blank=True)
    mistake = models.BooleanField(blank=True)
    mistake_other = models.BooleanField(blank=True)
    mistakes = models.FloatField(blank=True)
    errors = models.FloatField(blank=True)
    timeouts = models.IntegerField(initial=0)    
    bigtimeout = models.IntegerField(initial=0)
    report = models.BooleanField()
    report_other = models.BooleanField(blank=True)
    punishment_other = models.FloatField(blank=True)
    punishment = models.FloatField(blank=True)
    timer = models.IntegerField(blank=True)
    meanTime_doubleColor = models.FloatField(blank=True)
    meanTime_sum = models.FloatField(blank=True)
    meanTime_multiply = models.FloatField(blank=True)
    meanTime_color = models.FloatField(blank=True)
    mistake_1 = models.IntegerField(blank=True)
    mistake_2 = models.IntegerField(blank=True)
    mistake_3 = models.IntegerField(blank=True)
    mistake_4 = models.IntegerField(blank=True)
    mistake_5 = models.IntegerField(blank=True)
    mistake_6 = models.IntegerField(blank=True)
    mistake_7 = models.IntegerField(blank=True)
    mistake_8 = models.IntegerField(blank=True)
    mistake_9 = models.IntegerField(blank=True)
    mistake_10 = models.IntegerField(blank=True)
    mistake_11 = models.IntegerField(blank=True)
    mistake_12 = models.IntegerField(blank=True)
    mistake_13 = models.IntegerField(blank=True)
    mistake_14 = models.IntegerField(blank=True)
    mistake_15 = models.IntegerField(blank=True)
    mistake_16 = models.IntegerField(blank=True)
    mistake_17 = models.IntegerField(blank=True)
    mistake_18 = models.IntegerField(blank=True)
    mistake_19 = models.IntegerField(blank=True)
    mistake_20 = models.IntegerField(blank=True)

# FUNCTIONS 
def creating_session(subsession: Subsession):
    global manager, task_manager
    session = subsession.session
    session.past_groups = []

    if subsession.round_number == 1:
        print(f'\n \n \n')
        print(f'------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------')
        print(f'\n \n \n')


        # region [TREATMENT ASSIGNMENT]
        # Defining possible treatments
        possibleTreatments = ['random_low','random_high','matched_low','matched_high']
        twoStrangers = session.config['twoStrangers']
        twoPartners = session.config['twoPartners']
        oneEachHigh = session.config['oneEachHigh']
        oneEachLow = session.config['oneEachLow']
        oneStrangerLow = session.config['oneStrangerLow']
        onePartnerLow = session.config['onePartnerLow']
        oneStrangerHigh = session.config['oneStrangerHigh']
        onePartnerHigh = session.config['onePartnerHigh']
        pilot = session.config['pilot']


        # Determine group assignments by session variables
        if twoStrangers == 1:
            treatments = ['random_low', 'random_high'] 
        elif twoPartners ==1:
            treatments = ['matched_low', 'matched_high']
        elif oneEachHigh == 1:
            treatments = ['random_high', 'matched_high']
        elif oneEachLow == 1:
            treatments = ['random_low', 'matched_low']
        elif oneStrangerLow == 1:
            treatments = ['random_low']
        elif onePartnerLow == 1:
            treatments = ['matched_low']
        elif oneStrangerHigh == 1:
            treatments = ['random_high']
        elif onePartnerHigh == 1:
            treatments = ['matched_low']
        else:
            treatments = ['random_high', 'matched_low']

        # Actually assign treatment
        treatment_cycle = itertools.cycle(treatments)
        
        for group in subsession.get_groups():
            treatment = next(treatment_cycle)
            for player in group.get_players():
                player.participant.treatment_group = treatment
                if player.id_in_group ==1:
                    player.participant.manager = 1  # 0 for worker, 1 for manager
                else: 
                    player.participant.manager = 0  # 0 for worker, 1 for manager

                
                print(f"Player {player.id_in_group} assigned to treatment: {player.participant.treatment_group}")
                print(f"Player {player.id_in_group} role: {'Manager' if player.participant.manager else 'Worker'}")

        # initialising participant variables 
        for group in subsession.get_groups():
            for player in group.get_players():  
                player.participant.payoff_r1 = []
                player.participant.payoff_r2 = []
                player.participant.payoff_r3 = []
                player.participant.payoff_r4 = []
                player.participant.failed_attempts = 0
                player.participant.all_task_times = []
                player.participant.reports = []
                player.participant.round_timers = []
                player.participant.temp_data = []
        # endregion
        # region [TASK GENERATION - PRACTICE]
        # PRACTICE ROUND
        # Initialize the TreatmentGroupManager

        
        # practice = TreatmentGroupManager()

        # # Define blocks with stakes and team composition
        # practice.create_block('practice', ['doubleColor', 'sum', 'multiply'], [10, 5, 5], stakes=False, team=True)

        # # Define treatment groups with different block orders
        # practice.create_group('practice_treat', ['practice', 'practice'])

        # # Generate rounds for all groups
        # practice.generate_group_rounds()

        # # Create the MultiRoundTaskManager
        # practice_manager = MultiRoundTaskManager(C.NUM_ROUNDS, practice)
        # practice_manager.generate_tasks()
        
        # treatment_group = 'practice_treat'
        # practice_round_tasks = practice_manager.get_tasks_for_round(1, treatment_group)

        # tasks_dict = [task.to_dict() for task in practice_round_tasks]
        # session.vars['practiceTasks'] = json.dumps(tasks_dict)

        hardcoded_practice_tasks = [
            {
                "taskType": "sum",
                "correctAnswer": "3",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 2,
                "y": 1,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#7f8c8d",
                "correctAnswer2": "#2ecc71",
                "distraction": "#000000",
                "distraction2": "#FFF700",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 1,
                "font2": 0,
                "buttons": 4,
                "buttons2": 6
            },
            {
                "taskType": "multiply",
                "correctAnswer": "5",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 5,
                "y": 1,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "sum",
                "correctAnswer": "14",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 5,
                "y": 9,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "sum",
                "correctAnswer": "14",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 4,
                "y": 10,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#7f8c8d",
                "correctAnswer2": "#f39c12",
                "distraction": "#1E90FF",
                "distraction2": "#7f8c8d",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 0,
                "font2": 1,
                "buttons": 5,
                "buttons2": 5
            },
            {
                "taskType": "sum",
                "correctAnswer": "3",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 2,
                "y": 1,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "sum",
                "correctAnswer": "15",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 6,
                "y": 9,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "multiply",
                "correctAnswer": "3",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 3,
                "y": 1,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#2ecc71",
                "correctAnswer2": "#e74c3c",
                "distraction": "#8A2BE2",
                "distraction2": "#f39c12",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 0,
                "font2": 0,
                "buttons": 6,
                "buttons2": 5
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#000000",
                "correctAnswer2": "#000000",
                "distraction": "#e74c3c",
                "distraction2": "#f39c12",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 1,
                "font2": 0,
                "buttons": 4,
                "buttons2": 5
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#1E90FF",
                "correctAnswer2": "#f39c12",
                "distraction": "#000000",
                "distraction2": "#FFF700",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 0,
                "font2": 1,
                "buttons": 5,
                "buttons2": 4
            },
            {
                "taskType": "multiply",
                "correctAnswer": "8",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 2,
                "y": 4,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "multiply",
                "correctAnswer": "50",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 10,
                "y": 5,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#f39c12",
                "correctAnswer2": "#000000",
                "distraction": "#2ecc71",
                "distraction2": "#8A2BE2",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 1,
                "font2": 0,
                "buttons": 4,
                "buttons2": 5
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#7f8c8d",
                "correctAnswer2": "#7f8c8d",
                "distraction": "#2ecc71",
                "distraction2": "#8A2BE2",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 0,
                "font2": 0,
                "buttons": 4,
                "buttons2": 6
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#FFF700",
                "correctAnswer2": "#7f8c8d",
                "distraction": "#7f8c8d",
                "distraction2": "#e74c3c",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 0,
                "font2": 1,
                "buttons": 6,
                "buttons2": 4
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#e74c3c",
                "correctAnswer2": "#FFF700",
                "distraction": "#f39c12",
                "distraction2": "#000000",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 1,
                "font2": 0,
                "buttons": 5,
                "buttons2": 6
            },
            {
                "taskType": "multiply",
                "correctAnswer": "64",
                "correctAnswer2": "",
                "distraction": "",
                "distraction2": "",
                "x": 8,
                "y": 8,
                "mistake": False,
                "font": "",
                "font2": "",
                "buttons": "",
                "buttons2": ""
            },
            {
                "taskType": "doubleColor",
                "correctAnswer": "#FFF700",
                "correctAnswer2": "#000000",
                "distraction": "#1E90FF",
                "distraction2": "#2ecc71",
                "x": 0,
                "y": 0,
                "mistake": False,
                "font": 1,
                "font2": 0,
                "buttons": 6,
                "buttons2": 6
            }
            ]
        session.vars['practiceTasks'] = json.dumps(hardcoded_practice_tasks)
        print("these are practice")
        print(session.vars['practiceTasks'])

        # endregion 
        # region [TASK GENERATION - MAIN]
        def load_original_blocks():
            with open('original_blocks.json', 'r') as f:
                return json.load(f)
            
        def randomize_round_order(blocks):
            randomized_blocks = copy.deepcopy(blocks)
            for block in randomized_blocks.values():
                random.shuffle(block)
            return randomized_blocks


        def randomize_task_order(round_data):
            randomized_round = copy.deepcopy(round_data)
            random.shuffle(randomized_round['tasks'])
            return randomized_round

        def assign_treatment_round_orders(session, original_blocks):
            for treatment in treatments:
                setattr(session, f'treatment_{treatment}', randomize_round_order(original_blocks))

        def get_participant_tasks(treatment_blocks, player):
            participant_tasks = []
            
            for block in treatment_blocks.values():
                for round_data in block:
                    participant_tasks.append(randomize_task_order(round_data))
            return participant_tasks
        
        def get_round_data(participant_tasks, round_number):
            return participant_tasks[round_number - 1]



        original_blocks = load_original_blocks()
        
        # Assign randomized round orders to each treatment
        assign_treatment_round_orders(subsession.session, original_blocks)
        
        # Randomize task order for each participant
        for player in subsession.get_players():
            playTreatment = player.participant.treatment_group
            print(playTreatment)
            if playTreatment == 'random_high':
                treatment_blocks = player.session.vars['treatment_random_high']
            elif playTreatment == 'random_low':
                treatment_blocks = player.session.vars['treatment_random_low']
            elif playTreatment == 'matched_low':    
                treatment_blocks = player.session.vars['treatment_matched_low']
            elif playTreatment == 'matched_high':
                treatment_blocks= player.session.vars['treatment_matched_high']

            participant_tasks = get_participant_tasks(treatment_blocks, player)
            player.participant.tasks = participant_tasks
            
            # Print the first and last round for this participant
            for round_num in [1, C.NUM_ROUNDS]:
                print(player)
                print(player.participant.treatment_group)
                round_data = get_round_data(participant_tasks, round_num)
                print(f"Round {round_num}:")
                print(f"Timer: {round_data['timer']}")
                print(f"First 3 task types: {[task['taskType'] for task in round_data['tasks'][:3]]}")


        # Verify that round order is the same within a treatment
        print("\nVerifying round order consistency within treatments:")
        for treatment in treatments:
            treatment_blocks = getattr(session, f'treatment_{treatment}')
            print(f"\n{treatment.upper()}:")
            for block_name, block_data in treatment_blocks.items():
                print(f"{block_name}: {[round_data['timer'] for round_data in block_data]}")

        print("\nNote: The timer values represent the round order. They should be consistent for all participants within the same treatment.")



        # Initialize the TreatmentGroupManager
        manager = TreatmentGroupManager()

        # Define blocks with stakes and team composition
        manager.create_block('random_high', ['doubleColor', 'sum', 'multiply'], [10, 5, 5], stakes=True, team=False)
        manager.create_block('random_low', ['doubleColor', 'sum', 'multiply'], [10, 5, 5], stakes=False, team=False)
        manager.create_block('matched_high', ['doubleColor', 'sum', 'multiply'], [10, 5, 5], stakes=True, team=True)
        manager.create_block('matched_low', ['doubleColor', 'sum', 'multiply'], [10, 5, 5], stakes=False, team=True)


        # Define treatment groups with different block orders
        manager.create_group('random_low', ['random_low', 'random_high'])
        manager.create_group('random_high', ['random_high', 'random_low'])
        manager.create_group('matched_low', ['matched_low', 'matched_high'])
        manager.create_group('matched_high', ['matched_high', 'matched_low'])
        manager.create_group('matched_pilot', ['matched_low', 'matched_low'])
        manager.create_group('random_pilot', ['random_low', 'random_low'])

        # Generate rounds for all groups
        manager.generate_group_rounds()

        # Create the MultiRoundTaskManager
        task_manager = MultiRoundTaskManager(C.NUM_ROUNDS, manager)
        task_manager.generate_tasks()

        # Store both managers in the session for later use
        session.vars['treatment_group_manager'] = manager
        session.vars['task_manager'] = task_manager

        # Print block sequences and settings only for groups in 'treatments' variable
        print("\nBlock Sequences and Settings for Treatment Groups:")
        for group_name in treatments:
            if group_name in manager.groups:
                group = manager.groups[group_name]
                print(f"\n{group_name} Block Sequence:")
                for block_index, block_name in enumerate(group.block_sequence):
                    block = manager.blocks[block_name]
                    print(f"  Block {block_index + 1} ({block_name}):")
                    print(f"    Stakes: {'High' if block.stakes else 'Low'}")
                    print(f"    Team: {'Paired' if block.team else 'Random'}")
                    print(f"    Tasks: {dict(zip(block.task_types, block.task_counts))}")
            else:
                print(f"\nWarning: {group_name} not found in manager.groups")


        # Print task sequences for the first round of each block for each group
        print(f' \n You have set {C.NUM_ROUNDS} rounds into motion.')
        print(f'\n The first rounds of each block are:')
        for group_name in treatments:
            for round_number in [1,C.numTaskRounds+1]:  # First round of each block
                round_data = manager.get_round_data(group_name, round_number)
                print(f"\n{group_name}, Round {round_number}:")
                print(f"  Stakes: {'High' if round_data.stakes else 'Low'}")
                print(f"  Team: {'Paired' if round_data.team else 'Random'}")
                print(f"  Task Sequence: {round_data.task_sequence}")

        # endregion

# GENERATING PARTICIPANT ROUND RANDOMISATION
def randomize_for_participant(blocks: Dict[str, List[Dict]]) -> Dict[str, Dict[str, List[Dict]]]:
    randomized_blocks = copy.deepcopy(blocks)
    for block_name, block_data in randomized_blocks.items():
        # Shuffle the order of rounds within the block
        random.shuffle(block_data)
        # Shuffle tasks within each round
        for round_data in block_data:
            random.shuffle(round_data['tasks'])
    return randomized_blocks

def get_round_data(participant_tasks: Dict[str, List[Dict]], round_number: int) -> Dict:
    block_round_number = round_number 
    return participant_tasks[block_round_number - 1]

# GENERATING THE DATA        
def generate_round_timers(num_rounds):
    possible_timers = list(range(C.timer_bounds['low'], C.timer_bounds['high']+1 , 1))
    print(f' \n Possible timers are: {possible_timers}')
    timers = random.sample(possible_timers, k=min(num_rounds, len(possible_timers)))
    
    # If we need more timers than unique values, we start repeating
    while len(timers) < num_rounds:
        timers.extend(random.sample(possible_timers, k=min(num_rounds - len(timers), len(possible_timers))))
    
    return timers

def format_group_info(groups, round_number):
    formatted_info = f"Round {round_number} Groups:\n"
    for i, group in enumerate(groups, 1):
        formatted_info += f"Team {i}: {group}\n"
    return formatted_info

def print_matching_groups(player_categories):
    print("Matching Groups:")
    for (treatment_group, is_manager), players in player_categories.items():
        print(f"Treatment Group: {treatment_group}, Is Manager: {is_manager}")
        print(f"  Players: {[p.id_in_subsession for p in players]}")

def common_template_vars(session, group):
    return {
        'counter': session.counter,
        'bonus': cu(C.bonus),
        'x_high': cu(C.x_high),
        'x_low': cu(C.x_low),
        'y': cu(C.y),
        'x': cu(group.X),
    }  

def collect_payoffs(player):
    payoffs = []
    for i in range(1,player.round_number+1):
        prevplayer = player.in_round(i)
        roundpay = prevplayer.payoff
        payoffs.append(roundpay)
        # player.participant.payoff_r1 = player.in_all_rounds()
    return payoffs

class RoundData:
    def __init__(self, stakes: bool, team: bool, task_sequence: List[str]):
        self.stakes = stakes  # True for high, False for low
        self.team = team  # True for paired, False for random
        self.task_sequence = task_sequence

class Block:
    def __init__(self, name: str, task_types: List[str], task_counts: List[int], stakes: bool, team: bool):
        self.name = name
        self.task_types = task_types
        self.task_counts = task_counts
        self.stakes = stakes
        self.team = team

    def generate_task_sequence(self) -> List[str]:
        task_sequence = []
        for task_type, count in zip(self.task_types, self.task_counts):
            task_sequence.extend([task_type] * count)
        random.shuffle(task_sequence)
        return task_sequence

class TreatmentGroup:
    def __init__(self, name: str, block_sequence: List[str]):
        self.name = name
        self.block_sequence = block_sequence
        self.round_data: Dict[int, RoundData] = {}

    def add_round_data(self, round_number: int, task_sequence: List[str], stakes: bool, team: bool):
        self.round_data[round_number] = RoundData(stakes, team, task_sequence)

class TreatmentGroupManager:
    def __init__(self):
        self.groups: Dict[str, TreatmentGroup] = {}
        self.blocks: Dict[str, Block] = {}

    def create_block(self, name: str, task_types: List[str], task_counts: List[int], stakes: bool, team: bool):
        self.blocks[name] = Block(name, task_types, task_counts, stakes, team)

    def create_group(self, name: str, block_sequence: List[str]):
        self.groups[name] = TreatmentGroup(name, block_sequence)

    def generate_group_rounds(self):
        for group_name, group in self.groups.items():
            round_number = 1
            for block_name in group.block_sequence:
                if block_name not in self.blocks:
                    raise ValueError(f"Block {block_name} does not exist.")

                block = self.blocks[block_name]
                for _ in range(C.numTaskRounds):  # number of rounds per block
                    task_sequence = block.generate_task_sequence()
                    group.add_round_data(round_number, task_sequence, block.stakes, block.team)
                    round_number += 1

    def get_round_data(self, group_name: str, round_number: int) -> RoundData:
        if group_name in self.groups and round_number in self.groups[group_name].round_data:
            return self.groups[group_name].round_data[round_number]
        else:
            raise ValueError(f"Data for group {group_name}, round {round_number} does not exist.")

class Task:
    def __init__(self, task_type: str, correct_answer: str, correct_answer_2: str, distraction: str, distraction_2: str, font: int, font_2: int, buttons: int,buttons_2: int, x: int = 0, y: int = 0, ):
        self.taskType = task_type
        self.correctAnswer = correct_answer
        self.correctAnswer2 = correct_answer_2
        self.distraction = distraction
        self.distraction2 = distraction_2
        self.x = x
        self.y = y
        self.mistake = False
        self.font = font
        self.font2 = font_2
        self.buttons = buttons
        self.buttons2 = buttons_2

    def to_dict(self):
        return {
            'taskType': self.taskType,
            'correctAnswer': self.correctAnswer,
            'correctAnswer2': self.correctAnswer2,
            'distraction': self.distraction,
            'distraction2': self.distraction2,
            'x': self.x,
            'y': self.y,
            'mistake': self.mistake,
            'font': self.font,
            'font2': self.font2,
            'buttons': self.buttons,
            'buttons2': self.buttons2
        }

class RandomGeneratedTasks:
    def __init__(self, treatment_group_manager, group_name, round_number):
        self.treatment_group_manager = treatment_group_manager
        self.group_name = group_name
        self.round_number = round_number
        self.tasks = []

    def getListOfTasks(self) -> List[Task]:
        round_data = self.treatment_group_manager.get_round_data(self.group_name, self.round_number)
        task_sequence = round_data.task_sequence
        tasks = []
        for task_type in task_sequence:
            if task_type == 'color':
                correct_answer, distraction, font, buttons = self._generate_color_task()
                tasks.append(Task(task_type=task_type, correct_answer=correct_answer, distraction=distraction, correct_answer_2="", distraction_2="", font=font, font_2="", buttons=buttons, buttons_2=0))
            elif task_type == 'doubleColor':
                correct_answer, distraction, font, buttons, correct_answer2, distraction2, font2, buttons2 = self._generate_double_color_task()
                tasks.append(Task(task_type=task_type, correct_answer=correct_answer, distraction=distraction, correct_answer_2=correct_answer2, distraction_2=distraction2, font=font, font_2=font2, buttons=buttons, buttons_2=buttons2))
            elif task_type == 'multiply':
                correct_answer, x, y = self._generate_multiply_task()
                tasks.append(Task(task_type=task_type, correct_answer=str(correct_answer), distraction='', correct_answer_2='', distraction_2='', font='', font_2='', buttons='', buttons_2='', x=x, y=y))
            elif task_type == 'sum':
                correct_answer, x, y = self._generate_sum_task()
                tasks.append(Task(task_type=task_type, correct_answer=str(correct_answer), distraction='', correct_answer_2='', distraction_2='', font='', font_2='', buttons='', buttons_2='', x=x, y=y))
        self.tasks = tasks
        return tasks

    def get_task_attribute(self, task_number, attribute):
        task_index = task_number - 1
        if task_index < 0 or task_index >= len(self.tasks):
            raise ValueError(f"Task number {task_number} is out of range.")
        return getattr(self.tasks[task_index], attribute)

    def _generate_color_task(self) -> Tuple[str, str, int, int]:
        correct_answer = random.choice(C.colors)
        distraction = random.choice([c for c in C.colors if c != correct_answer])
        font = random.randint(0, 1)
        buttons = random.randint(4, 6)
        return correct_answer, distraction, font, buttons

    def _generate_double_color_task(self) -> Tuple[str, str, int, int, str, str, int, int]:
        correct_answer = random.choice(C.colors)
        correct_answer2 = random.choice(C.colors)
        distraction = random.choice([c for c in C.colors if c != correct_answer])
        distraction2 = random.choice([c for c in C.colors if c != correct_answer2])
        font = random.randint(0, 1)
        # Generate font2 with the desired probability distribution
        if random.random() < 0.8:  # 80% chance
            font2 = 1 - font
        else:  # 20% chance
            font2 = font
        buttons = random.randint(4, 6)
        buttons2 = random.randint(4, 6)
        return correct_answer, distraction, font, buttons, correct_answer2, distraction2, font2, buttons2

    def _generate_multiply_task(self) -> Tuple[int, int, int]:
        x = random.randint(1, 10)
        y = random.randint(1, 10)
        correct_answer = x * y
        return correct_answer, x, y

    def _generate_sum_task(self) -> Tuple[int, int, int]:
        x = random.randint(1, 10)
        y = random.randint(1, 10)
        correct_answer = x + y
        return correct_answer, x, y

class RoundTasks:
    def __init__(self, round_number: int, task_list: List[Task]):
        self.round = round_number
        self.taskList = task_list

    def to_dict(self):
        return {
            'round': self.round,
            'tasks': [task.to_dict() for task in self.taskList]
        }

class MultiRoundTaskManager:
    def __init__(self, num_rounds: int, treatment_group_manager: TreatmentGroupManager):
        self.num_rounds = num_rounds
        self.treatment_group_manager = treatment_group_manager
        self.rounds: Dict[int, Dict[str, RoundTasks]] = {}

    def generate_tasks(self):
        for group_name in self.treatment_group_manager.groups.keys():
            for round_num in range(1, self.num_rounds + 1):
                new_tasks = RandomGeneratedTasks(self.treatment_group_manager, group_name, round_num)
                task_list = new_tasks.getListOfTasks()
                if round_num not in self.rounds:
                    self.rounds[round_num] = {}
                self.rounds[round_num][group_name] = RoundTasks(round_num, task_list)

    def get_tasks_for_round(self, round_num: int, group_name: str) -> List[Task]:
        if round_num not in self.rounds or group_name not in self.rounds[round_num]:
            raise ValueError(f"Round {round_num} for group {group_name} not found.")
        return self.rounds[round_num][group_name].taskList

    def to_dict(self):
        return {round_num: {group_name: round_tasks.to_dict() for group_name, round_tasks in group_dict.items()}
                for round_num, group_dict in self.rounds.items()}
    
class TreatmentGroups:
    def __init__(self, groupName: str, groupMembers: List[int]):
        self.groupName = groupName
        self.groupMembers = groupMembers 

# PAGES   
class RoundStartWaitPage(WaitPage):
    wait_for_all_groups = True

    def after_all_players_arrive(self):
        subsession = self.subsession
        session = self.session
        treatment_group_manager = session.vars['treatment_group_manager']
        
        print(f"\nStarting RoundStartWaitPage process for Round {self.round_number}")
        
        # Set player attributes
        for player in subsession.get_players():
            treatment_group = player.participant.treatment_group
            round_data = treatment_group_manager.get_round_data(treatment_group, self.round_number)
            
            player.matched = 1 if round_data.team else 0
            player.group.stakes_high = 1 if round_data.stakes else 0
            player.group.X = C.x_high if player.group.stakes_high == 1 else C.x_low
            
            print(f"Player {player.id_in_subsession} - matched: {player.matched}, stakes_high: {player.group.stakes_high}, X: {player.group.X}")

        print("Player attributes set")

        # Grouping logic
        if self.round_number in [1, C.numTaskRounds + 1, 2 * C.numTaskRounds + 1]:
            print(f"Grouping randomly; start of block {(self.round_number - 1) // C.numTaskRounds + 1}")
            self.group_randomly(subsession.get_players())
        else:
            # First, maintain groups for matched players
            subsession.group_like_round(self.round_number - 1)
            print("Groups initially maintained from previous round")
            
            # Then, regroup unmatched players
            unmatched_players = [p for p in subsession.get_players() if not p.matched]
            if unmatched_players:
                print("Regrouping unmatched players")
                self.group_randomly(unmatched_players)
            else:
                print("All players matched, groups remain unchanged")

        # Record the current grouping for this round
        current_groups = [[p.id_in_subsession for p in g.get_players()] for g in subsession.get_groups()]
        if 'past_groups' not in session.vars:
            session.vars['past_groups'] = []
        session.vars['past_groups'].append(current_groups)
        
        print(f"Final groups for Round {self.round_number}: {current_groups}")
        # print(current_groups) # debuggin groups
        # print(f"Total recorded rounds: {len(session.vars['past_groups'])}") # debugging

    def group_randomly(self, players_to_group):
        subsession = self.subsession
        round_number = self.round_number

        print(f"\n--- Starting grouping for Round {round_number} ---")

        # Categorize players by exact treatment group and manager status
        def categorize_players(players):
            categories = {}
            for p in players:
                key = (p.participant.treatment_group, p.participant.manager)
                if key not in categories:
                    categories[key] = []
                categories[key].append(p)
            return categories

        player_categories = categorize_players(players_to_group)
        print("\nInitial player categories:")
        for (treatment_group, is_manager), players in player_categories.items():
            print(f"Treatment: {treatment_group}, Manager: {is_manager}, Count: {len(players)}")

        new_groups = []
        for (treatment_group, is_manager), players_in_category in player_categories.items():
            if is_manager:
                print(f"\nProcessing treatment group: {treatment_group}")
                managers = players_in_category
                workers = player_categories.get((treatment_group, 0), [])
                print(f"Managers: {len(managers)}, Workers: {len(workers)}")

                if treatment_group.startswith('matched_'):
                    print(f"Applying '{treatment_group}' grouping strategy")
                    if round_number == 1 or round_number == C.numTaskRounds + 1:
                        print("Implementing perfect stranger matching")
                        new_groups.extend(self.perfect_stranger_matching(managers, workers, treatment_group))
                    else:
                        print("Keeping groups from previous round")
                        previous_subsession = subsession.in_round(round_number - 1)
                        previous_matrix = previous_subsession.get_group_matrix()
                        for group in previous_matrix:
                            if previous_subsession.get_players()[group[0] - 1].participant.treatment_group == treatment_group:
                                new_groups.append(group)
                    print(f"Groups for {treatment_group}: {new_groups[-len(managers):]}")
                elif treatment_group.startswith('random_'):
                    print(f"Applying '{treatment_group}' grouping strategy")
                    random.shuffle(managers)
                    random.shuffle(workers)
                    new_groups.extend(self.form_groups(managers, workers))
                    print(f"Groups for {treatment_group}: {new_groups[-len(managers):]}")

        print(f"\nTotal new groups formed: {len(new_groups)}")

        # Get the existing group matrix
        matrix = subsession.get_group_matrix()
        print(f"Existing matrix groups: {len(matrix)}")

        # Remove players who are being regrouped from the existing matrix
        players_to_group_ids = set(p.id_in_subsession for p in players_to_group)
        matrix = [[p for p in group if p not in players_to_group_ids] for group in matrix]
        matrix = [group for group in matrix if group]  # Remove any empty groups
        print(f"Matrix groups after removal: {len(matrix)}")

        # Add the new groups to the matrix
        matrix.extend(new_groups)

        print(f"Final matrix groups: {len(matrix)}")

        # Set the new group matrix
        subsession.set_group_matrix(matrix)

        print("\nGrouping for Players Successful")
        print(format_group_info(matrix, self.round_number))
        print("--- Grouping completed ---\n")
        
    def perfect_stranger_matching(self, managers, workers, treatment_group):
        session = self.session
        # Use a dictionary to store past groups for each treatment
        past_groups_by_treatment = session.vars.get('past_groups_by_treatment', {})
        past_groups = past_groups_by_treatment.get(treatment_group, [])

        # If there are less than three teams, use random matching
        if len(managers) < 3:
            return self.form_groups(managers, workers)

        num_teams = len(managers)

        if not past_groups:
            # For the first matching, create initial groups
            initial_groups = self.form_groups(managers, workers)
            past_groups.append(initial_groups)
            past_groups_by_treatment[treatment_group] = past_groups
            session.vars['past_groups_by_treatment'] = past_groups_by_treatment
            return initial_groups

        # Get the most recent grouping for this treatment
        last_grouping = next((groups for groups in reversed(past_groups) if len(groups) == num_teams), None)

        if not last_grouping:
            # If no previous grouping found, create a new one
            new_groups = self.form_groups(managers, workers)
        else:
            # Perform perfect stranger matching
            new_groups = []
            for i, old_group in enumerate(last_grouping):
                manager = old_group[0]
                worker1 = last_grouping[(i + 1) % num_teams][1]
                worker2 = last_grouping[(i + 2) % num_teams][2]
                new_groups.append([manager, worker1, worker2])

        # Store the new groups for this treatment
        past_groups.append(new_groups)
        past_groups_by_treatment[treatment_group] = past_groups
        session.vars['past_groups_by_treatment'] = past_groups_by_treatment

        print(f'these are the new groups for treatment {treatment_group}: {new_groups}')
        return new_groups

    def form_groups(self, managers, workers):
        groups = []
        for manager in managers:
            if len(workers) < 2:
                raise ValueError(f"Not enough workers to form a group with manager")
            workers_pair = workers[:2]
            new_group = [manager.id_in_subsession] + [w.id_in_subsession for w in workers_pair]
            groups.append(new_group)
            workers = workers[2:] # Remove the paired workers from the pool
        return groups
        
class block(Page):
    template_name = 'main1/block.html'
    def is_displayed(player):
        return player.round_number in [1, C.numTaskRounds + 1, 2 * C.numTaskRounds + 1, 3 * C.numTaskRounds +1]

    def vars_for_template(self):
        session = self.session
        treatment_group_manager = session.vars['treatment_group_manager']
        blockNumber = math.ceil(self.round_number / C.numTaskRounds)
        treatment_group = self.participant.treatment_group
        round_data = treatment_group_manager.get_round_data(treatment_group, self.round_number)

        # Set player and group attributes
        self.matched = 1 if round_data.team else 0
        self.group.stakes_high = 1 if round_data.stakes else 0
        self.group.X = C.x_high if self.group.stakes_high == 1 else C.x_low
            
        return{
            'round_count': self.round_number,
            'bonus': cu(C.bonus),
            'x_high': cu(C.x_high),
            'x_low': cu(C.x_low),
            'y': cu(C.y),
            'previousblock': blockNumber-1,
            'blockNow': blockNumber,
            'fail': cu(C.fail),
            'x': cu(self.group.X),
            'matched': self.matched,
        }
    def before_next_page(p, timeout_happened):
        pass

class stakes(Page):
    template_name = 'main1/stakes.html'
    def before_next_page(p, timeout_happened):
        pass
       
    def vars_for_template(self):
        blockStart = self.round_number in [1, C.numTaskRounds + 1, 2 * C.numTaskRounds + 1, 3 * C.numTaskRounds + 1]
        session = self.session
        treatment_group_manager = session.vars['treatment_group_manager']
        treatment_group = self.participant.treatment_group
        round_data = treatment_group_manager.get_round_data(treatment_group, self.round_number)
        # Set player and group attributes
        self.matched = 1 if round_data.team else 0
        self.group.stakes_high = 1 if round_data.stakes else 0
        self.group.X = C.x_high if self.group.stakes_high == 1 else C.x_low
        return{
            'round_count': self.round_number,
            'bonus': cu(C.bonus),
            'x_high': cu(C.x_high),
            'x_low': cu(C.x_low),
            'y': cu(C.y),
            'fail': cu(C.fail),
            'x': cu(self.group.X),
            'matched': self.matched,
            'stakes_high': self.group.stakes_high,
            'blockStart': blockStart,
        }

class Wait(WaitPage):
    pass

class taskP(Page):
    template_name = 'main1/taskP.html'
    def vars_for_template(self):
        
        variablesOfInterest = ['totalTimeTaken']
        # treatment_group = self.participant.treatment_group
        # task_manager = self.session.vars['task_manager']
        # current_round_tasks = task_manager.get_tasks_for_round(self.round_number, treatment_group)
        # tasks_dict = [task.to_dict() for task in current_round_tasks]
        # print(tasks_dict)
        round_data = get_round_data(self.participant.tasks, self.round_number)
        self.timer = round_data['timer']
        self.group.timer=self.timer

        return {
            'bigtime': round_data['timer'],
            'taskList_json': json.dumps(round_data['tasks']),
            # 'bigtime': self.participant.round_timers[self.round_number - 1],
            # 'bigtime': 3,
            'round_count': self.round_number,
            # 'taskList_json': json.dumps(tasks_dict),
            'colors': C.colors,
            'colorNames_json': json.dumps(C.color_names),
            'numTasks': 20,
            'task_start_times': [],
            'task_end_times': [],
            'variablesOfInterest': json.dumps(variablesOfInterest),
        }
    def is_displayed(player):
        return player.participant.manager == 0
    form_model = 'player'
    form_fields = ['mistakeList','bigtimeout','task_start_times','task_end_times', 'mistake_1','mistake_2','mistake_3','mistake_4','mistake_5','mistake_6','mistake_7','mistake_8','mistake_9','mistake_10','mistake_11','mistake_12','mistake_13','mistake_14','mistake_15','mistake_16','mistake_17','mistake_18','mistake_19','mistake_20'] 
    def live_method(player, data):
        player.participant.vars['temp_data'] = data

    def before_next_page(player, timeout_happened):

        data = player.participant.temp_data
        if data == []:
            pass
        else:
            for variable, value in data.items():
                print(f"Set '{variable}': '{value}'")  # debugging
                setattr(player, variable, value)


        # Collating into mistake variable
        treatment_group = player.participant.treatment_group
        task_manager = player.session.vars['task_manager']
        current_round_tasks = task_manager.get_tasks_for_round(player.round_number, treatment_group)        
        numTasks = len(current_round_tasks)
        player.mistake = 1  # Start with the assumption that there is a mistake
        all_zero = True  # Flag to check if all mistake fields are zero

        for i in range(1, numTasks + 1):
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

        # Process timing data
        start_times = json.loads(player.task_start_times or '[]')
        end_times = json.loads(player.task_end_times or '[]')
        
        task_times = []
        task_manager = player.session.vars['task_manager']
        current_round_tasks = task_manager.get_tasks_for_round(player.round_number, treatment_group)
        tasks_dict = [task.to_dict() for task in current_round_tasks]
        player.tasks = json.dumps(tasks_dict)
        
        for i, (start, end) in enumerate(zip(start_times, end_times)):
            task_type = current_round_tasks[i].taskType
            duration = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
            task_times.append({'task_type': task_type, 'duration': duration})
        
        # Store the processed timing data
        player.task_times = json.dumps(task_times)
        # Append to participant variable
        player.participant.all_task_times.extend(task_times)

        # Create all_data by combining task times from all players
        all_data =  json.loads(player.task_times)

        # Create a defaultdict to store durations for each task type
        task_durations = defaultdict(list)

        # Group durations by task type
        for item in all_data:
            task_durations[item['task_type']].append(item['duration'])

        # Calculate mean time for each task type
        mean_times = {}
        for task_type, durations in task_durations.items():
            mean_times[task_type] = sum(durations) / len(durations)

        # Print results
        for task_type, mean_time in mean_times.items():
            print(f"Mean time for {task_type}: {mean_time:.3f} seconds")
        # taskTypes = ['doubleColor','color','multiply', 'sum']
        if 'doubleColor' in mean_times:
            player.meanTime_doubleColor = mean_times['doubleColor']
        if 'sum' in mean_times:
            player.meanTime_sum = mean_times['sum']
        if 'multiply' in mean_times:
            player.meanTime_multiply = mean_times['multiply']
        if 'color' in mean_times:
            player.meanTime_color = mean_times['color']

class WaitWithSolutions(WaitPage):
    body_text = """
        {{ include 'main1/color.html'}}

    """

class solutions(Page):
    template_name = 'main1/solutions.html'
    def is_displayed(p):
        return p.participant.manager == 1
    def vars_for_template(self):
        # treatment_group = self.participant.treatment_group
        # task_manager = self.session.vars['task_manager']
        # current_round_tasks = task_manager.get_tasks_for_round(self.round_number, treatment_group)
        # tasks_dict = [task.to_dict() for task in current_round_tasks]
        round_data = get_round_data(self.participant.tasks, self.round_number)

        return {
            'bigtime': C.timer_solutions,
            # 'bigtime': 3,
            'round_count': self.round_number,
            'taskList_json': json.dumps(round_data['tasks']),
            # 'taskList_json': json.dumps(tasks_dict),
            'colors': C.colors,
            'colorNames_json': json.dumps(C.color_names),
            'numTasks': 20,
            'task_start_times': [],
            'task_end_times': [],
        }
    
class report(Page):
    template_name = 'main1/report.html'
    def is_displayed(player):
        return player.participant.manager == 0 and player.mistake == 1
    form_model = 'player'
    form_fields = ['report']
    def before_next_page(player, timeout_happened):
        if player.mistake == 1:
            player.group.mistake = 1
        if player.id_in_group == 2:
            player.group.report_p2 = player.report
            player.group.mistake_p2 = player.mistake
        elif player.id_in_group == 3:
            player.group.report_p3 = player.report
            player.group.mistake_p3 = player.mistake

class nomistake(Page):
    template_name = 'main1/nomistake.html'
    def is_displayed(player):
        return player.participant.manager == 0 and player.mistake != 1
    def before_next_page(player, timeout_happened):
        if player.id_in_group == 2:
            player.group.report_p2 = player.field_maybe_none('report')
            player.group.mistake_p2 = player.mistake
        elif player.id_in_group == 3:
            player.group.report_p3 = player.field_maybe_none('report')
            player.group.mistake_p3 = player.mistake

class project(Page):
    template_name = 'main1/project.html'
    form_model = 'group'
    def get_form_fields(self):
        if self.id_in_group==1 :
            return ['project']
        
    def before_next_page(p, timeout_happened):
        if p.id_in_group==1:
            if p.group.project == 'A':
                # Set payoff with C.prob probability
                if p.group.field_maybe_none('mistake') != 1:
                    if random.random() < C.prob:
                        p.group.payoff = p.group.X
                    else:
                        p.group.payoff = C.fail 
                else:
                    p.group.payoff = C.fail
            elif p.group.project == 'B':
                p.group.payoff = C.y
            else:
                p.group.payoff = -333   
    def vars_for_template(self):
        return{
            'x': cu(self.group.X),
            'fail': cu(C.fail),
            'y': cu(C.y),
            '2': cu(2),
            '4': cu(4),
        }  

class bonus(Page):
    template_name = 'main1/bonus.html'
    def is_displayed(p):
        return p.participant.manager == 1
    form_model = 'group'
    form_fields = ['bonus_p2','bonus_p3']
    def error_message(player, values):
        if values['bonus_p2'] + values['bonus_p3']> C.punish_max:
            bon = cu(C.punish_max)
            return "The total punishment cannot exceed " + str(bon) + "."
    def vars_for_template(self):
        return{
            'bonus': cu(C.bonus),
            'x_high': cu(C.x_high),
            'x_low': cu(C.x_low),
            'payoff': cu(self.group.payoff),
            'punishmax': cu(C.punish_max)
        }
    
class payoff(Page):
    template_name = 'main1/payoff.html'
    def before_next_page(player, timeout_happened):
        round_number = player.round_number  # Assuming self.round_number gives the current round number
        if player.id_in_group == 2:
            #setattr(player.participant, player.payoff, player.group.payoff + player.group.bonus_p2)
            player.payoff = player.group.payoff - player.group.bonus_p2
        elif player.id_in_group == 3:
            #setattr(player.participant, player.payoff, player.group.payoff + player.group.bonus_p3)
            player.payoff = player.group.payoff - player.group.bonus_p3
        else: 
            #setattr(player.participant, player.payoff, player.group.payoff + C.bonus / 2)
            player.payoff = player.group.payoff

        # Generating OTHER variables; i.e. report_other & mistake_other and punishment_other
        if player.id_in_group == 2:
            player.report_other = player.group.field_maybe_none('report_p3')
            player.mistake_other = player.group.field_maybe_none('mistake_p3')
            player.punishment_other = player.group.bonus_p3
            player.punishment = player.group.bonus_p2
        elif player.id_in_group == 3:
            player.report_other = player.group.field_maybe_none('report_p2')
            player.mistake_other = player.group.field_maybe_none('mistake_p2')
            player.punishment_other = player.group.bonus_p2
            player.punishment = player.group.bonus_p3
        # Summing up reports made for end summary
        if player.field_maybe_none('report') in [1, 0]:
            player.participant.reports.append(player.report)
            print(player.participant.reports)

        # Generating subsession payoff vector to call back at end of experiment
        if player.round_number==C.NUM_ROUNDS:
            #player.participant.counter = player.participant.counter + 1
            subseshpayoffs = collect_payoffs(player)
            if player.participant._current_app_name == 'main1':
                player.participant.payoff_r1 = subseshpayoffs
            elif player.participant._current_app_name == "main2":
                player.participant.payoff_r2 = subseshpayoffs
            elif player.participant._current_app_name == 'main3':
                player.participant.payoff_r3 = subseshpayoffs
            elif player.participant._current_app_name == 'main4':
                player.participant.payoff_r4 = subseshpayoffs
            else: 
                player.participant.payoff_r1 = -333
                print("doesn't work")


    def vars_for_template(self):
        return{
            'bonus': cu(C.bonus),
            'x_high': cu(C.x_high),
            'x_low': cu(C.x_low),
            'payoff': cu(self.group.payoff),
            'b2': cu(self.group.bonus_p2),
            'b3': cu(self.group.bonus_p3),
            'round_count' : self.round_number,
        }

# page_sequence = [RoundStartWaitPage, solutions, block, stakes,taskP, report,nomistake, WaitWithSolutions,project,bonus,Wait,payoff]
page_sequence = [RoundStartWaitPage , block, stakes,taskP, report, nomistake, solutions, Wait,project,bonus,Wait,payoff]
