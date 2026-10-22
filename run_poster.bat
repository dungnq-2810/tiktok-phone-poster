@echo off
chcp 65001 >nul
cd /d %~dp0
where python >nul 2>nul || (echo Chua co Python - cai Python 3.11+ truoc. & pause & exit /b 1)
python -c "import uiautomator2" 2>nul || python -m pip install -r requirements.txt
echo.
echo === Dang video TikTok bang dien thoai ===
echo Thu muc hang doi: %CD%\outbox
echo Chay thu (dry-run) truoc: them --dry-run o dong lenh neu go tay.
echo.
python phone_poster.py --dir "%CD%\outbox" %*
pause
