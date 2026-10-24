@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Khong tim thay python. Cai Python 3.11+ tu python.org roi chay lai file nay.
  pause
  exit /b 1
)
python -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo Python cua ban thieu tkinter (thu vien giao dien).
  echo Cai lai Python tu python.org voi tuy chon mac dinh roi chay lai file nay.
  pause
  exit /b 1
)
python gui.py
pause
