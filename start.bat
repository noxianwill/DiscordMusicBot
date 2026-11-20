@echo off
title Discord Music Bot + Web UI Launcher
echo ========================================================
echo   Discord Music Bot + Web UI Launcher (Windows)
echo ========================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH!
    echo Please install Python 3.10+ from https://python.org
    echo Make sure to check the box: "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: 2. Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in your system PATH!
    echo Please install Node.js LTS from https://nodejs.org
    pause
    exit /b 1
)

:: 3. Check FFmpeg
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg was not found in your system PATH!
    echo Audio playback will fail without FFmpeg.
    echo Install in PowerShell with: winget install Gyan.FFmpeg
    echo.
)

:: 4. Setup Python Virtual Environment
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating Python virtual environment (venv)...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: 5. Setup Web UI Dependencies
if exist "web" (
    if not exist "web\node_modules" (
        echo [*] Installing Web UI npm dependencies...
        cd web
        call npm install
        cd ..
    )
)

:: 6. Setup Configuration Files if missing
if not exist "config.txt" (
    if exist "config.example.txt" (
        copy config.example.txt config.txt
        echo [!] Created config.txt from template. Please edit config.txt with your BOT_TOKEN!
    )
)

if exist "web" (
    if not exist "web\.env" (
        if exist "web\.env.example" (
            copy web\.env.example web\.env
            echo [!] Created web\.env from template. Please edit web\.env with your DISCORD_CLIENT_ID!
        )
    )
)

:: 7. Start Web UI in separate window
if exist "web" (
    echo [*] Starting Web UI Dashboard on port 5000...
    start "Discord Music Bot - Web UI" cmd /k "cd web && npm start"
)

:: 8. Start Python Bot
echo [*] Starting Python Music Bot Launcher...
python launcher.py

pause

