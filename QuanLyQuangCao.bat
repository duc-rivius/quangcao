@echo off
rem Mo app Quan ly quang cao (cua so rieng; dong cua so la tat)
start "" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0quanly\ads-server.ps1" %*
