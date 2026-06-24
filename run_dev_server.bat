@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo  CV + Jobs site - local dev server
echo ========================================
echo.
echo  Browse jobs:  http://127.0.0.1:8000/
echo  Applied page: http://127.0.0.1:8000/jobs/applied/
echo  CV:           http://127.0.0.1:8000/cv/
echo.
echo  Keep this window OPEN while you browse.
echo  Press Ctrl+C to stop the server.
echo.
python manage.py runserver 127.0.0.1:8000
pause
