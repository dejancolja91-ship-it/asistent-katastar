@echo off
rem Preuzima najnoviju verziju programa sa GitHub-a (program to radi i sam pri pokretanju).
setlocal
cd /d "%~dp0"
if not exist .git (echo Folder jos nije povezan sa GitHub-om: pokreni povezi_sa_github.bat & pause & exit /b 1)
if not exist rezerve mkdir rezerve
for /f %%h in ('git rev-parse --short HEAD') do set STARI=%%h
git fetch -q origin main
for /f %%h in ('git rev-parse --short origin/main') do set NOVI=%%h
if "%STARI%"=="%NOVI%" (echo Vec je najnovija verzija. & pause & exit /b 0)
copy /y asistent_katastar.py "rezerve\asistent_katastar_%STARI%.py" >nul
git pull --ff-only
if errorlevel 1 (echo Preuzimanje nije uspelo, vidi poruku iznad. & pause & exit /b 1)
echo.
git log --oneline -3
echo Gotovo. Stara verzija je u rezerve\asistent_katastar_%STARI%.py
pause
