# -*- coding: utf-8 -*-
"""
main.py
=======
Point d'entrée du programme :      python main.py

Synthèse de filtres de Butterworth réalisés avec des cellules de Sallen & Key
à gain unité.

Organisation du programme :
    moteur.py     les calculs (étapes 1 à 6 de la méthode de synthèse),
                  utilisable seul :  python moteur.py
    graphes.py    les dessins : diagrammes de Bode, schémas, formules
    interface.py  la fenêtre principale et les interactions, avec :
        commun.py    couleurs, polices, numéro de version, préférences
        saisie.py    la colonne de saisie (type, gabarit, séries)
        panneaux.py  les résultats (bandeau, onglets, accueil)
        aide.py      le menu Aide, la visite guidée, la fenêtre du cours
        mise_a_jour.py  les nouvelles versions (recherche, installation)
    compte_rendu.py  le compte rendu PDF (menu Fichier)
    netlist.py    les netlists LTspice et PSpice (onglet Câblage)
    guide.py      le contenu du cours « Comprendre Sallen & Key » (F2)
"""

import os
import sys
import tempfile


def journal_sans_console() -> None:
    """Programme installé (construit sans console) : sys.stdout et sys.stderr valent None.
    Les messages d'erreur sont alors écrits dans un fichier journal du dossier temporaire
    (%TEMP%\\FiltresButterworth.log sous Windows)."""
    if sys.stdout is None or sys.stderr is None:
        journal = open(os.path.join(tempfile.gettempdir(), "FiltresButterworth.log"), "a",
                       encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or journal
        sys.stderr = sys.stderr or journal


def garder_cache_matplotlib() -> None:
    """Programme installé : matplotlib garde sa liste des polices d'un lancement à l'autre.

    PyInstaller la place sinon dans un dossier temporaire, effacé à chaque fermeture :
    matplotlib referait alors, à chaque lancement, l'inventaire des polices de l'ordinateur
    (plusieurs secondes sous Windows). Le programme installé ne bouge pas, les chemins des
    polices restent valables ; s'il est déplacé, matplotlib refait la liste de lui-même."""
    if not getattr(sys, "frozen", False):
        return
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.join(os.path.expanduser("~"), ".cache"))
    dossier = os.path.join(base, "FiltresButterworth", "matplotlib")
    try:
        os.makedirs(dossier, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = dossier
    except OSError:
        pass                    # dossier temporaire de PyInstaller : plus lent, mais sans risque


def ecran_de_demarrage():
    """Programme installé : l'écran de démarrage (image affichée par PyInstaller dès le
    lancement, avant même Python) ; None sinon. Le texte en bas de l'image dit ce qui se
    passe ; l'écran se ferme quand la fenêtre du programme est prête."""
    try:
        import pyi_splash          # module fourni par PyInstaller seulement (option Splash)
        return pyi_splash
    except ImportError:
        return None


def preparer(ecran) -> None:
    """« FiltresButterworth.exe --preparer », lancé par l'installateur : prépare à l'avance ce
    que matplotlib construit au tout premier lancement (liste des polices de l'ordinateur, qui
    peut prendre plusieurs secondes sous Windows). Le premier vrai lancement est ainsi rapide."""
    if ecran is not None:
        ecran.update_text("Préparation du premier lancement…")
    import matplotlib
    matplotlib.use("Agg")
    import graphes
    graphes.configurer_matplotlib()                     # liste des polices (mise en cache)
    graphes.formule_png(r"H(p) = \dfrac{1}{1 + 2m\,p + p^2}")   # polices des formules


if __name__ == "__main__":
    journal_sans_console()
    garder_cache_matplotlib()                  # avant tout import de matplotlib
    ecran = ecran_de_demarrage()
    if "--preparer" in sys.argv[1:]:
        try:
            preparer(ecran)
        finally:
            if ecran is not None:
                ecran.close()
        sys.exit(0)
    if ecran is not None:
        ecran.update_text("Chargement…")
    from interface import lancer
    # Un fichier .filtre peut être donné au lancement (double-clic dans l'Explorateur)
    lancer(sys.argv[1] if len(sys.argv) > 1 else None, pret=ecran.close if ecran is not None else None)
