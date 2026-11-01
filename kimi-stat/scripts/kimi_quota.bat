@echo off
chcp 65001 >nul

pushd %~dp0

py kimi_quota.py -f ..\assets\keys.txt --html %*

pause
