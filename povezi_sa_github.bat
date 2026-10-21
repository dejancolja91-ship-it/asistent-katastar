@echo off
rem JEDNOM: povezuje ovaj folder sa privatnim GitHub repozitorijumom asistent-katastar.
rem Baza, rezerve, zadaci, izvodi i PDF se ne diraju (nisu u repozitorijumu).
setlocal
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (echo Git nije instaliran. U cmd pokreni: winget install --id Git.Git -e & pause & exit /b 1)
if exist .git (echo Folder je vec povezan. & call "%~dp0preuzmi_sa_github.bat" & exit /b 0)
if not exist rezerve mkdir rezerve
copy /y asistent_katastar.py "rezerve\asistent_katastar_pre_github.py" >nul
git init -q
git remote add origin https://github.com/dejancolja91-ship-it/asistent-katastar.git
git fetch -q origin main
if errorlevel 1 (echo Preuzimanje sa GitHub-a nije uspelo, vidi poruku iznad. & rmdir /s /q .git & pause & exit /b 1)
git checkout -q -f -B main origin/main
if errorlevel 1 (echo Povezivanje nije uspelo, vidi poruku iznad. & pause & exit /b 1)
git branch -q -u origin/main
echo.
git log --oneline -3
git status --short
echo Gotovo. Prethodna verzija je u rezerve\asistent_katastar_pre_github.py
echo Od sada program pri svakom pokretanju sam preuzima nove verzije.
pause
