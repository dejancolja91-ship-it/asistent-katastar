@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -c "import requests" 2>nul || (
    echo Instaliram biblioteku requests...
    py -3 -m pip install --user requests
  )
  start "" pyw -3 "%~dp0asistent_katastar.py"
) else (
  python -c "import requests" 2>nul || (
    echo Instaliram biblioteku requests...
    python -m pip install --user requests
  )
  start "" pythonw "%~dp0asistent_katastar.py"
)
