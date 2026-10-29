# -*- coding: utf-8 -*-
"""
creer_icones.py
===============
Crée les fichiers d'icône du programme à partir du dessin de graphes.icone_png :

    icone.ico   Windows : sept tailles (16 à 256 pixels), pour le fichier .exe,
                les raccourcis, la barre des tâches et l'installateur
    icone.png   256 pixels, pour Linux ou un document

Les fichiers sont écrits dans le dossier du programme (au-dessus de ce dossier).
Utilisation :   python installation/creer_icones.py
"""

import io
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)

from PIL import Image          # noqa: E402  (fourni avec matplotlib)

import graphes as gr           # noqa: E402

TAILLES = [16, 24, 32, 48, 64, 128, 256]


def creer_icones() -> None:
    """Dessine chaque taille séparément (traits nets en petit) puis assemble le .ico."""
    images = {t: Image.open(io.BytesIO(gr.icone_png(t))).convert("RGBA") for t in TAILLES}
    grande = images[256]
    grande.save(os.path.join(RACINE, "icone.ico"), format="ICO", sizes=[(t, t) for t in TAILLES],
                append_images=[images[t] for t in TAILLES if t != 256])
    grande.save(os.path.join(RACINE, "icone.png"))
    print("Icônes créées : icone.ico et icone.png")


if __name__ == "__main__":
    creer_icones()
