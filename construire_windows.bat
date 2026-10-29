@echo off
chcp 65001 >nul
rem ===========================================================================
rem  construire_windows.bat : construit le logiciel pour Windows.
rem
rem    dist\FiltresButterworth\FiltresButterworth.exe    programme autonome, avec son icône
rem    dist\Installer_FiltresButterworth_2.0.exe         installateur (si Inno Setup 6 est installé)
rem
rem  À lancer une seule fois, par double-clic, sur un PC Windows où Python 3 est
rem  installé (python.org). La première fois, une connexion Internet est nécessaire.
rem ===========================================================================
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PYTHON=py -3") else (set "PYTHON=python")

echo.
echo [1/4] Environnement Python de construction...
if not exist ".venv-construction\Scripts\python.exe" %PYTHON% -m venv .venv-construction
if not exist ".venv-construction\Scripts\python.exe" goto erreur
set "PY=.venv-construction\Scripts\python.exe"

echo [2/4] Bibliothèques : numpy, matplotlib, pillow, pyinstaller...
"%PY%" -m pip install --upgrade pip
rem Versions vérifiées ensemble, les mêmes que pour la construction sur GitHub
"%PY%" -m pip install -r installation\requirements-construction.txt
if errorlevel 1 goto erreur

echo [3/4] Icône et programme autonome...
"%PY%" installation\creer_icones.py
if errorlevel 1 goto erreur
"%PY%" -m PyInstaller --noconfirm --clean installation\FiltresButterworth.spec
if errorlevel 1 goto erreur

echo [4/4] Installateur...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto sans_inno
"%ISCC%" installation\installateur.iss
if errorlevel 1 goto erreur
echo.
echo Terminé. L'installateur à partager est dans le dossier dist :
rem Le plus récent (son nom contient le numéro de version, voir installation\installateur.iss)
for /f "delims=" %%f in ('dir /b /o-d "dist\Installer_FiltresButterworth_*.exe"') do (
  echo     dist\%%f
  goto fin
)
goto fin

:sans_inno
echo.
echo Inno Setup 6 n'est pas installé : seul le programme autonome est prêt,
echo dans le dossier dist\FiltresButterworth. Pour obtenir l'installateur,
echo installez Inno Setup 6 depuis https://jrsoftware.org/isdl.php puis relancez ce fichier.
goto fin

:erreur
echo.
echo La construction a échoué : lisez le message ci-dessus.
pause
exit /b 1

:fin
echo.
pause
exit /b 0
