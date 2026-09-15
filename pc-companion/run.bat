@echo off
cd /d "%~dp0"
echo ========================================================
echo   InkLife 3D Companion Station (Raylib Native Engine)
echo ========================================================
echo Starting InkLife Companion Station...
uv run companion.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to run with uv. Falling back to local python environment...
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python.exe companion.py %*
    ) else (
        python companion.py %*
    )
)
pause
