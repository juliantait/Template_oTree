@echo off

REM !!! FILL IN THE CHANGE_ME_* VALUES BELOW LOCALLY ON THE LAB PC. NEVER COMMIT THE REAL VALUES (this repository is public). !!!

REM FYI: REM means that row is commented out

REM === Database Setup (only needed if you want to set up your own DB; this requires the postgres password to be entered into the terminal) ===
REM psql -U postgres
REM CREATE DATABASE experimentname;
REM CREATE USER CHANGE_ME_DB_USER WITH PASSWORD 'CHANGE_ME_DB_PASSWORD';
REM GRANT ALL PRIVILEGES ON DATABASE experimentname TO CHANGE_ME_DB_USER;

REM === Database Management (at CREED, ask the lab manager for the shared lab database name, user and password) ===
set DB_NAME=CHANGE_ME_DB_NAME
set DB_USER=CHANGE_ME_DB_USER
set DB_PASSWORD=CHANGE_ME_DB_PASSWORD
set DB_HOST=localhost
set DB_PORT=5432
set DATABASE_URL=postgres://%DB_USER%:%DB_PASSWORD%@%DB_HOST%:%DB_PORT%/%DB_NAME%


REM === OTree variables ===
set OTREE_ADMIN_USERNAME=admin
set OTREE_ADMIN_PASSWORD=CHANGE_ME_ADMIN_PASSWORD
set OTREE_PRODUCTION=1 
set OTREE_AUTH_LEVEL=STUDY

REM === Starting the OTree project up on the server ===

REM === !!! ADOPT PATH TO YOUR OTREE PROJECT FOLDER!!! ===
cd "C:\Users\Admin\Desktop\TAIT\my great experiment"
echo Type 'y' to reset the database (advised)
otree resetdb

REM Start the server in a new terminal
start "oTree Server" cmd /k otree prodserver

REM === Open oTree Monitoring Page === 

REM === !!! SELECT LAB !!! ===
REM Set this to the IP address of the lab's oTree server PC (ask the lab manager; one per lab room)
set LAB_SERVER_IP=CHANGE_ME_LAB_SERVER_IP

REM Wait for prodserver to boot up & open oTree monitoring page
timeout /t 5 >nul
start http://%LAB_SERVER_IP%:8000/rooms

echo Your postgres server is up and running :)
echo This terminal will close now
timeout /t 10 >nul