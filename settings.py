from os import environ

SESSION_CONFIGS = [
    dict(
         name='test',
         app_sequence=['before','intro','outro'],
         num_demo_participants=18,
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
    )

PARTICIPANT_FIELDS = ['temp_data']
SESSION_FIELDS = []

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'
# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False

DEMO_PAGE_INTRO_HTML = """ """

INSTALLED_APPS = ['otree']

DEBUG = False

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

SECRET_KEY = 'REDACTED_SECRET_KEY'
