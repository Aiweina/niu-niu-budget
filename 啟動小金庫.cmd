@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python investment_server.py
) else (
  py investment_server.py
)
if errorlevel 1 (
  echo.
  echo 無法啟動小金庫，請確認電腦已安裝 Python。
  pause
)
