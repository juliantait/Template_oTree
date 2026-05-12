from os import environ

SESSION_CONFIGS = [
    dict(
         name='test',
         app_sequence=['before','intro','main','outro'],
         num_demo_participants=10,
     ),
]

# if you set a property in SESSION_CONFIG_DEFAULTS, it will be inherited by all configs
# in SESSION_CONFIGS, except those that explicitly override it.
# the session config can be accessed from methods in your apps as self.session.config,
# e.g. self.session.config['participation_fee']

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00,
    participation_fee=0.00,
    doc="",
    quiz_bonus=5,
    num_rewarded=2,
    showup=2.5,
    num_experimental_rounds=10,
    verify_quiz=True,  # when False, quiz answers are not validated (useful for testing)
)

PARTICIPANT_FIELDS = ['temp_data','payoff_vector','failed_attempts']
# Description of PARTICIPANT_FIELDS:
# - temp_data: Temporary storage for any participant-specific data during the session.
# - payoff_vector: A list storing all payoff-relevant values across all rounds and apps for a participant.
# - failed_attempts: Counts the number of times a participant answers the quiz incorrectly.

SESSION_FIELDS = []

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'
# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False

DEMO_PAGE_INTRO_HTML = """ """

INSTALLED_APPS = ['otree']

DEBUG = True

# This room exists on the computers in the CREED large lab as a desktop shortcut 'Chrome to 'experiment' Room' or 'Chrome to Large Lab experiment Server (Giorgia)'
ROOMS = [
dict(
name='experiment',
display_name='Experimental Session',
),
]

# Admin credentials from environment
import os
ADMIN_USERNAME = os.environ.get('OTREE_ADMIN_USERNAME')
ADMIN_PASSWORD = os.environ.get('OTREE_ADMIN_PASSWORD')
DATABASES = {
'default': {
'ENGINE': 'django.db.backends.postgresql_psycopg2',
'NAME': os.environ.get('DB_NAME'),
'USER': os.environ.get('DB_USER'),
'PASSWORD': os.environ.get('DB_PASSWORD'),
'HOST': os.environ.get('DB_HOST', 'localhost'),
'PORT': os.environ.get('DB_PORT', '5432'),
}
}

SECRET_KEY = os.environ.get("OTREE_SECRET_KEY", "")
