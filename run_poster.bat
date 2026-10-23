@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TikTok Phone Poster

set "PY=.venv\Scripts\python.exe"

if exist "%PY%" goto READY

echo [Setup] Lan chay dau tien - dang cai dat...
where python >nul 2>nul
if errorlevel 1 goto NOPYTHON
python -m venv .venv
if errorlevel 1 goto VENVFAIL
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto PIPFAIL
echo [Setup] Cai dat xong.

:READY
if not "%~1"=="" goto RUNARGS

:MENU
echo.
echo ============ TikTok Phone Poster ============
echo  1. Cai agent len dien thoai (lam 1 lan, cam USB)
echo  2. Test: mo TikTok + luot feed
echo  3. Dang thu - dry-run (khong bam nut Dang)
echo  4. Dang that (video trong thu muc outbox)
echo  0. Thoat
echo =============================================
set /p "CH=Chon so roi bam Enter: "
if "%CH%"=="1" "%PY%" phone_poster.py --init
if "%CH%"=="2" "%PY%" test_open_scroll.py
if "%CH%"=="3" "%PY%" phone_poster.py --dir "%CD%\outbox" --dry-run
if "%CH%"=="4" "%PY%" phone_poster.py --dir "%CD%\outbox"
if "%CH%"=="0" goto END
echo.
pause
goto MENU

:RUNARGS
"%PY%" phone_poster.py %*
goto END

:NOPYTHON
echo Loi: May chua co Python. Cai Python 3.11+ tai python.org, nho tick o "Add python.exe to PATH", roi chay lai file nay.
goto END

:VENVFAIL
echo Loi: Tao moi truong ao (.venv) that bai.
goto END

:PIPFAIL
echo Loi: Cai thu vien that bai - kiem tra ket noi mang roi chay lai.
goto END

:END
echo.
pause
