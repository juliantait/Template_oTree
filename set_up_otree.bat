@echo off

set DATABASE_URL=postgres://moi:ExperimentAllDay@localhost:5432/mistakesexperiment
set ADMIN_USERNAME = "admin"
set OTREE_ADMIN_PASSWORD="1234"
set OTREE_PRODUCTION=1
set OTREE_AUTH_LEVEL=STUDY

cd C:\Users\Admin\Desktop\TAIT\ExpMistakes Copy
otree resetdb
y
start http://145.18.178.130:8000/rooms
otree prodserver
echo Your postgres server is now up and running