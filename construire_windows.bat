@echo off
setlocal
set "PAGE=850"
for /f "tokens=2 delims=:" %%c in ('chcp ^<nul') do for %%d in (%%c) do set "PAGE=%%d"
set "PAGE=%PAGE:.=%"
chcp 65001 >nul <nul
rem ===========================================================================
rem  construire_windows.bat : construit le logiciel pour Windows.
rem
rem    dist\FiltresButterworth\FiltresButterworth.exe    programme autonome, avec son icône
rem    dist\Installer_FiltresButterworth_2.0.exe         installateur (avec Inno Setup 7 ou 6)
rem
rem  À lancer par double-clic, depuis le dossier du programme décompressé, sur un
rem  PC Windows avec Python 3.12, 3.13, 3.14 ou 3.15 (python.org). La première fois,
rem  une connexion Internet est nécessaire. S'il manque Python ou Inno Setup, le
rem  fichier propose de les installer (winget). À la fin, le dossier dist s'ouvre
rem  dans l'Explorateur, l'installateur sélectionné.
rem ===========================================================================
rem Messages en UTF-8 (accents) ; la page de code d'origine (PAGE) revient à la fin.
rem chcp est lancé avec <nul : sinon, il lit l'entrée standard et les réponses
rem préparées dans un fichier (construire_windows.bat < reponses.txt) seraient perdues.
cd /d "%~dp0"

rem Lancé depuis le .zip sans l'avoir décompressé, ce fichier est seul dans un
rem dossier temporaire : rien ne peut être construit.
if exist "main.py" if exist "installation\installateur.iss" goto dossier_ok
echo.
echo Les fichiers du programme ne sont pas à côté de construire_windows.bat.
echo Décompressez d'abord le fichier .zip (clic droit, puis « Extraire tout »),
echo puis lancez construire_windows.bat depuis le dossier décompressé.
goto arret
:dossier_ok
echo Dossier du programme : %CD%

echo.
echo [1/4] Python et environnement de construction...
call :chercher_python
if defined PYTHON goto python_trouve
echo.
echo Python 3.12, 3.13, 3.14 ou 3.15 est nécessaire : les bibliothèques de la
echo construction (installation\requirements-construction.txt) l'exigent.
call :proposer_winget "Python 3.13" Python.Python.3.13
if errorlevel 1 goto python_manquant
call :chercher_python
if defined PYTHON goto python_trouve
:python_manquant
echo.
echo Installez Python 3.13 depuis https://www.python.org/downloads/windows/
echo en cochant « Add python.exe to PATH », puis relancez ce fichier.
goto arret
:python_trouve
%PYTHON% --version
set "PY=.venv-construction\Scripts\python.exe"
rem Environnement d'un essai précédent fait avec un Python trop ancien, ou
rem désinstallé depuis : il est refait.
if not exist "%PY%" goto creer_environnement
"%PY%" -c "import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 15) else 1)" <nul >nul 2>nul
if not errorlevel 1 goto environnement_pret
echo L'environnement .venv-construction d'un essai précédent est refait.
rmdir /s /q ".venv-construction"
:creer_environnement
%PYTHON% -m venv .venv-construction
if not exist "%PY%" goto echec
:environnement_pret

echo [2/4] Bibliothèques : numpy, matplotlib, pillow, pyinstaller...
"%PY%" -m pip install --upgrade pip
rem Versions vérifiées ensemble, les mêmes que pour la construction sur GitHub
"%PY%" -m pip install -r installation\requirements-construction.txt
if errorlevel 1 goto echec

echo [3/4] Icône et programme autonome (quelques minutes)...
"%PY%" installation\creer_icones.py
if errorlevel 1 goto echec
"%PY%" -m PyInstaller --noconfirm --clean installation\FiltresButterworth.spec
if errorlevel 1 goto echec

echo [4/4] Installateur...
call :chercher_inno
if defined ISCC goto compiler
echo.
echo Inno Setup, gratuit, crée l'installateur : il n'est pas installé sur ce PC.
call :proposer_winget "Inno Setup 7" JRSoftware.InnoSetup.7
if errorlevel 1 goto sans_inno
call :chercher_inno
if not defined ISCC goto sans_inno
:compiler
echo Inno Setup : %ISCC%
"%ISCC%" installation\installateur.iss
if errorlevel 1 goto echec
rem Le plus récent (son nom contient le numéro de version, voir installation\installateur.iss)
for /f "delims=" %%f in ('dir /b /o-d "dist\Installer_FiltresButterworth_*.exe"') do (
  set "INSTALLATEUR=%%f"
  goto installateur_pret
)
goto echec
:installateur_pret
echo.
echo Terminé. L'installateur à partager est prêt :
echo     %CD%\dist\%INSTALLATEUR%
echo Le dossier dist s'ouvre dans l'Explorateur, l'installateur sélectionné.
explorer /select,"%CD%\dist\%INSTALLATEUR%"
goto fin

:sans_inno
echo.
echo Le programme autonome est prêt (dossier dist\FiltresButterworth), mais pas
echo l'installateur : il faut Inno Setup. Installez Inno Setup 7, gratuit :
echo     https://jrsoftware.org/isdl.php   (fichier innosetup-...-x64.exe)
echo puis relancez ce fichier ; la deuxième fois, la construction est plus rapide.
goto fin

:echec
echo.
echo La construction a échoué : lisez le message ci-dessus.
goto arret

:arret
echo.
chcp %PAGE% >nul <nul
pause
exit /b 1

:fin
echo.
chcp %PAGE% >nul <nul
pause
exit /b 0


rem ===========================================================================
rem  Sous-programmes
rem ===========================================================================

:chercher_python
rem PYTHON : commande d'un Python 3.12 à 3.15, versions prises en charge par les
rem bibliothèques de requirements-construction.txt (à revoir si elles changent),
rem sinon vide. D'abord le lanceur py (Python de python.org), puis python du PATH,
rem puis un Python tout juste installé pour soi seul (pas encore dans le PATH).
rem Le gestionnaire d'installation de Python (py) ne doit rien installer ici.
set "PYTHON="
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
for %%v in (3.13 3.12 3.14 3.15) do if not defined PYTHON call :essayer_python py -%%v
if not defined PYTHON call :essayer_python python
for %%v in (313 312 314 315) do if not defined PYTHON if exist "%LocalAppData%\Programs\Python\Python%%v\python.exe" call :essayer_python "%LocalAppData%\Programs\Python\Python%%v\python.exe"
exit /b 0

:essayer_python
%* -c "import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 15) else 1)" <nul >nul 2>nul
if not errorlevel 1 set "PYTHON=%*"
exit /b 0

:chercher_inno
rem ISCC : compilateur d'Inno Setup 7 ou 6, sinon vide. D'abord les dossiers
rem habituels (édition 64 ou 32 bits, installée pour tous ou pour soi seul), puis
rem le dossier noté par l'installation d'Inno Setup (autre dossier choisi), puis
rem le PATH.
set "ISCC="
for %%d in ("%ProgramFiles%\Inno Setup 7" "%ProgramFiles(x86)%\Inno Setup 7" "%LocalAppData%\Programs\Inno Setup 7" "%LocalAppData%\Programs\Inno Setup 7 (32-bit)" "%ProgramFiles(x86)%\Inno Setup 6" "%ProgramFiles%\Inno Setup 6" "%LocalAppData%\Programs\Inno Setup 6") do if not defined ISCC if exist "%%~d\ISCC.exe" set "ISCC=%%~d\ISCC.exe"
set "CLE=SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
set "CLE32=SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
for %%k in ("HKLM\%CLE%\Inno Setup 7_is1" "HKLM\%CLE32%\Inno Setup 7 (32-bit)_is1" "HKCU\%CLE%\Inno Setup 7_is1" "HKCU\%CLE%\Inno Setup 7 (32-bit)_is1" "HKLM\%CLE32%\Inno Setup 6_is1" "HKCU\%CLE%\Inno Setup 6_is1") do if not defined ISCC call :inno_registre %%k
if not defined ISCC for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%i"
exit /b 0

:inno_registre
for /f "tokens=2,*" %%a in ('reg query "%~1" /v InstallLocation 2^>nul ^| findstr /i /c:"InstallLocation"') do if exist "%%~b\ISCC.exe" for %%p in ("%%~b\ISCC.exe") do set "ISCC=%%~fp"
exit /b 0

:proposer_winget
rem Propose d'installer un logiciel avec winget, pour l'utilisateur seul (sans
rem droits administrateur) : nom affiché, puis identifiant winget. Code 0 si
rem l'installation a été lancée, 1 sinon (refus, ou winget absent).
where winget >nul 2>nul
if errorlevel 1 exit /b 1
set "REPONSE="
set /p "REPONSE=Installer %~1 maintenant (winget, quelques minutes) ? O/N : "
if /i "%REPONSE%"=="oui" set "REPONSE=O"
if /i not "%REPONSE%"=="O" exit /b 1
winget install --id %~2 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements
exit /b 0
