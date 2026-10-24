@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 goto HAVEPY
echo Khong tim thay python. Cai Python 3.11+ tu python.org roi chay lai file nay.
pause
exit /b 1
:HAVEPY
python -c "import tkinter" >nul 2>nul
if not errorlevel 1 goto HAVETK
echo Python cua ban thieu tkinter - thu vien giao dien.
echo Cai lai Python tu python.org voi tuy chon mac dinh roi chay lai file nay.
pause
exit /b 1
:HAVETK
python gui.py
pause
