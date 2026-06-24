@echo off
cd /d "%~dp0"
echo === Daily job pipeline ===
echo.

echo [1/2] Refresh job cache (all free DE sources + Apify if configured)...
python jobsearch\jobsearch.py --refresh-cache
if errorlevel 1 (
    echo Refresh failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Score jobs (uses cache, needs MISTRAL_API_KEY)...
python jobsearch\jobsearch.py --use-cache --max-jobs 100 --min-score 55 --dry-run
if errorlevel 1 (
    echo Scoring failed.
    pause
    exit /b 1
)

echo.
echo Done. Open http://127.0.0.1:8000/ and check Apply list.
pause
