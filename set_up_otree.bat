@echo off

set DATABASE_URL=postgres://CHANGE_ME_DB_USER:CHANGE_ME_DB_PASSWORD@localhost:5432/mistakesexperiment
set ADMIN_USERNAME = "admin"
set OTREE_ADMIN_PASSWORD="1234"
set OTREE_PRODUCTION=1
set OTREE_AUTH_LEVEL=STUDY

cd C:\Users\Admin\Desktop\TAIT\ExpMistakes Copy
otree resetdb
y
start http://CHANGE_ME_LAB_SERVER_IP:8000/rooms
otree prodserver
echo Your postgres server is now up and running