@echo off
title Telegram Orders Bot
cd /d "%~dp0"
echo Starting Telegram Orders Bot...
py -m bot.main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bot stopped with error.
    pause
)
