@echo off
chcp 65001 >nul
cd /d %~dp0
set PY=.venv\Scripts\python.exe

rem --- Lan chay dau: tu tao moi truong rieng + cai thu vien ---
if not exist %PY% (
  echo [Setup] Dang tao moi truong Python rieng (.venv)...
  where python >nul 2>nul || (echo Loi: chua co Python. Cai Python 3.11+ truoc, nho tick "Add python.exe to PATH". & pause & exit /b 1)
  python -m venv .venv || (echo Loi: tao .venv that bai. & pause & exit /b 1)
  %PY% -m pip install --upgrade pip >nul 2>nul
  %PY% -m pip install -r requirements.txt || (echo Loi: cai thu vien that bai. & pause & exit /b 1)
  echo [Setup] Xong.
)

rem --- Neu co tham so thi chay thang phone_poster.py voi tham so do ---
if not "%~1"=="" (
  %PY% phone_poster.py %*
  pause
  exit /b
)

:menu
echo.
echo ============ TikTok Phone Poster ============
echo  1. Cai agent len dien thoai (lam 1 lan, cam USB)
echo  2. Test: mo TikTok + luot feed
echo  3. Dang thu - dry-run (khong bam nut Dang)
echo  4. Dang that (video trong thu muc outbox)
echo  0. Thoat
echo =============================================
set /p CH=Chon so roi bam Enter:
if "%CH%"=="1" %PY% phone_poster.py --init
if "%CH%"=="2" %PY% test_open_scroll.py
if "%CH%"=="3" %PY% phone_poster.py --dir "%CD%\outbox" --dry-run
if "%CH%"=="4" %PY% phone_poster.py --dir "%CD%\outbox"
if "%CH%"=="0" exit /b
echo.
pause
goto menu
