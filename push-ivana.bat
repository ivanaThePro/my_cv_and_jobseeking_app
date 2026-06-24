@echo off
cd /d "%~dp0"
echo.
echo === IVANA GitHub ===
echo Repo: ivanaThePro/my_cv_and_jobseeking_app
echo.
echo Hvis push feiler: kjør FIX_IVANA_PUSH.bat i Downloads-mappen.
echo.
git push --force-with-lease -u origin main
echo.
if errorlevel 1 (
  echo Push feilet - bruk FIX_IVANA_PUSH.bat for token-hjelp.
) else (
  echo Ferdig - Ivana-kode er pa GitHub.
)
pause
