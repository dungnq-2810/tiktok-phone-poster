@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Tu cap nhat code moi nhat tu GitHub (neu thu muc la git repo va co git).
REM Neu pull that bai (khong co mang, file sua tay xung dot...) thi van chay
REM ban hien co, khong dung lai.
if exist ".git" (
  where git >nul 2>nul
  if not errorlevel 1 (
    echo [Update] Dang pull code moi nhat tu GitHub...
    git pull --ff-only
    if errorlevel 1 echo [Update] git pull that bai - van chay ban hien co.
  )
)
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
echo  5. Xem cac acc da dang nhap trong TikTok
echo  6. Doi acc thu (trong cac acc da dang nhap)
echo  7. Chuyen sang ADB qua Wi-Fi (rut cap duoc)
echo  8. Config acc theo ngach (lay danh sach truoc)
echo  9. Mo giao dien GUI
echo 10. Nuoi TAT CA acc - moi acc ~10p, theo ngach da config
echo 11. Quet cay UI man hinh hien tai (luu file map ui_map)
echo  0. Thoat
echo =============================================
set /p "CH=Chon so roi bam Enter: "
if "%CH%"=="1" goto M1
if "%CH%"=="2" goto M2
if "%CH%"=="3" goto M3
if "%CH%"=="4" goto M4
if "%CH%"=="5" goto M5
if "%CH%"=="6" goto M6
if "%CH%"=="7" goto M7
if "%CH%"=="8" goto M8
if "%CH%"=="9" goto M9
if "%CH%"=="10" goto M10
if "%CH%"=="11" goto M11
if "%CH%"=="0" goto END
goto MENUDONE

:M1
"%PY%" phone_poster.py --init
goto MENUDONE

:M2
"%PY%" test_open_scroll.py
goto MENUDONE

:M3
"%PY%" phone_poster.py --known-accounts
set /p "ACC=Dang vao acc nao? (nhap username, de trong = acc dang mo): "
if "%ACC%"=="" "%PY%" phone_poster.py --dir "%CD%\outbox" --dry-run
if not "%ACC%"=="" "%PY%" phone_poster.py --dir "%CD%\outbox" --dry-run --account "%ACC%"
goto MENUDONE

:M4
"%PY%" phone_poster.py --known-accounts
set /p "ACC=Dang vao acc nao? (nhap username, de trong = acc dang mo): "
if "%ACC%"=="" "%PY%" phone_poster.py --dir "%CD%\outbox"
if not "%ACC%"=="" "%PY%" phone_poster.py --dir "%CD%\outbox" --account "%ACC%"
goto MENUDONE

:M5
"%PY%" phone_poster.py --list-accounts
goto MENUDONE

:M6
"%PY%" phone_poster.py --known-accounts
set /p "ACC=Doi sang acc nao? (nhap username): "
if "%ACC%"=="" goto MENUDONE
"%PY%" phone_poster.py --switch-to "%ACC%"
goto MENUDONE

:M7
"%PY%" phone_poster.py --wifi
goto MENUDONE

:M8
"%PY%" phone_poster.py --config-niches
goto MENUDONE

:M9
call gui.bat
goto MENUDONE

:M10
"%PY%" phone_poster.py --nurture-all
goto MENUDONE

:M11
set /p "SCAN=Ten man hinh (vd feed, profile, sheet, gallery, editor, caption): "
if "%SCAN%"=="" goto MENUDONE
"%PY%" phone_poster.py --scan-ui "%SCAN%"
goto MENUDONE

:MENUDONE
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
