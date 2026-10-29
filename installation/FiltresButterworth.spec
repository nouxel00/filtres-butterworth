# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# Recette PyInstaller : construit le programme autonome dist/FiltresButterworth/
# (FiltresButterworth.exe avec son icône, Python et les bibliothèques inclus).
#
# À lancer depuis le dossier du programme :
#     pyinstaller --noconfirm installation/FiltresButterworth.spec
# (construire_windows.bat le fait automatiquement.)
# =============================================================================

import os

RACINE = os.path.dirname(SPECPATH)            # SPECPATH : dossier de ce fichier (installation/)
ICONE = os.path.join(RACINE, "icone.ico")

a = Analysis(
    [os.path.join(RACINE, "main.py")],
    pathex=[RACINE],
    # Fichiers lus par le programme (voir commun.chemin_ressource) ; le LISEZMOI sert au
    # menu Aide > Mode d'emploi
    datas=[(ICONE, "."), (os.path.join(RACINE, "icone.png"), "."), (os.path.join(RACINE, "LISEZMOI.txt"), ".")],
    # Visite guidée : photo de la fenêtre (Pillow) affichée dans Tk. PyInstaller écarte d'office
    # le lien de Pillow avec Tkinter : il est ajouté ici.
    hiddenimports=["PIL.ImageGrab", "PIL.ImageTk", "PIL._tkinter_finder"],
    # Bibliothèques inutiles au programme : le paquet reste plus léger
    excludes=["scipy", "pandas", "IPython", "jupyter", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "wx", "gi"],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Écran de démarrage : affiché par le lanceur dès le double-clic, avant le chargement de Python
# et des bibliothèques ; main.py écrit son texte en bas, puis le ferme quand la fenêtre est prête.
splash = Splash(
    os.path.join(SPECPATH, "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(148, 280),
    text_size=10,
    text_color="#4A5A6A",
    text_default="Chargement…",
    minify_script=True,
    always_on_top=False,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    exclude_binaries=True,
    name="FiltresButterworth",
    console=False,          # programme fenêtré : pas de fenêtre noire de console
    icon=ICONE,             # icône du fichier .exe (Explorateur, raccourcis, barre des tâches)
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    name="FiltresButterworth",
    upx=False,
)
