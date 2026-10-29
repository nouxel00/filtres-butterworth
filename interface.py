# -*- coding: utf-8 -*-
"""
interface.py
============
Fenêtre principale du programme (Tkinter).

    ┌───────────────┬───────────────────────────────────────────────────┐
    │ Saisie        │ Résumé : ordre, k, ε, référence, montage          │
    │  type         ├───────────────────────────────────────────────────┤
    │  gabarit      │ Bode normalisé | Bode réel | Étapes du calcul |   │
    │  référence    │ Composants | Câblage                              │
    │  valeurs (E…) │ (accueil tant qu'aucun filtre n'est calculé)      │
    ├───────────────┤                                                   │
    │ [Calculer]    │                                                   │
    │ état          │                                                   │
    └───────────────┴───────────────────────────────────────────────────┘

Les calculs sont faits par moteur.py et les dessins par graphes.py :
ce fichier ne s'occupe que de l'affichage et des interactions.
"""

from __future__ import annotations

import base64
import io
import itertools
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

import matplotlib
import numpy as np
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg   # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg       # noqa: E402
from matplotlib.figure import Figure                              # noqa: E402

import graphes as gr                                              # noqa: E402
import guide                                                      # noqa: E402
import moteur as mt                                               # noqa: E402


# =============================================================================
# Couleurs et polices
# =============================================================================

UI = {
    "plan": "#F3F5F8",          # fond du panneau de saisie
    "surface": "#FFFFFF",       # fond des résultats
    "encre": "#1B2A3A",         # texte principal
    "encre2": "#4A5A6A",        # texte secondaire
    "discret": "#5B6676",       # légendes (contraste suffisant même en petit)
    "trait": "#E3E8EE",         # filets de séparation
    "trait_fort": "#C9D2DC",    # bordures des champs
    "accent": "#1F5FBF",        # actions et sélection
    "accent_survol": "#184C99",
    "accent_occupe": "#7D9FD6",  # bouton pendant un calcul
    "accent_doux": "#EAF1FB",
    "erreur": "#B42318",
    "erreur_doux": "#FEF0EE",
    "succes": "#0A7A33",
    "succes_doux": "#E8F6EC",
    "alerte": "#7A5200",
    "alerte_doux": "#FFF5DB",
}

# Version du programme (à reporter dans installation/installateur.iss)
VERSION = "2.0"
DEPOT = "https://github.com/nouxel00/filtres-butterworth"   # code source (licence MIT)

# Aide affichée sous le gabarit selon le champ actif.
AIDE = {
    "fp": "Limite de la bande passante : le gain doit y rester au-dessus de Gp.",
    "fa": "Début de la bande atténuée : le gain doit y rester sous Ga.",
    "fp_moins": "Limite basse de la bande passante [fp− ; fp+].",
    "fp_plus": "Limite haute de la bande passante [fp− ; fp+].",
    "fa_moins": "Limite de la bande atténuée côté basses fréquences.",
    "fa_plus": "Limite de la bande atténuée côté hautes fréquences.",
    "Gp": "Gain minimal en bande passante (−3 dB en général).",
    "Ga": "Gain maximal en bande atténuée (atténuation A = −Ga).",
    "R0": "Résistance des cellules passe-bas. C0 s'en déduit par R0·C0·ω = 1.",
    "C0": "Condensateur des cellules passe-haut. R0 s'en déduit par R0·C0·ω = 1.",
}
AIDE_DEFAUT = "Saisie libre : 2400, 2,4k, 2.4 kHz, 10n, 4k7…"
UNITES = {"Gp": "dB", "Ga": "dB", "R0": "Ω", "C0": "F"}

# Choix des séries des composants (listes déroulantes de la colonne de saisie)
OPTIONS_SERIES = [("", "Calculées"), ("E6", "E6 (±20 %)"), ("E12", "E12 (±10 %)"), ("E24", "E24 (±5 %)")]

# Filtre neuf : le gabarit est vide ; seuls les composants de référence, choisis librement,
# reçoivent une valeur courante (modifiable).
REFERENCES_DEPART = {"R0": "10k", "C0": "10n"}


def champs_du_type(t: str) -> List[str]:
    """Champs à remplir pour un type de filtre : gabarit, puis composants de référence."""
    return (list(mt.FREQUENCES[t]) + ["Gp", "Ga"] + (["R0"] if t in ("PB", "PM") else [])
            + (["C0"] if t in ("PH", "PM") else []))


def valeurs_de_depart() -> Dict[str, Dict[str, str]]:
    """Champs d'un filtre neuf, pour chaque type : gabarit vide, R0 et C0 proposés."""
    return {t: {nom: REFERENCES_DEPART.get(nom, "") for nom in champs_du_type(t)} for t in mt.NOMS_TYPES}


def lire_ajustements(liste, config) -> Tuple[Tuple[mt.Ajustement, ...], Optional[tuple]]:
    """Valeurs ajustées par la correction du gabarit, lues dans un fichier .filtre ou dans la
    séance gardée, et vérifiées une à une : (ajustements, séries, options et calcul pour
    lesquels elles ont été trouvées). Un contenu illisible n'en donne aucune."""
    try:
        R, C, associations, pont, signature = config
        if (R not in ("", "E6", "E12", "E24") or C not in ("", "E6", "E12", "E24")
                or not isinstance(associations, bool) or not isinstance(pont, bool)
                or not isinstance(signature, str)):
            return (), None
        ajustements = []
        for cellule, cle, calculee, elements in liste:
            elements = tuple(float(x) for x in elements)
            if (not isinstance(cellule, str) or cle not in ("R1", "R2", "R3", "C1", "C2", "Ra", "Rb")
                    or not float(calculee) > 0 or not 1 <= len(elements) <= 2 or min(elements) <= 0):
                return (), None
            ajustements.append(mt.Ajustement(cellule, cle, float(calculee), elements))
        return tuple(ajustements), (R, C, associations, pont, signature)
    except (TypeError, ValueError):
        return (), None

# Infobulles (survol de la souris) : types de filtre, paramètres du gabarit, séries, onglets.
BULLE_SERIES = ("Calculées : valeurs exactes du calcul.\n"
                + "\n".join(f"{nom} ({mt.TOLERANCE_SERIE[nom]}) : "
                            + ("\u00a0– ".join(mt.fmt_compact(v) for v in valeurs) if len(valeurs) <= 12
                               else f"{len(valeurs)} valeurs par décade")
                            for nom, valeurs in mt.SERIES_E.items())
                + "\nLes valeurs choisies servent au tableau, aux schémas, au Bode réel (courbe orange) "
                  "et au contrôle du gabarit.")
BULLES_TYPES = {
    "PB": "Passe-bas : laisse passer les fréquences inférieures à fp et atténue celles qui dépassent fa.",
    "PH": "Passe-haut : laisse passer les fréquences supérieures à fp et atténue celles qui sont "
          "inférieures à fa.",
    "PM": "Passe-bande : laisse passer la bande de fp− à fp+ et atténue en dessous de fa− et au-dessus "
          "de fa+. Chaque pôle du prototype donne une cellule passe-bas et une cellule passe-haut.",
    "CB": "Coupe-bande : rejette la bande de fa− à fa+ et laisse passer en dessous de fp− et au-dessus de "
          "fp+. Seules les fonctions de transfert sont calculées : les cellules de Sallen & Key ne le "
          "réalisent pas.",
}
BULLES_CHAMPS = {
    ("PB", "fp"): "Limite de la bande passante : de 0 à fp, le gain doit rester au-dessus de Gp.",
    ("PB", "fa"): "Début de la bande atténuée : au-delà de fa, le gain doit rester au-dessous de Ga. "
                  "Plus fa est proche de fp, plus l'ordre du filtre augmente.",
    ("PH", "fa"): "Fin de la bande atténuée : en dessous de fa, le gain doit rester au-dessous de Ga. "
                  "Plus fa est proche de fp, plus l'ordre du filtre augmente.",
    ("PH", "fp"): "Début de la bande passante : au-delà de fp, le gain doit rester au-dessus de Gp.",
    ("PM", "fa_moins"): "Limite basse de la bande atténuée : en dessous de fa−, le gain doit rester "
                        "au-dessous de Ga.",
    ("PM", "fp_moins"): "Limite basse de la bande passante : de fp− à fp+, le gain doit rester au-dessus de Gp.",
    ("PM", "fp_plus"): "Limite haute de la bande passante : de fp− à fp+, le gain doit rester au-dessus de Gp.",
    ("PM", "fa_plus"): "Limite haute de la bande atténuée : au-dessus de fa+, le gain doit rester "
                       "au-dessous de Ga.",
    ("CB", "fp_moins"): "Limite basse de la bande passante : en dessous de fp−, le gain doit rester "
                        "au-dessus de Gp.",
    ("CB", "fa_moins"): "Début de la bande rejetée : de fa− à fa+, le gain doit rester au-dessous de Ga.",
    ("CB", "fa_plus"): "Fin de la bande rejetée : de fa− à fa+, le gain doit rester au-dessous de Ga.",
    ("CB", "fp_plus"): "Limite haute de la bande passante : au-dessus de fp+, le gain doit rester "
                       "au-dessus de Gp.",
    "Gp": "Gain minimal dans la bande passante, en dB (valeur négative). Avec −3 dB, la valeur habituelle, "
          "ε = 1 : la coupure à −3 dB tombe exactement sur la fréquence limite.",
    "Ga": "Gain maximal dans la bande atténuée, en dB. Par exemple −40 dB : l'amplitude du signal est "
          "divisée par 100.",
    ("PB", "R0"): "Résistance de référence, choisie librement (10 kΩ par exemple). R0·C0·ωp = 1 donne C0, "
                  "puis toutes les valeurs des cellules passe-bas.",
    ("PM", "R0"): "Résistance de référence des cellules passe-bas (et de la cellule de Rauch), choisie "
                  "librement. R0·C0·ω0 = 1 donne leur condensateur de référence.",
    ("PH", "C0"): "Condensateur de référence, choisi librement (10 nF par exemple). R0·C0·ωp = 1 donne R0, "
                  "puis toutes les valeurs des cellules passe-haut.",
    ("PM", "C0"): "Condensateur de référence des cellules passe-haut, choisi librement. R0·C0·ω0 = 1 donne "
                  "leur résistance de référence.",
}
BULLES_ONGLETS = [
    "Gain et phase du prototype passe-bas normalisé H(jΩ), avec le gabarit réduit : Ω = 1 et Ω = 1/k.",
    "Réponse du filtre réel en fonction de la fréquence, avec le gabarit de départ. En orange : le montage "
    "aux valeurs normalisées (E6, E12, E24) ; en violet : avec de vrais µA741 ; zone colorée : dispersion "
    "des composants (cases au-dessus du graphique).",
    "Les six étapes rédigées comme une copie : formule, application numérique, résultat encadré. De "
    "quoi vérifier un calcul ligne par ligne.",
    "Valeurs des composants de chaque cellule (coefficients m et q) et schéma de la cellule choisie.",
    "Montage complet avec des µA741 : brochage, alimentation, nomenclature et notes de câblage.",
]


def chemin_ressource(nom: str) -> str:
    """Chemin d'un fichier livré avec le programme (icône…), aussi une fois installé :
    PyInstaller place ces fichiers dans le dossier indiqué par sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nom)


def identifier_application() -> None:
    """Sous Windows, la barre des tâches affiche l'icône du programme et non celle de Python."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FiltresButterworth.Synthese")
        except Exception:
            pass


def activer_haute_resolution() -> None:
    """Sous Windows, évite le flou sur les écrans à mise à l'échelle (125 %, 150 %…)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


# Tailles du texte proposées dans le menu Affichage (facteur appliqué à toute la fenêtre).
TAILLES_TEXTE = [("Texte normal", 1.0), ("Texte grand", 1.15), ("Texte très grand", 1.3)]


def ouvrir_document(chemin: str) -> None:
    """Ouvre un fichier avec le programme par défaut du système (lecteur PDF…)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(chemin)                                    # noqa: S606 (fichier créé par le programme)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", chemin])
        else:
            subprocess.Popen(["xdg-open", chemin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, AttributeError):
        pass                                                         # pas de lecteur : le fichier est enregistré


def lire_lisezmoi(numeros: Tuple[str, ...]) -> List[Tuple[str, List[str]]]:
    """Parties du LISEZMOI.txt dont le titre commence par l'un des `numeros` (« 4. »…) :
    [(titre, paragraphes)], les lignes coupées à 80 caractères étant recollées."""
    try:
        with open(chemin_ressource("LISEZMOI.txt"), encoding="utf-8-sig") as fichier:
            lignes = fichier.read().replace("\r\n", "\n").split("\n")
    except OSError:
        return []
    sections: List[Tuple[str, List[str]]] = []
    paragraphes: Optional[List[str]] = None
    courant = ""
    for i, ligne in enumerate(lignes):
        souligne = i + 1 < len(lignes) and lignes[i + 1].startswith("---") and ligne[:2].strip(". ").isdigit()
        if souligne:
            if paragraphes is not None and courant:
                paragraphes.append(courant)
            titre = ligne.split(".", 1)[1].strip().capitalize() if "." in ligne else ligne
            if ligne.startswith(numeros):
                paragraphes = []
                sections.append((titre, paragraphes))
            else:
                paragraphes = None
            courant = ""
            continue
        if paragraphes is None or ligne.startswith("---"):
            continue
        brut = ligne.strip()
        if not brut:                                                 # fin de paragraphe
            if courant:
                paragraphes.append(courant)
            courant = ""
        elif brut.startswith("- ") or not courant:
            if courant:
                paragraphes.append(courant)
            courant = brut
        else:
            courant += " " + brut
    if paragraphes is not None and courant:
        paragraphes.append(courant)
    return sections


def fichier_preferences() -> str:
    """Fichier des préférences de l'utilisateur (taille du texte)."""
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "FiltresButterworth", "preferences.json")


def lire_preferences() -> dict:
    try:
        with open(fichier_preferences(), encoding="utf-8") as fichier:
            preferences = json.load(fichier)
        return preferences if isinstance(preferences, dict) else {}
    except (OSError, ValueError):
        return {}


def enregistrer_preferences(preferences: dict) -> None:
    try:
        chemin = fichier_preferences()
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as fichier:
            json.dump(preferences, fichier)
    except OSError:
        pass                                    # préférence simplement non gardée


class Theme:
    """Polices et facteurs d'échelle.

    ecran : rapport entre la résolution de l'écran et 96 ppp (1,25 pour un affichage à 125 %) ;
    zoom  : taille du texte choisie dans le menu Affichage (1 ; 1,15 ; 1,3).
    Toute la fenêtre suit le produit des deux : textes, marges, largeurs et graphiques.
    """

    def __init__(self, racine: tk.Tk, zoom: float = 1.0):
        self.ecran = max(1.0, racine.winfo_fpixels("1i") / 96)
        self.zoom = zoom
        self.echelle = self.ecran * zoom
        familles = set(tkfont.families(racine))
        self.famille = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter",
                                         "Noto Sans", "Ubuntu", "DejaVu Sans", "Arial")
                             if f in familles), "TkDefaultFont")
        # Demi-gras : « Segoe UI Semibold » sous Windows, sinon gras.
        semi, poids = ("Segoe UI Semibold", "normal") if "Segoe UI Semibold" in familles \
            else (self.famille, "bold")
        f = self.famille
        z = lambda taille: int(round(taille * zoom))          # tailles en points
        self.polices = {
            "marque": (semi, z(14), poids),
            "section": (semi, z(11), poids),
            "texte": (f, z(11)),
            "petit": (f, z(10)),
            "champ": (semi, z(11), poids),
            "valeur": (semi, z(16), poids),
            "onglet": (f, z(11)),
            "onglet_actif": (semi, z(11), poids),
            "bouton": (semi, z(11), poids),
            "titre_bloc": (semi, z(12), poids),
        }

    def px(self, n: float) -> int:
        """Convertit une taille pensée pour un écran à 96 ppp, à la taille de texte choisie."""
        return int(round(n * self.echelle))

    @property
    def dpi_figure(self) -> float:
        """Résolution des graphiques matplotlib affichés dans la fenêtre. matplotlib tient
        déjà compte de la résolution de l'écran : seule la taille du texte choisie s'ajoute."""
        return 96 * self.zoom


# =============================================================================
# Petits composants graphiques réutilisables
# =============================================================================

class BoutonPlat(tk.Label):
    """Bouton plat, identique sous Windows, macOS et Linux.

    Pendant une action longue, occuper() change son libellé et l'éclaircit ;
    les clics sont alors ignorés jusqu'à liberer().
    """

    # Fonds (normal, survolé, occupé) et texte : bouton principal (bleu) ou secondaire (clair, bordé)
    STYLES = {"principal": (UI["accent"], UI["accent_survol"], UI["accent_occupe"], "white"),
              "secondaire": (UI["surface"], UI["plan"], UI["plan"], UI["encre"])}

    def __init__(self, parent, theme: Theme, texte: str, commande: Callable, style: str = "principal"):
        self.fonds = self.STYLES[style]
        super().__init__(parent, text=texte, bg=self.fonds[0], fg=self.fonds[3], font=theme.polices["bouton"],
                         cursor="hand2", pady=theme.px(9), takefocus=1)
        if style == "secondaire":
            self.configure(highlightthickness=1, highlightbackground=UI["trait_fort"],
                           highlightcolor=UI["trait_fort"])
        self.texte, self.commande = texte, commande
        self.occupe = self.survol = False
        self.bind("<Enter>", lambda _e: self._survoler(True))
        self.bind("<Leave>", lambda _e: self._survoler(False))
        for evenement in ("<Button-1>", "<Return>", "<space>"):
            # « break » : la touche ne déclenche rien d'autre (la fenêtre a pu être fermée)
            self.bind(evenement, lambda _e: (self._activer(), "break")[1])

    def _couleur(self) -> str:
        """Fond selon l'état : occupé, survolé ou normal."""
        if self.occupe:
            return self.fonds[2]
        return self.fonds[1] if self.survol else self.fonds[0]

    def _survoler(self, dessus: bool) -> None:
        self.survol = dessus
        self.configure(bg=self._couleur())

    def _activer(self) -> None:
        if not self.occupe:
            self.commande()

    def occuper(self, texte: str) -> None:
        """Signale une action en cours : nouveau libellé, fond éclairci, curseur d'attente."""
        self.occupe = True
        self.configure(text=texte, bg=self._couleur(), cursor="watch")

    def liberer(self) -> None:
        """Fin de l'action : le bouton redevient cliquable."""
        self.occupe = False
        self.configure(text=self.texte, bg=self._couleur(), cursor="hand2")


class EtatCalcul(tk.Label):
    """Ligne d'état sous le bouton « Calculer le filtre ».

    Elle dit si le calcul est en cours, terminé (avec l'heure, pour voir qu'un
    nouveau calcul a bien eu lieu même si les résultats n'ont pas changé),
    impossible, ou si la saisie a été modifiée depuis le dernier calcul.
    """

    def __init__(self, parent, theme: Theme):
        super().__init__(parent, text="", font=theme.polices["petit"], bg=UI["plan"], anchor="w",
                         justify="left", wraplength=theme.px(292))
        texte_souple(self)
        self._etat_calcul = ("", UI["discret"])     # dernier résultat d'un calcul (terminé ou impossible)
        self._annonce: Optional[object] = None

    def _montrer(self, texte: str, couleur: str) -> None:
        self._annonce = None                        # une annonce en cours n'est plus d'actualité
        self.configure(text=texte, fg=couleur)

    def en_cours(self) -> None:
        self._montrer("Calcul en cours…", UI["discret"])

    def occupe(self, texte: str) -> None:
        """Action longue en cours (création du compte rendu PDF…)."""
        self._montrer(texte, UI["discret"])

    def termine(self, detail: str = "") -> None:
        texte = f"✓  Calcul terminé à {time.strftime('%H:%M:%S')}" + (f" ({detail})" if detail else "")
        self._etat_calcul = (texte, UI["succes"])
        self._montrer(*self._etat_calcul)

    def impossible(self) -> None:
        self._etat_calcul = ("✕  Calcul impossible : saisie à corriger", UI["erreur"])
        self._montrer(*self._etat_calcul)

    def modifie(self) -> None:
        self._montrer("•  Saisie modifiée : relancez le calcul", UI["alerte"])

    def a_completer(self) -> None:
        """Calcul automatique impossible pour l'instant (valeur incomplète ou incorrecte)."""
        self._montrer("•  Saisie incomplète ou incorrecte : Entrée affiche le problème", UI["alerte"])

    def retablir(self) -> None:
        """La saisie est revenue à celle du dernier calcul : on réaffiche son état."""
        self._montrer(*self._etat_calcul)

    def vider(self) -> None:
        """Aucun calcul pour le filtre affiché (filtre neuf, autre type de filtre)."""
        self._etat_calcul = ("", UI["discret"])
        self._montrer(*self._etat_calcul)

    def annoncer(self, texte: str, succes: bool = True) -> None:
        """Message bref (« Filtre enregistré… », ou ce qui manque pour une action) puis retour
        à l'état du calcul."""
        self._montrer(("✓  " if succes else "•  ") + texte, UI["succes"] if succes else UI["alerte"])
        marque = self._annonce = object()
        self.winfo_toplevel().after(2600, lambda: self.winfo_exists() and marque is self._annonce
                                    and self.retablir())


class Lien(tk.Label):
    """Action discrète en texte (Copier, Enregistrer…)."""

    def __init__(self, parent, theme: Theme, texte: str, commande: Callable, fond: str):
        police = tkfont.Font(font=theme.polices["petit"])
        self.police_survol = tkfont.Font(font=theme.polices["petit"])
        self.police_survol.configure(underline=True)
        super().__init__(parent, text=texte, fg=UI["accent"], bg=fond, font=police, cursor="hand2")
        self.police = police
        self.texte = texte
        self.bind("<Enter>", lambda _e: self.configure(font=self.police_survol))
        self.bind("<Leave>", lambda _e: self.configure(font=self.police))
        self.bind("<Button-1>", lambda _e: commande())

    def confirmer(self, message: str) -> None:
        """Affiche brièvement un retour (« Texte copié ») puis revient au libellé."""
        self.configure(text=message, fg=UI["succes"])
        self.winfo_toplevel().after(1600, lambda: self.winfo_exists()
                                    and self.configure(text=self.texte, fg=UI["accent"]))


class Infobulle:
    """Bulle d'explication qui apparaît au survol d'un élément, après un court délai.

    texte : chaîne, ou fonction qui la renvoie (contenu qui dépend du filtre affiché).
    auto=False : le propriétaire appelle lui-même programmer() et cacher() (onglets
    dessinés sur un Canvas).
    """

    DELAI = 450          # ms avant l'apparition

    def __init__(self, widget: tk.Widget, theme: Theme, texte, auto: bool = True):
        self.widget, self.theme, self.texte = widget, theme, texte
        self.bulle: Optional[tk.Toplevel] = None
        self._attente: Optional[str] = None
        if auto:
            self._lier(widget)

    def _lier(self, w: tk.Widget) -> None:
        """Survol du widget et de ses éléments intérieurs."""
        w.bind("<Enter>", lambda *_: self.programmer(), add="+")
        w.bind("<Leave>", self._sortir, add="+")
        w.bind("<ButtonPress>", lambda *_: self.cacher(), add="+")
        for enfant in w.winfo_children():
            self._lier(enfant)

    def _sortir(self, e=None) -> None:
        try:
            dessous = self.widget.winfo_containing(e.x_root, e.y_root)
        except (tk.TclError, KeyError, AttributeError, TypeError):
            dessous = None
        if dessous is not None and str(dessous).startswith(str(self.widget)):
            return                                  # passage sur un élément intérieur
        self.cacher()

    def programmer(self, position: Optional[Tuple[int, int]] = None, haut: Optional[int] = None) -> None:
        """Affiche la bulle après le délai. position : coin haut gauche (coordonnées écran) ;
        haut : bord supérieur de l'élément, si la bulle doit passer au-dessus faute de place."""
        self.cacher()
        try:
            # minuterie portée par la fenêtre principale : sans effet si l'élément disparaît entre-temps
            self._attente = self.widget.winfo_toplevel().after(self.DELAI, lambda: self.montrer(position, haut))
        except tk.TclError:
            pass

    def cacher(self) -> None:
        if self._attente is not None:
            try:
                self.widget.winfo_toplevel().after_cancel(self._attente)
            except tk.TclError:
                pass
            self._attente = None
        if self.bulle is not None:
            try:
                self.bulle.destroy()
            except tk.TclError:
                pass
            self.bulle = None

    def montrer(self, position: Optional[Tuple[int, int]] = None, haut: Optional[int] = None) -> None:
        self._attente = None
        try:
            if not self.widget.winfo_viewable():
                return
        except tk.TclError:
            return
        texte = self.texte() if callable(self.texte) else self.texte
        if not texte:
            return
        texte = insecable(texte)
        px = self.theme.px
        bulle = tk.Toplevel(self.widget)
        bulle.wm_overrideredirect(True)
        try:
            bulle.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(bulle, text=texte, font=self.theme.polices["petit"], bg=UI["encre"], fg="white",
                 justify="left", anchor="w", wraplength=px(340), padx=px(11), pady=px(8)).pack()
        bulle.update_idletasks()
        largeur, hauteur = bulle.winfo_reqwidth(), bulle.winfo_reqheight()
        if position is None:                        # sous l'élément, à partir de la souris
            x = self.widget.winfo_pointerx() - px(16)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + px(6)
            haut = self.widget.winfo_rooty()
        else:
            x, y = position
        ecran_l, ecran_h = self.widget.winfo_screenwidth(), self.widget.winfo_screenheight()
        x = max(4, min(x, ecran_l - largeur - 4))
        if y + hauteur > ecran_h - 4 and haut is not None:
            y = haut - hauteur - px(6)              # pas la place dessous : au-dessus
        bulle.geometry(f"+{x}+{max(4, y)}")
        self.bulle = bulle


# Croquis d'un gabarit incomplet : position type de chaque fréquence (rapports entre elles),
# pour dessiner la forme du gabarit à l'échelle des valeurs déjà saisies.
FORME_CROQUIS = {
    "PB": {"fp": 1.0, "fa": 3.0},
    "PH": {"fa": 1.0, "fp": 3.0},
    "PM": {"fa_moins": 1.0, "fp_moins": 1.8, "fp_plus": 3.3, "fa_plus": 6.0},
    "CB": {"fp_moins": 1.0, "fa_moins": 1.8, "fa_plus": 3.3, "fp_plus": 6.0},
}


def croquis_complet(t: str, connues: Dict[str, float]) -> Dict[str, float]:
    """Valeurs à dessiner dans le croquis : celles qui sont saisies et, pour les champs encore
    vides, une position type à l'échelle des fréquences déjà saisies (gains : −3 et −30 dB)."""
    forme = FORME_CROQUIS[t]
    saisies = {nom: connues[nom] for nom in forme if connues.get(nom) is not None and connues[nom] > 0}
    echelle = (math.exp(sum(math.log(f / forme[nom]) for nom, f in saisies.items()) / len(saisies))
               if saisies else 1000.0)
    valeurs = {nom: saisies.get(nom, forme[nom] * echelle) for nom in forme}
    valeurs["Gp"] = connues["Gp"] if connues.get("Gp") is not None else -3.0
    valeurs["Ga"] = connues["Ga"] if connues.get("Ga") is not None else min(-30.0, valeurs["Gp"] - 20.0)
    return valeurs


class CroquisGabarit(tk.Canvas):
    """Petit dessin du gabarit à l'échelle (fréquences en échelle logarithmique), redessiné
    pendant la saisie : on voit tout de suite où tombe chaque fréquence, et le paramètre en
    cours de saisie (fp, fa, Gp…) est mis en évidence en bleu."""

    FOND = "#FBEDED"          # zones interdites (comme sur les diagrammes de Bode)
    BORD = "#DC6C6C"

    def __init__(self, parent, theme: Theme):
        super().__init__(parent, height=theme.px(100), bg=UI["surface"], highlightthickness=1,
                         highlightbackground=UI["trait_fort"], bd=0)
        self.theme = theme
        self.police = tkfont.Font(font=theme.polices["petit"])
        self.police_active = tkfont.Font(font=theme.polices["petit"])
        self.police_active.configure(weight="bold")
        self.donnees: Optional[tuple] = None
        self.bind("<Configure>", lambda _e: self._dessiner())

    def montrer(self, type_: str, valeurs: Dict[str, float], actif: Optional[str]) -> None:
        """valeurs : fréquences (Hz), Gp et Ga (dB) à dessiner ; actif : champ mis en évidence."""
        self.donnees = (type_, valeurs, actif)
        self._dessiner()

    def _dessiner(self) -> None:
        self.delete("all")
        largeur, hauteur = self.winfo_width(), self.winfo_height()
        if self.donnees is None or largeur < 60:
            return
        t, v, actif = self.donnees
        px = self.theme.px
        noms_f = list(mt.FREQUENCES[t])
        if any(v.get(n) is None or v[n] <= 0 for n in noms_f) or v.get("Gp") is None or v.get("Ga") is None:
            return
        gauche, droite, haut = px(30), largeur - px(10), px(10)
        bas = hauteur - px(38)                                     # place des noms de fréquences
        f_min, f_max = min(v[n] for n in noms_f) / 2.4, max(v[n] for n in noms_f) * 2.4
        db_haut = max(3.0, v["Gp"] + 3)
        db_bas = min(v["Ga"], v["Gp"]) - 12

        def X(f: float) -> float:
            return gauche + (droite - gauche) * math.log(f / f_min) / math.log(f_max / f_min)

        def Y(db: float) -> float:
            return haut + (bas - haut) * (db_haut - db) / (db_haut - db_bas)

        # Zones interdites : (fréquence gauche, fréquence droite, bas en dB, haut en dB) ; None = bord du cadre
        Gp, Ga = "Gp", "Ga"
        zones = {
            "PB": [(None, "fp", None, Gp), ("fa", None, Ga, None)],
            "PH": [(None, "fa", Ga, None), ("fp", None, None, Gp)],
            "PM": [(None, "fa_moins", Ga, None), ("fp_moins", "fp_plus", None, Gp), ("fa_plus", None, Ga, None)],
            "CB": [(None, "fp_moins", None, Gp), ("fa_moins", "fa_plus", Ga, None), ("fp_plus", None, None, Gp)],
        }[t]
        aretes = []
        for fg, fd, yb, yh in zones:
            x1, x2 = (gauche if fg is None else X(v[fg])), (droite if fd is None else X(v[fd]))
            y1, y2 = (haut if yh is None else Y(v[yh])), (bas if yb is None else Y(v[yb]))
            self.create_rectangle(x1, y1, x2, y2, fill=self.FOND, outline="")
            if fg is not None:
                aretes.append((fg, x1, y1, x1, y2))
            if fd is not None:
                aretes.append((fd, x2, y1, x2, y2))
            if yh is not None:
                aretes.append((yh, x1, y1, x2, y1))
            if yb is not None:
                aretes.append((yb, x1, y2, x2, y2))
        # Axes
        self.create_line(gauche, haut - px(4), gauche, bas, fill=UI["trait_fort"])
        self.create_line(gauche, bas, droite, bas, fill=UI["trait_fort"])
        y0 = Y(0)
        if haut < y0 < bas:
            self.create_line(gauche, y0, droite, y0, fill=UI["trait"], dash=(2, 3))
        # Bords des zones, le paramètre actif en dernier (par-dessus), en bleu
        for nom, x1, y1, x2, y2 in sorted(aretes, key=lambda a: a[0] == actif):
            if nom == actif:
                self.create_line(x1, y1, x2, y2, fill=UI["accent"], width=max(2, px(2.5)))
            else:
                self.create_line(x1, y1, x2, y2, fill=self.BORD, width=max(1, px(1.2)))
        # Noms des fréquences sous l'axe, sur deux rangées s'ils sont trop proches
        fin_rang = [-1e9, -1e9]
        for nom in sorted(noms_f, key=lambda n: v[n]):
            x = X(v[nom])
            texte = mt.LIBELLES[nom]
            police = self.police_active if nom == actif else self.police
            demi = police.measure(texte) / 2
            rang = 0 if x - demi > fin_rang[0] + px(4) else 1
            fin_rang[rang] = x + demi
            y = bas + px(4) + rang * px(15)
            if rang:
                self.create_line(x, bas, x, y, fill=UI["trait_fort"])
            self.create_text(x, y, text=texte, anchor="n", font=police,
                             fill=UI["accent"] if nom == actif else UI["encre2"])
        # Gp et Ga à gauche, à la hauteur de leur limite
        for nom in (Gp, Ga):
            police = self.police_active if nom == actif else self.police
            self.create_text(gauche - px(4), Y(v[nom]), text=nom, anchor="e", font=police,
                             fill=UI["accent"] if nom == actif else UI["encre2"])


class TuileType(tk.Frame):
    """Choix du type de filtre, avec la forme idéale de son gain."""

    FORMES = {
        "PB": [(3, 6), (15, 6), (21, 17), (33, 17)],
        "PH": [(3, 17), (15, 17), (21, 6), (33, 6)],
        "PM": [(3, 17), (10, 17), (14, 6), (22, 6), (26, 17), (33, 17)],
        "CB": [(3, 6), (10, 6), (14, 17), (22, 17), (26, 6), (33, 6)],
    }

    def __init__(self, parent, theme: Theme, code: str, commande: Callable[[str], None]):
        super().__init__(parent, bg=UI["surface"], highlightthickness=1,
                         highlightbackground=UI["trait_fort"], cursor="hand2")
        self.theme, self.code, self.actif = theme, code, False
        # Icône à gauche du nom : tuile basse, la colonne de saisie reste courte
        self.icone = tk.Canvas(self, width=theme.px(24), height=theme.px(16), bg=UI["surface"],
                               highlightthickness=0)
        self.libelle = tk.Label(self, text=mt.NOMS_TYPES[code], font=theme.polices["texte"],
                                bg=UI["surface"], fg=UI["encre"], anchor="w")
        self.icone.pack(side="left", padx=(theme.px(8), theme.px(5)), pady=theme.px(12))
        self.libelle.pack(side="left", fill="x", expand=True)
        for w in (self, self.icone, self.libelle):
            w.bind("<Button-1>", lambda _e: commande(code))
            w.bind("<Enter>", lambda _e: self._survol(True))
            w.bind("<Leave>", lambda _e: self._survol(False))
        self.selectionner(False)

    def selectionner(self, actif: bool) -> None:
        """Met la tuile en avant (type choisi) ou la remet à l'état normal."""
        self.actif = actif
        fond = UI["accent_doux"] if actif else UI["surface"]
        self.configure(bg=fond, highlightbackground=UI["accent"] if actif else UI["trait_fort"])
        self.icone.configure(bg=fond)
        self.libelle.configure(bg=fond, fg=UI["accent"] if actif else UI["encre"])
        self.icone.delete("all")
        points = [self.theme.px(v * e) for xy in self.FORMES[self.code] for v, e in zip(xy, (24 / 36, 16 / 23))]
        self.icone.create_line(*points, fill=UI["accent"] if actif else UI["discret"],
                               width=max(2, self.theme.px(2)), capstyle="round", joinstyle="round")

    def _survol(self, dedans: bool) -> None:
        """Bordure plus foncée au survol d'une tuile non choisie."""
        if not self.actif:
            self.configure(highlightbackground=UI["encre2"] if dedans else UI["trait_fort"])


class Fait(tk.Frame):
    """Un résultat clé du bandeau : titre discret, valeur, précision."""

    def __init__(self, parent, theme: Theme, titre: str, accent: bool = False):
        super().__init__(parent, bg=UI["surface"])
        self.couleur = UI["accent"] if accent else UI["encre"]
        self.titre = tk.Label(self, text=titre, font=theme.polices["petit"], fg=UI["discret"],
                              bg=UI["surface"], anchor="w")
        self.valeur = tk.Label(self, text="—", font=theme.polices["valeur"],
                               fg=self.couleur, bg=UI["surface"], anchor="w")
        self.detail = tk.Label(self, text="", font=theme.polices["petit"], fg=UI["encre2"],
                               bg=UI["surface"], anchor="w")
        self.titre.pack(fill="x")
        self.valeur.pack(fill="x")
        self.detail.pack(fill="x")

    def maj(self, valeur: str, detail: str = "", titre: Optional[str] = None) -> None:
        """Affiche une nouvelle valeur, sa précision et éventuellement un nouveau titre."""
        self.valeur.configure(text=valeur, fg=self.couleur)
        self.detail.configure(text=detail, fg=UI["encre2"])
        if titre:
            self.titre.configure(text=titre)

    def perime(self) -> None:
        """Grise la valeur : elle correspond à un calcul précédent."""
        self.valeur.configure(fg=UI["trait_fort"])
        self.detail.configure(fg=UI["trait_fort"])

    def vider(self, titre: Optional[str] = None) -> None:
        """Pas encore de résultat : tiret discret (la hauteur reste celle d'un résultat)."""
        self.valeur.configure(text="—", fg=UI["trait_fort"])
        self.detail.configure(text=" ", fg=UI["encre2"])
        if titre:
            self.titre.configure(text=titre)


def rectangle_arrondi(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, rayon: float,
                      **options) -> int:
    """Rectangle aux coins arrondis sur un Canvas (polygone lissé)."""
    r = min(rayon, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=12, **options)


class BarreOnglets(tk.Frame):
    """Onglets bien visibles : une piste grise où l'onglet actif est une pastille bleue.

    Un clic, Ctrl+Tab ou Ctrl+1 à Ctrl+5 changent d'onglet ; le survol éclaire l'onglet visé.
    Si la place manque (petit écran, grand texte), les marges diminuent, puis les libellés
    longs raccourcissent, puis les onglets passent sur deux rangées : ils restent tous visibles.
    L'indicateur de gabarit est aligné à droite ; il raccourcit son texte si besoin.
    """

    PISTE = "#E6EBF2"          # fond de la barre d'onglets
    SURVOL = "#D3DCE7"         # onglet survolé
    COURTS = {"Étapes du calcul": "Étapes"}

    def __init__(self, parent, theme: Theme, noms: List[str], commande: Callable[[int], None],
                 aides: Optional[List[str]] = None):
        super().__init__(parent, bg=UI["surface"])
        self.theme, self.commande = theme, commande
        self.actif, self.survol = 0, None
        self.aides = aides or []
        police = tkfont.Font(font=theme.polices["onglet_actif"])      # demi-gras : largeurs stables
        self.libelles = {"complets": list(noms), "courts": [self.COURTS.get(n, n) for n in noms]}
        self.largeurs = {cle: [police.measure(n) for n in libelles] for cle, libelles in self.libelles.items()}
        self.hauteur_pastille = police.metrics("linespace") + theme.px(14)
        self.cle, self.marge, self.rangs = "complets", 16, [list(range(len(noms)))]
        self.zones: List[tuple] = []          # (x1, y1, x2, y2) de chaque onglet
        self.largeur_piste = self.hauteur = 1
        self.canvas = tk.Canvas(self, height=1, width=1, bg=UI["surface"], highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.canvas.bind("<Button-1>", self._clic)
        self.canvas.bind("<Motion>", self._mouvement)
        self.canvas.bind("<Leave>", lambda _e: self._survoler(None))
        self.bulle = Infobulle(self.canvas, theme, self._texte_bulle, auto=False)
        # Indicateur « gabarit respecté », centré verticalement à droite
        self.statut = tk.Label(self, text="", font=theme.polices["petit"], bg=UI["surface"],
                               padx=theme.px(10), pady=theme.px(4))
        self.statut.pack(side="right")
        self.police_statut = tkfont.Font(font=theme.polices["petit"])
        self._statut: tuple = (None, "")
        self.bind("<Configure>", lambda _e: self._mise_en_page())
        self._dessiner()

    # ---------------------------------------------------------------- disposition
    def _largeur_rang(self, cle: str, marge: int, indices) -> int:
        px = self.theme.px
        return (2 * px(4) + sum(self.largeurs[cle][i] + 2 * px(marge) for i in indices)
                + (len(indices) - 1) * px(2))

    def _mise_en_page(self) -> None:
        """Choisit la disposition la plus aérée qui laisse tous les onglets entiers."""
        largeur = self.winfo_width()
        if largeur <= 1:
            return
        tous = list(range(len(self.largeurs["complets"])))
        reserve = self.theme.px(56)                    # place minimale de l'indicateur
        choix = None
        for cle in ("complets", "courts"):
            for marge in (16, 12, 9):
                if self._largeur_rang(cle, marge, tous) + reserve <= largeur:
                    choix = (cle, marge, [tous])
                    break
            if choix:
                break
        if choix is None:                              # plusieurs rangées
            choix = ("courts", 9, self._rangs_equilibres(largeur - reserve))
        if choix != (self.cle, self.marge, self.rangs):
            self.cle, self.marge, self.rangs = choix
            self._dessiner()
        self._dessiner_statut()

    def _rangs_equilibres(self, place: int) -> List[List[int]]:
        """Le moins de rangées possible, de largeurs voisines (3 + 2 plutôt que 4 + 1)."""
        n = len(self.largeurs["courts"])
        if n < 2:
            return [list(range(n))]
        for nombre in range(2, n + 1):
            meilleur = None
            for coupes in itertools.combinations(range(1, n), nombre - 1):
                bornes = (0,) + coupes + (n,)
                rangs = [list(range(a, b)) for a, b in zip(bornes, bornes[1:])]
                pire = max(self._largeur_rang("courts", 9, rang) for rang in rangs)
                if meilleur is None or pire < meilleur[0]:
                    meilleur = (pire, rangs)
            if meilleur[0] <= place:
                break
        return meilleur[1]

    def _dessiner(self) -> None:
        px, c = self.theme.px, self.canvas
        c.delete("all")
        retrait, ecart, hp = px(4), px(2), self.hauteur_pastille
        self.largeur_piste = max(self._largeur_rang(self.cle, self.marge, rang) for rang in self.rangs)
        self.hauteur = 2 * retrait + len(self.rangs) * (hp + ecart) - ecart
        c.configure(width=self.largeur_piste, height=self.hauteur)
        rectangle_arrondi(c, 0, 0, self.largeur_piste, self.hauteur, px(11), fill=self.PISTE, outline="")
        self.zones = [None] * len(self.largeurs[self.cle])
        y = retrait
        for rang in self.rangs:
            x = retrait
            for i in rang:
                largeur = self.largeurs[self.cle][i] + 2 * px(self.marge)
                self.zones[i] = (x, y, x + largeur, y + hp)
                x += largeur + ecart
            y += hp + ecart
        for i, (x1, y1, x2, y2) in enumerate(self.zones):
            actif, survole = i == self.actif, i == self.survol and i != self.actif
            if actif or survole:
                rectangle_arrondi(c, x1, y1, x2, y2, px(8), fill=UI["accent"] if actif else self.SURVOL,
                                  outline="")
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=self.libelles[self.cle][i],
                          font=self.theme.polices["onglet_actif" if actif else "onglet"],
                          fill="white" if actif else (UI["encre"] if survole else UI["encre2"]))

    # ---------------------------------------------------------------- souris
    def _onglet_sous(self, x: float, y: float) -> Optional[int]:
        return next((i for i, (x1, y1, x2, y2) in enumerate(self.zones) if x1 <= x <= x2 and y1 <= y <= y2),
                    None)

    def _clic(self, event) -> None:
        self.bulle.cacher()
        i = self._onglet_sous(event.x, event.y)
        if i is not None:
            self.commande(i)

    def _mouvement(self, event) -> None:
        self._survoler(self._onglet_sous(event.x, event.y))

    def _survoler(self, i: Optional[int]) -> None:
        self.canvas.configure(cursor="hand2" if i is not None else "")
        if i != self.survol:
            self.survol = i
            self._dessiner()
            if i is None:
                self.bulle.cacher()
            else:                                   # bulle sous l'onglet survolé
                x1, y1, _x2, y2 = self.zones[i]
                x0, y0 = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
                self.bulle.programmer((x0 + int(x1), y0 + int(y2) + self.theme.px(8)), haut=y0 + int(y1))

    def _texte_bulle(self) -> str:
        i = self.survol
        if i is None or i >= len(self.aides):
            return ""
        return f"{self.aides[i]}\nRaccourci : Ctrl+{i + 1}"

    def activer(self, i: int) -> None:
        """Met l'onglet i en avant (pastille bleue)."""
        self.actif = i
        self._dessiner()

    # ---------------------------------------------------------------- indicateur
    def afficher_statut(self, respecte: Optional[bool], precision: str = "") -> None:
        """Indicateur « Gabarit respecté » (vert) ou « non respecté » (rouge).

        `precision` indique les valeurs affichées, par exemple « (R E12, C E6) ».
        """
        self._statut = (respecte, precision)
        self._dessiner_statut()

    def _dessiner_statut(self) -> None:
        """Écrit l'indicateur avec le texte le plus complet qui tient à droite des onglets."""
        respecte, precision = self._statut
        if respecte is None:
            self.statut.configure(text="", bg=UI["surface"])
            return
        signe, mot = ("✓", "respecté") if respecte else ("✕", "non respecté")
        variantes = [f"{signe}  Gabarit {mot}" + (f" {precision}" if precision else ""),
                     f"{signe}  Gabarit {mot}", f"{signe}  {mot.capitalize()}", signe]
        place = self.winfo_width() - self.largeur_piste - self.theme.px(14) - 2 * self.theme.px(10)
        texte = next((v for v in variantes if self.police_statut.measure(v) <= place), signe)
        self.statut.configure(text=texte, fg=UI["succes"] if respecte else UI["erreur"],
                              bg=UI["succes_doux"] if respecte else UI["erreur_doux"])


class Segments(tk.Frame):
    """Choix exclusif entre quelques options côte à côte (contrôle segmenté)."""

    def __init__(self, parent, theme: Theme, options: List[tuple], valeur: str,
                 commande: Callable[[str], None]):
        super().__init__(parent, bg=UI["trait_fort"])           # le fond sert de bordure de 1 px
        self.commande = commande
        self.boutons: Dict[str, tk.Label] = {}
        for i, (code, texte) in enumerate(options):
            bouton = tk.Label(self, text=texte, font=theme.polices["texte"], cursor="hand2",
                              pady=theme.px(5))
            bouton.grid(row=0, column=i, sticky="nsew", padx=(1, 1 if i == len(options) - 1 else 0), pady=1)
            self.columnconfigure(i, weight=1, uniform="segment")
            bouton.bind("<Button-1>", lambda _e, c=code: self._choisir(c))
            self.boutons[code] = bouton
        self.selectionner(valeur)

    def selectionner(self, code: str) -> None:
        """Met en avant l'option choisie."""
        self.valeur = code
        for c, bouton in self.boutons.items():
            actif = c == code
            bouton.configure(bg=UI["accent"] if actif else UI["surface"],
                             fg="white" if actif else UI["encre"])

    def _choisir(self, code: str) -> None:
        """Clic sur une option : sélection puis appel de la commande."""
        if code != self.valeur:
            self.selectionner(code)
            self.commande(code)


class ChampUnite(tk.Frame):
    """Champ de saisie compact : son nom au-dessus, la valeur et l'unité dans le même cadre.

    `entree` est le champ ttk lui-même ; marquer(True) le signale en rouge (saisie incorrecte)."""

    def __init__(self, parent, theme: Theme, nom: str, unite: str):
        super().__init__(parent, bg=UI["plan"])
        px, P = theme.px, theme.polices
        self.nom_champ = tk.Label(self, text=mt.LIBELLES.get(nom, nom), font=P["petit"], fg=UI["encre2"],
                                  bg=UI["plan"], anchor="w")
        self.nom_champ.pack(fill="x", pady=(0, px(2)))
        self.boite = tk.Frame(self, bg=UI["surface"], highlightthickness=1,
                              highlightbackground=UI["trait_fort"], highlightcolor=UI["trait_fort"])
        self.boite.pack(fill="x")
        self.unite = tk.Label(self.boite, text=unite, font=P["petit"], fg=UI["discret"], bg=UI["surface"],
                              cursor="xterm")
        self.unite.pack(side="right", padx=(0, px(8)))
        self.entree = ttk.Entry(self.boite, style="Nu.TEntry", font=P["texte"], width=5)
        self.entree.pack(side="left", fill="x", expand=True)
        self.erreur = False
        self.entree.bind("<FocusIn>", lambda _e: self._bordure(True), add="+")
        self.entree.bind("<FocusOut>", lambda _e: self._bordure(False), add="+")
        for w in (self.boite, self.unite):
            w.bind("<Button-1>", lambda _e: self.entree.focus_set())

    def _bordure(self, focus: bool) -> None:
        couleur = UI["erreur"] if self.erreur else (UI["accent"] if focus else UI["trait_fort"])
        self.boite.configure(highlightbackground=couleur, highlightcolor=couleur)

    def marquer(self, erreur: bool) -> None:
        """Champ en erreur (fond rosé, bordure rouge) ou normal."""
        self.erreur = erreur
        fond = UI["erreur_doux"] if erreur else UI["surface"]
        self.boite.configure(bg=fond)
        self.unite.configure(bg=fond)
        self.entree.configure(style="NuErreur.TEntry" if erreur else "Nu.TEntry")
        try:
            focus = self.focus_get() is self.entree
        except (KeyError, tk.TclError):
            focus = False
        self._bordure(focus)


class ListeChoix(tk.Frame):
    """Liste déroulante sobre, utilisée comme Segments (valeur, selectionner) : un cadre comme
    celui des champs, le choix et un chevron ; un clic (ou Espace, Entrée, flèche bas) ouvre le
    menu des options. Flèches haut et bas : option précédente ou suivante, sans ouvrir le menu."""

    def __init__(self, parent, theme: Theme, options: List[tuple], valeur: str,
                 commande: Callable[[str], None]):
        super().__init__(parent, bg=UI["surface"], highlightthickness=1, highlightbackground=UI["trait_fort"],
                         highlightcolor=UI["accent"], cursor="hand2", takefocus=1)
        px, P = theme.px, theme.polices
        self.theme, self.options, self.commande = theme, list(options), commande
        self.texte = tk.Label(self, text="", font=P["texte"], fg=UI["encre"], bg=UI["surface"], anchor="w")
        self.texte.pack(side="left", fill="x", expand=True, padx=(px(8), 0), pady=px(5))
        self.fleche = tk.Canvas(self, width=px(12), height=px(12), bg=UI["surface"], highlightthickness=0)
        self.fleche.pack(side="right", padx=(px(4), px(9)))
        s = theme.px
        self.fleche.create_line(s(2), s(4), s(6), s(8), s(10), s(4), fill=UI["encre2"], width=max(1.5, s(1.6)),
                                capstyle="round", joinstyle="round")
        self.var = tk.StringVar(value=valeur)
        self.menu = tk.Menu(self, tearoff=False, font=P["texte"], bg=UI["surface"], fg=UI["encre"],
                            activebackground=UI["accent_doux"], activeforeground=UI["encre"],
                            selectcolor=UI["accent"], bd=1, relief="solid")
        for code, texte in self.options:
            self.menu.add_radiobutton(label=texte, value=code, variable=self.var,
                                      command=lambda c=code: self._choisir(c))
        for w in (self, self.texte, self.fleche):
            w.bind("<Button-1>", self.ouvrir)
            w.bind("<Enter>", lambda _e: self._bordure(survol=True), add="+")
            w.bind("<Leave>", lambda _e: self._bordure(), add="+")
        for touche in ("<space>", "<Return>", "<KP_Enter>", "<Alt-Down>"):
            self.bind(touche, self.ouvrir)
        self.bind("<Down>", lambda _e: self._voisine(1))
        self.bind("<Up>", lambda _e: self._voisine(-1))
        self.bind("<FocusIn>", lambda _e: self._bordure(), add="+")
        self.bind("<FocusOut>", lambda _e: self._bordure(), add="+")
        self.selectionner(valeur)

    def _bordure(self, survol: bool = False) -> None:
        try:
            focus = self.focus_get() is self
        except (KeyError, tk.TclError):
            focus = False
        couleur = UI["accent"] if focus else (UI["encre2"] if survol else UI["trait_fort"])
        self.configure(highlightbackground=couleur, highlightcolor=couleur)

    def ouvrir(self, _e=None) -> str:
        """Ouvre le menu des options juste sous la liste."""
        self.focus_set()
        try:
            self.menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            self.menu.grab_release()
        return "break"

    def _voisine(self, sens: int) -> str:
        codes = [code for code, _texte in self.options]
        i = codes.index(self.valeur) if self.valeur in codes else 0
        self._choisir(codes[max(0, min(len(codes) - 1, i + sens))])
        return "break"

    def selectionner(self, code: str) -> None:
        """Affiche l'option choisie (sans appeler la commande)."""
        self.valeur = code
        self.var.set(code)
        self.texte.configure(text=dict(self.options).get(code, ""))

    def _choisir(self, code: str) -> None:
        if code != self.valeur:
            self.selectionner(code)
            self.commande(code)
        else:
            self.var.set(code)


class SectionRepliable(tk.Frame):
    """Bandeau cliquable (chevron, titre, résumé à droite) qui montre ou cache son contenu.

    Il se déplie aussi au clavier (Tab puis Espace ou Entrée)."""

    def __init__(self, parent, theme: Theme, titre: str, ouvert: bool = False,
                 commande: Optional[Callable[[bool], None]] = None):
        super().__init__(parent, bg=UI["plan"])
        px, P = theme.px, theme.polices
        self.theme, self.commande, self.ouvert = theme, commande, ouvert
        self.tete = tk.Frame(self, bg=UI["surface"], highlightthickness=1, highlightbackground=UI["trait_fort"],
                             highlightcolor=UI["accent"], cursor="hand2", takefocus=1)
        self.tete.pack(fill="x")
        self.chevron = tk.Canvas(self.tete, width=px(12), height=px(12), bg=UI["surface"], highlightthickness=0)
        self.chevron.pack(side="left", padx=(px(10), px(7)), pady=px(11))
        self.titre = tk.Label(self.tete, text=titre, font=P["champ"], fg=UI["encre"], bg=UI["surface"])
        self.titre.pack(side="left")
        self.resume = tk.Label(self.tete, text="", font=P["petit"], fg=UI["encre2"], bg=UI["surface"])
        self.resume.pack(side="right", padx=(0, px(10)))
        self.contenu = tk.Frame(self, bg=UI["plan"])
        for w in (self.tete, self.chevron, self.titre, self.resume):
            w.bind("<Button-1>", lambda _e: self.basculer())
            w.bind("<Enter>", lambda _e: self._survol(True), add="+")
            w.bind("<Leave>", lambda _e: self._survol(False), add="+")
        for touche in ("<space>", "<Return>", "<KP_Enter>"):
            self.tete.bind(touche, lambda _e: self.basculer())
        self._dessiner()
        if ouvert:
            self.contenu.pack(fill="x", pady=(px(10), 0))

    def _survol(self, dedans: bool) -> None:
        self.tete.configure(highlightbackground=UI["encre2"] if dedans else UI["trait_fort"])

    def _dessiner(self) -> None:
        """Chevron : vers la droite (replié) ou vers le bas (déplié)."""
        s = self.theme.px
        self.chevron.delete("all")
        points = [s(2), s(4), s(6), s(8), s(10), s(4)] if self.ouvert else [s(4), s(2), s(8), s(6), s(4), s(10)]
        self.chevron.create_line(*points, fill=UI["encre2"], width=max(1.5, s(1.6)), capstyle="round",
                                 joinstyle="round")

    def basculer(self) -> None:
        """Déplie ou replie la section."""
        self.ouvert = not self.ouvert
        if self.ouvert:
            self.contenu.pack(fill="x", pady=(self.theme.px(10), 0))
        else:
            self.contenu.pack_forget()
        self._dessiner()
        if self.commande is not None:
            self.commande(self.ouvert)

    def resumer(self, texte: str) -> None:
        """Texte discret à droite du titre (« 2 actives »)."""
        self.resume.configure(text=texte)


def insecable(texte: str) -> str:
    """Espaces insécables (voir moteur.insecable) : nombre et unité, « : », « ; », égalités courtes."""
    return mt.insecable(texte)


def texte_souple(label: tk.Label, marge: int = 0) -> tk.Label:
    """Le texte du label passe à la ligne selon la largeur réellement disponible
    (elle diminue par exemple quand une barre de défilement apparaît)."""
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(60, e.width - marge)), add="+")
    return label


def entete_panneau(parent, theme: Theme, action: str, commande: Callable) -> tuple:
    """Ligne du haut d'un onglet : légende à gauche, action(s) discrète(s) à droite
    (dans lien.master). Si la légende n'a plus assez de place (petit écran, grand texte),
    les actions passent sous la légende, alignées à droite."""
    entete = tk.Frame(parent, bg=UI["surface"])
    actions = tk.Frame(entete, bg=UI["surface"])
    lien = Lien(actions, theme, action, commande, UI["surface"])
    lien.pack(side="right")
    legende = tk.Label(entete, text="", font=theme.polices["petit"], fg=UI["encre2"],
                       bg=UI["surface"], anchor="w", justify="left")
    legende.bind("<Configure>", lambda e: legende.configure(wraplength=max(100, e.width - 4)))
    etat = {"etroit": None}

    def disposer(_e=None) -> None:
        largeur = entete.winfo_width()
        if largeur <= 1:
            return
        etroit = largeur - actions.winfo_reqwidth() < theme.px(420)
        if etroit == etat["etroit"]:
            return
        etat["etroit"] = etroit
        actions.pack_forget()
        legende.pack_forget()
        if etroit:
            legende.pack(side="top", fill="x")
            actions.pack(side="top", anchor="e", pady=(theme.px(2), 0))
        else:
            actions.pack(side="right")                 # placées en premier : jamais rognées
            legende.pack(side="left", fill="x", expand=True)

    actions.pack(side="right")
    legende.pack(side="left", fill="x", expand=True)
    entete.bind("<Configure>", disposer, add="+")
    entete.pack(fill="x")
    return legende, lien


def barre_automatique(barre: ttk.Scrollbar, **placement) -> Callable:
    """Renvoie une fonction yscrollcommand qui n'affiche la barre que si elle sert."""
    def maj(debut, fin):
        """Met la barre à jour et la masque quand tout le contenu est visible."""
        barre.set(debut, fin)
        if float(debut) <= 0.0 and float(fin) >= 1.0:
            barre.pack_forget()
        elif not barre.winfo_ismapped():
            barre.pack(**placement)
    return maj


class CadreDefilant(tk.Frame):
    """Colonne qui défile à la molette si son contenu dépasse la hauteur de la fenêtre
    (petits écrans, mise à l'échelle 125 % ou 150 %).

    hauteur_min : si elle est donnée (fonction), le contenu occupe toute la hauteur visible,
    sans descendre sous hauteur_min() ; en dessous, la colonne défile (un graphique garde
    ainsi une taille lisible au lieu d'être écrasé)."""

    def __init__(self, parent, fond: str, hauteur_min: Optional[Callable[[], int]] = None, **options):
        super().__init__(parent, bg=fond, **options)
        self.hauteur_min = hauteur_min
        self.canvas = tk.Canvas(self, bg=fond, highlightthickness=0, bd=0, width=1, height=1)
        self.barre = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interieur = tk.Frame(self.canvas, bg=fond)
        self.fenetre = self.canvas.create_window(0, 0, window=self.interieur, anchor="nw")
        self.canvas.configure(yscrollcommand=barre_automatique(self.barre, side="right", fill="y",
                                                               before=self.canvas))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interieur.bind("<Configure>",
                            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda _e: self.ajuster())
        for evenement in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(evenement, self._molette, add="+")

    def ajuster(self) -> None:
        """Contenu à la largeur visible (et à la hauteur visible, au moins hauteur_min())."""
        largeur, hauteur = self.canvas.winfo_width(), self.canvas.winfo_height()
        if largeur <= 1:
            return
        self.canvas.itemconfigure(self.fenetre, width=largeur)
        if self.hauteur_min is not None:
            self.canvas.itemconfigure(self.fenetre, height=max(hauteur, self.hauteur_min()))

    def montrer(self, widget: tk.Widget) -> None:
        """Fait défiler la colonne juste ce qu'il faut pour que `widget` soit visible."""
        self.update_idletasks()
        total, vue = self.interieur.winfo_height(), self.canvas.winfo_height()
        if total <= vue or vue <= 1:
            return
        y = widget.winfo_rooty() - self.interieur.winfo_rooty()
        h = widget.winfo_height()
        haut = self.canvas.yview()[0] * total
        if y < haut:
            self.canvas.yview_moveto(max(0, y - 12) / total)
        elif y + h > haut + vue:
            self.canvas.yview_moveto(min(y - 12, y + h + 12 - vue) / total)

    def _molette(self, event) -> None:
        """Défilement à la molette, seulement si la souris est sur cette colonne."""
        if not self.winfo_exists():
            return                                  # colonne d'une fenêtre reconstruite
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not str(widget).startswith(str(self)):
            return                                  # la souris n'est pas sur cette colonne
        if self.canvas.yview() == (0.0, 1.0):
            return                                  # tout est visible : rien à faire
        if getattr(event, "num", None) == 4:
            pas = -1
        elif getattr(event, "num", None) == 5:
            pas = 1
        else:
            pas = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(pas * 2, "units")


def image_tk(fig: Figure, dpi: float) -> tk.PhotoImage:
    """Rend une figure matplotlib en image Tk (format PPM, plus rapide que le PNG)."""
    fig.set_dpi(dpi)
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    hauteur, largeur = rgba.shape[:2]
    entete = b"P6 %d %d 255 " % (largeur, hauteur)
    return tk.PhotoImage(data=entete + rgba[:, :, :3].tobytes(), format="PPM")


class ZoneImage(tk.Frame):
    """Grande image (schéma de câblage) qui défile dans les deux sens : molette
    (vertical), Maj + molette (horizontal), ou en la faisant glisser à la souris."""

    def __init__(self, parent, fond: str):
        super().__init__(parent, bg=fond)
        self.canvas = tk.Canvas(self, bg=fond, highlightthickness=0, bd=0, width=1, height=1)
        self.barre_v = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.barre_h = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(
            yscrollcommand=barre_automatique(self.barre_v, side="right", fill="y", before=self.canvas),
            xscrollcommand=barre_automatique(self.barre_h, side="bottom", fill="x", before=self.canvas))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.image = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        for evenement in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>",
                          "<Shift-Button-4>", "<Shift-Button-5>"):
            self.bind_all(evenement, self._molette, add="+")

    def afficher(self, photo: tk.PhotoImage, garder_position: bool = False) -> None:
        """Affiche l'image ; sans garder_position, la vue revient en haut à gauche."""
        vue = (self.canvas.xview()[0], self.canvas.yview()[0])
        self.canvas.itemconfigure(self.image, image=photo)
        self.canvas.configure(scrollregion=(0, 0, photo.width(), photo.height()))
        self.canvas.xview_moveto(vue[0] if garder_position else 0)
        self.canvas.yview_moveto(vue[1] if garder_position else 0)

    def _molette(self, event) -> None:
        """Défilement à la molette quand la souris est sur l'image (Maj : horizontal)."""
        if not self.winfo_exists():
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not str(widget).startswith(str(self)):
            return
        horizontal = bool(event.state & 0x0001)
        if getattr(event, "num", None) in (4, 5):
            pas = -1 if event.num == 4 else 1
        else:
            pas = -1 if event.delta > 0 else 1
        if horizontal:
            if self.canvas.xview() != (0.0, 1.0):
                self.canvas.xview_scroll(pas * 3, "units")
        elif self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(pas * 3, "units")


# =============================================================================
# Onglets de résultats
# =============================================================================

class PanneauBode(tk.Frame):
    """Diagramme de Bode (gain et phase) avec le gabarit et un curseur de lecture."""

    HAUTEUR_MIN = 260          # hauteur minimale du graphique (pixels à 100 %) ; en dessous, l'onglet défile

    def __init__(self, parent, theme: Theme, normalise: bool, app: "Application"):
        super().__init__(parent, bg=UI["surface"])
        self.theme, self.normalise, self.app = theme, normalise, app
        # Petit écran ou grand texte : l'onglet défile plutôt que d'écraser le graphique
        self.defil = CadreDefilant(self, UI["surface"], hauteur_min=self._hauteur_utile)
        self.defil.pack(fill="both", expand=True)
        contenu = self.defil.interieur
        self.legende, self.lien = entete_panneau(contenu, theme, "Enregistrer l'image…", self.enregistrer)
        self.entete = self.legende.master
        self.entete.bind("<Configure>", lambda _e: self.defil.ajuster(), add="+")
        self.case_aop: Optional[ttk.Checkbutton] = None
        self.case_dispersion: Optional[ttk.Checkbutton] = None
        if not normalise:
            # Option : réponse du montage avec de vrais µA741 (courbe violette en pointillés)
            self.case_aop = ttk.Checkbutton(self.lien.master, text=f"{mt.AOP_NOM} réel", variable=app.var_aop,
                                            style="Option.TCheckbutton", command=app.basculer_aop)
            self.case_aop.pack(side="right", padx=(0, theme.px(18)))
            self.case_dispersion = ttk.Checkbutton(self.lien.master, text="Dispersion", variable=app.var_dispersion,
                                                   style="Option.TCheckbutton", command=app.basculer_dispersion)
            self.case_dispersion.pack(side="right", padx=(0, theme.px(14)))
            Infobulle(self.case_dispersion, theme,
                      "Tire 300 montages au hasard, chaque composant dans sa tolérance (celle de la série "
                      "choisie, sinon R ±5 % et C ±10 %), et colore la zone balayée par leurs gains. La légende "
                      "donne la part des montages qui respectent le gabarit (amplificateurs idéaux).")
            Infobulle(self.case_aop, theme,
                      f"Ajoute la réponse du montage avec de vrais {mt.AOP_NOM} (gain 2·10⁵, produit gain-bande "
                      "1 MHz) au lieu d'amplificateurs idéaux, avec les mêmes valeurs de composants. "
                      "Aussi dans le menu Affichage.")

        # Ligne du bas : lecture (point survolé, ou repère posé) et champ pour lire en un point précis
        px, P = theme.px, theme.polices
        self.bas = tk.Frame(contenu, bg=UI["surface"])
        self.bas.pack(side="bottom", fill="x", pady=(px(4), 0))
        if not normalise:
            tk.Label(self.bas, text="Hz", font=P["petit"], fg=UI["discret"], bg=UI["surface"]).pack(side="right")
        self.champ_x = ttk.Entry(self.bas, width=9, style="Lecture.TEntry", font=P["petit"])
        self.champ_x.pack(side="right", padx=(px(4), px(4)))
        tk.Label(self.bas, text="Ω =" if normalise else "f =", font=P["petit"], fg=UI["encre2"],
                 bg=UI["surface"]).pack(side="right", padx=(px(14), 0))
        self.lecture = tk.Label(self.bas, text=self.LECTURE, font=P["petit"], fg=UI["discret"],
                                bg=UI["surface"], anchor="w", justify="left")
        self.lecture.pack(side="left", fill="x", expand=True)
        texte_souple(self.lecture)
        for touche in ("<Return>", "<KP_Enter>"):
            self.champ_x.bind(touche, lambda _e: self.lire_en(self.champ_x.get()))
        self.champ_x.bind("<Escape>", lambda _e: self.lire_en(""))
        Infobulle(self.champ_x, theme,
                  ("Tapez une pulsation réduite (0,5 ; 2,6…)" if normalise else
                   "Tapez une fréquence (2,4k ; 5 kHz ; 909…)")
                  + " puis Entrée : le gain et la phase exacts s'affichent et un repère est posé sur le "
                    "graphique. Un clic sur le graphique fait de même. Échap efface le repère.")
        self.x_repere: Optional[float] = None       # point de lecture posé (Hz, ou Ω pour le Bode normalisé)
        self.texte_repere = ""
        self.type_repere = ""
        self.artistes_repere: List = []
        self.res: Optional[mt.Resultat] = None
        self.courbe: Optional[gr.Courbe] = None
        self.choix: Optional[mt.ChoixSeries] = None

        self.fig, self.ax_g, self.ax_p = gr.creer_figure_bode(dpi=theme.dpi_figure)
        self.fig.set_size_inches(8, 5)
        self.canvas = FigureCanvasTkAgg(self.fig, master=contenu)
        widget = self.canvas.get_tk_widget()
        widget.configure(bg=UI["surface"], highlightthickness=0, height=1)
        widget.pack(fill="both", expand=True, pady=(theme.px(4), 0))
        self.curseur = gr.Curseur(self.canvas, self.ax_g, self.ax_p, afficher=self._lire)
        self.canvas.mpl_connect("button_press_event", self._clic)

    LECTURE = "Survolez le graphique pour lire la fréquence, le gain et la phase ; cliquez pour poser un repère."

    def _hauteur_utile(self) -> int:
        """Hauteur minimale de l'onglet : légende + graphique lisible + ligne de lecture."""
        px = self.theme.px
        return (self.entete.winfo_reqheight() + self.bas.winfo_reqheight() + px(8)
                + px(self.HAUTEUR_MIN))

    def _lire(self, texte: Optional[str]) -> None:
        """Affiche la lecture du curseur ; quand la souris sort, celle du repère posé (ou l'invite)."""
        if texte:
            self.lecture.configure(text=texte, fg=UI["encre"])
        elif self.texte_repere:
            self.lecture.configure(text=self.texte_repere, fg=UI["accent"])
        else:
            self.lecture.configure(text=self.LECTURE, fg=UI["discret"])

    # ------------------------------------------------------------ lecture en un point
    def _clic(self, event) -> None:
        """Clic sur le graphique : repère posé à cette fréquence."""
        if event.button != 1 or event.inaxes not in (self.ax_g, self.ax_p) or event.xdata is None:
            return
        x = float(event.xdata)
        texte = mt.fmt_compact(x, 4) if self.normalise else mt.fmt_si(x, "", 4, compact=True).replace(" ", "")
        self.champ_x.delete(0, "end")
        self.champ_x.insert(0, texte)
        self.lire_en(texte)

    def lire_en(self, texte: str) -> None:
        """Champ « f = » (ou « Ω = ») validé : valeurs exactes en ce point et repère sur le graphique."""
        texte = texte.strip()
        if not texte:
            self.x_repere, self.texte_repere = None, ""
            self.champ_x.delete(0, "end")
            self._dessiner_repere()
            self._lire(None)
            return
        try:
            x = mt.lire_valeur(texte, "f")
            if not x > 0:
                raise mt.ErreurGabarit("valeur négative", "f")
        except mt.ErreurGabarit:
            exemple = "0,5 ; 2,6" if self.normalise else "2,4k ; 5 kHz ; 909"
            self.lecture.configure(text=f"Valeur illisible : « {texte} ». Exemples : {exemple}.", fg=UI["erreur"])
            return
        self.x_repere = x
        self._dessiner_repere()

    def oublier_repere(self) -> None:
        """Nouveau filtre : pas de repère sur le prochain tracé."""
        self.x_repere, self.texte_repere, self.type_repere = None, "", ""
        self.champ_x.delete(0, "end")

    def _dessiner_repere(self) -> None:
        """(Re)place le repère et sa lecture ; appelé aussi après chaque nouveau tracé."""
        for artiste in self.artistes_repere:
            try:
                artiste.remove()
            except (ValueError, NotImplementedError):
                pass
        self.artistes_repere = []
        self.texte_repere = ""
        if self.x_repere is not None and self.res is not None and self.courbe is not None:
            x = self.x_repere
            G, ph, G2, G3 = gr.valeurs_en(self.res, self.courbe, x, self.normalise, self.choix)
            debut = f"Ω = {mt.fmt_nombre(x, 4)}" if self.normalise else mt.fmt_si(x, "Hz", 4)
            texte = f"Repère  {debut} :  G = {gr.fmt_db(G)} dB     φ = {gr.fmt_deg(ph)}°"
            if G2 is not None:
                texte += f"     Normalisées : G = {gr.fmt_db(G2)} dB"
            if G3 is not None:
                texte += f"     {mt.AOP_NOM} : G = {gr.fmt_db(G3)} dB"
            self.texte_repere = texte
            style = dict(color=gr.COULEURS["accent"], linewidth=1.1, linestyle=(0, (3, 2.5)), alpha=0.85, zorder=2.6)
            point = dict(marker="o", markersize=7, markerfacecolor=gr.COULEURS["accent"],
                         markeredgecolor=gr.COULEURS["fond"], markeredgewidth=1.5, linestyle="none", zorder=6.5)
            self.artistes_repere = [self.ax_g.axvline(x, **style), self.ax_p.axvline(x, **style),
                                    self.ax_g.plot([x], [G], **point)[0], self.ax_p.plot([x], [ph], **point)[0]]
        self._lire(None)
        self.canvas.draw_idle()

    def afficher(self, res: mt.Resultat) -> None:
        """Trace le diagramme de Bode pour le résultat donné."""
        # Sur le Bode réel, on superpose le montage aux valeurs normalisées si une série est choisie,
        # et, en option, le montage avec de vrais µA741.
        choix = None if self.normalise or not res.montages else self.app.choix_series()
        aop = not self.normalise and self.app.aop_reel and bool(res.montages)
        dispersion = not self.normalise and self.app.dispersion and bool(res.montages)
        courbe = gr.tracer_bode(self.ax_g, self.ax_p, res, self.normalise, choix, aop=aop, dispersion=dispersion)
        self.curseur.attacher(courbe)
        # Repère de lecture : gardé d'un calcul à l'autre, effacé si le type de filtre change
        self.res, self.courbe, self.choix = res, courbe, choix
        if res.gabarit.type != self.type_repere:
            self.type_repere = res.gabarit.type
            self.x_repere = None
            self.champ_x.delete(0, "end")
        self.artistes_repere = []                    # effacés par le nouveau tracé
        self._dessiner_repere()
        if self.normalise:
            texte = f"Prototype passe-bas d'ordre {res.n} et gabarit réduit (Ω = 1 et Ω = 1/k)."
        else:
            texte = (f"Filtre {mt.NOMS_TYPES[res.gabarit.type].lower()} réel et gabarit de départ"
                     + (f", avec le montage aux valeurs normalisées ({choix.court()})" if choix else "") + ".")
            if choix is not None and not all(p.ok for p in res.points_controle_serie(choix)):
                texte += (" Avec ces valeurs, le gabarit n'est plus respecté : « Corriger les valeurs », dans "
                          "l'onglet Composants, en cherche d'autres qui le respectent.")
            if res.attenuateur() and not self.app.pont_actif():
                texte += (f" Gain ramené à 0 dB à f0 pour la comparaison au gabarit : sans pont diviseur, le "
                          f"montage a {mt.fmt_nombre(20 * math.log10(res.gain_montage()), 3)} dB.")
            if aop:
                texte += " " + mt.bilan_aop(res, choix)[1]
            if courbe.dispersion is not None:
                texte += " " + mt.bilan_dispersion(res, courbe.dispersion, choix)
            for case in (self.case_aop, self.case_dispersion):
                if case is not None:
                    case.state(["!disabled"] if res.montages else ["disabled"])
        self.legende.configure(text=texte)

    def enregistrer(self) -> None:
        """Enregistre le diagramme en PNG, PDF ou SVG."""
        nom = "bode_normalise" if self.normalise else "bode_reel"
        chemin = self.app.demander_enregistrement(
            "Enregistrer le diagramme de Bode", f"{self.app.nom_base()}_{nom}.png", ".png",
            [("Image PNG", "*.png"), ("Document PDF", "*.pdf"), ("Image vectorielle SVG", "*.svg")])
        if chemin:
            self.fig.savefig(chemin, dpi=200, facecolor="white")
            self.lien.confirmer("Image enregistrée")


class PanneauEtapes(tk.Frame):
    """Les six étapes de la synthèse, écrites pas à pas : explications,
    formules (rendues en images) et applications numériques, puis la vérification du gabarit.

    Le texte s'affiche aussitôt ; les formules qui n'ont encore jamais été rendues
    arrivent ensuite une à une, sans bloquer la fenêtre.
    """

    def __init__(self, parent, theme: Theme, app: "Application"):
        super().__init__(parent, bg=UI["surface"])
        self.theme, self.app = theme, app
        self.legende, self.lien = entete_panneau(self, theme, "Copier le texte", self.copier)
        self.blocs: List[gr.Bloc] = []
        self._generation = 0                      # numéro de l'affichage en cours (rendu progressif)

        cadre = tk.Frame(self, bg=UI["surface"])
        cadre.pack(fill="both", expand=True, pady=(theme.px(6), 0))
        self.texte = tk.Text(cadre, bg=UI["surface"], fg=UI["encre"], relief="flat", bd=0,
                             highlightthickness=0, wrap="word", cursor="arrow", width=1, height=1,
                             font=theme.polices["texte"], padx=theme.px(2), pady=0)
        defil = ttk.Scrollbar(cadre, orient="vertical", command=self.texte.yview)
        defil_h = ttk.Scrollbar(cadre, orient="horizontal", command=self.texte.xview)
        self.texte.configure(yscrollcommand=barre_automatique(defil, side="right", fill="y",
                                                              before=self.texte),
                             xscrollcommand=barre_automatique(defil_h, side="bottom", fill="x",
                                                              before=self.texte))
        self.texte.pack(side="left", fill="both", expand=True)
        px, P = theme.px, theme.polices
        t = self.texte
        t.tag_configure("donnees", font=P["petit"], foreground=UI["encre2"], background=UI["plan"],
                        lmargin1=px(10), lmargin2=px(10), rmargin=px(10), spacing1=px(8), spacing3=px(8))
        t.tag_configure("numero", font=P["titre_bloc"], foreground=UI["accent"], spacing1=px(22), spacing3=px(4))
        t.tag_configure("titre", font=P["titre_bloc"], foreground=UI["encre"], spacing1=px(22), spacing3=px(4))
        t.tag_configure("texte", font=P["texte"], foreground=UI["encre2"], spacing1=px(4), spacing3=px(2))
        t.tag_configure("formule", spacing1=px(8), spacing3=px(4))
        # Copie de devoir : sous-parties, applications numériques (en retrait), résultats encadrés
        t.tag_configure("question", font=P["champ"], foreground=UI["encre"], spacing1=px(14), spacing3=px(2))
        t.tag_configure("an", lmargin1=px(22), lmargin2=px(22), spacing1=px(2), spacing3=px(4))
        t.tag_configure("resultat", spacing1=px(4), spacing3=px(10))
        t.tag_configure("detail", font=P["petit"], foreground=UI["discret"], lmargin1=px(4), lmargin2=px(4),
                        spacing1=px(1), spacing3=px(6))
        t.tag_configure("valeurs", font=P["texte"], foreground=UI["encre"], lmargin1=px(22), lmargin2=px(22),
                        spacing1=px(1), spacing3=px(8))
        t.tag_configure("respecte", font=P["texte"], foreground=UI["succes"], lmargin1=px(4),
                        spacing1=px(2), spacing3=px(2))
        t.tag_configure("non_respecte", font=P["texte"], foreground=UI["erreur"], lmargin1=px(4),
                        spacing1=px(2), spacing3=px(2))
        # En-tête d'un tableau récapitulatif : bandeau gris sur toute la largeur ; un peu d'air
        # entre la dernière ligne d'un tableau et le texte qui suit
        t.tag_configure("entete", font=P["champ"], foreground=UI["encre2"], background=UI["plan"],
                        spacing1=px(8), spacing3=px(4))
        t.tag_configure("apres_tableau", spacing1=px(10))
        self.police_texte = tkfont.Font(font=P["texte"])
        self.police_entete = tkfont.Font(font=P["champ"])
        self.images: List[tk.PhotoImage] = []

    # ------------------------------------------------------------------ formules
    def _reglages(self) -> dict:
        return dict(taille=15, dpi=96 * self.theme.echelle, couleur=UI["encre"], fond=UI["surface"])

    def _image(self, tex: str, cadre: Optional[Tuple[str, str]] = None) -> tk.PhotoImage:
        """Image Tk d'une formule (rendue par matplotlib, ou reprise du cache), encadrée si
        `cadre` est donné (résultat).

        Une formule plus large que la zone de texte (petit écran, grand texte) est rendue un
        peu plus petite, jusqu'à 60 % ; au-delà, la barre de défilement horizontale prend le relais."""
        reglages = self._reglages()
        image = tk.PhotoImage(data=base64.b64encode(gr.formule_png(tex, cadre=cadre, **reglages)).decode("ascii"))
        place = self.texte.winfo_width() - self.theme.px(14)
        if place > 100 and image.width() > place:
            reglages["dpi"] = reglages["dpi"] * max(0.6, place / image.width())
            image = tk.PhotoImage(data=base64.b64encode(gr.formule_png(tex, cadre=cadre, **reglages)).decode("ascii"))
        self.images.append(image)                   # garder une référence, sinon l'image disparaît
        return image

    @staticmethod
    def _expression(b: gr.Bloc) -> Tuple[str, Optional[Tuple[str, str]]]:
        """Formule à rendre pour un bloc et son cadre : « A.N. : » devant une application
        numérique, cadre autour d'un résultat."""
        if b.genre == "an":
            return gr.TEX_AN + b.tex, None
        if b.genre == "resultat":
            return b.tex, gr.CADRE_RESULTAT
        return b.tex, None

    def _rendre_suite(self, generation: int, attente: List[tuple]) -> None:
        """Rend la formule suivante et la place à son emplacement (rendu progressif)."""
        if generation != self._generation or not self.winfo_exists() or not attente:
            return
        marque, tex, cadre, etiquette = attente.pop(0)
        image = self._image(tex, cadre)
        self.texte.configure(state="normal")
        self.texte.image_create(marque, image=image)
        self.texte.tag_add(etiquette, marque)               # retrait de la ligne (A.N.)
        self.texte.mark_unset(marque)
        self.texte.configure(state="disabled")
        if attente:
            self.winfo_toplevel().after(1, self._rendre_suite, generation, attente)

    # ------------------------------------------------------------------ tableaux
    def _tabulations(self, lignes: List[Tuple[str, bool]]) -> tuple:
        """Taquets de tabulation adaptés aux colonnes d'un groupe de lignes (texte, en-tête ?)."""
        colonnes = [(ligne.split("\t"), entete) for ligne, entete in lignes]
        largeurs = [0] * max(len(c) for c, _ in colonnes)
        for c, entete in colonnes:
            police = self.police_entete if entete else self.police_texte
            for i, morceau in enumerate(c):
                largeurs[i] = max(largeurs[i], police.measure(morceau))
        taquets, x = [], self.theme.px(4)
        for largeur in largeurs[:-1]:
            x += largeur + self.theme.px(22)
            taquets.append(x)
        return tuple(taquets)

    # ------------------------------------------------------------------ affichage
    def afficher(self, res: mt.Resultat) -> None:
        """Écrit les étapes du calcul pour le résultat donné."""
        self.blocs = gr.etapes_du_calcul(res, self.app.choix_series(), self.app.pont_actif())
        self.legende.configure(text="Les six étapes rédigées comme une copie : formule, application numérique, "
                                     "résultat encadré.")
        self._generation += 1
        reglages = self._reglages()
        attente: List[tuple] = []
        t = self.texte
        t.configure(state="normal")
        t.delete("1.0", "end")
        for marque in t.mark_names():
            if marque.startswith("formule"):
                t.mark_unset(marque)
        self.images.clear()
        px = self.theme.px

        # Les lignes en colonnes d'un même tableau (même étape, même nom) : mêmes tabulations
        tableaux: Dict[Tuple[int, str], List[Tuple[str, bool]]] = {}
        etape = 0
        for b in self.blocs:
            if b.genre == "etape":
                etape += 1
            elif b.genre in ("ligne", "entete"):
                tableaux.setdefault((etape, b.tableau), []).append((b.texte, b.genre == "entete"))
        for (numero, nom), lignes in tableaux.items():
            t.tag_configure(f"tableau{numero}_{nom}", font=self.theme.polices["texte"], foreground=UI["encre"],
                            lmargin1=px(4), tabs=self._tabulations(lignes), spacing1=px(3), spacing3=px(1))
        t.tag_raise("entete")                       # l'en-tête garde sa police et son fond
        t.tag_raise("apres_tableau")

        etape = 0
        precedent = ""
        for b in self.blocs:
            apres = ("apres_tableau",) if precedent == "ligne" and b.genre in ("texte", "detail") else ()
            precedent = b.genre
            if b.genre == "etape":
                etape += 1
                if b.numero:
                    t.insert("end", f"Étape {b.numero}", "numero")
                    t.insert("end", f"  ·  {b.texte}\n", "titre")
                else:
                    t.insert("end", f"{b.texte}\n", "titre")
            elif b.genre in ("formule", "an", "resultat"):
                tex, cadre = self._expression(b)
                if gr.formule_en_cache(tex, cadre=cadre, **reglages):
                    debut = t.index("end-1c")
                    t.image_create(debut, image=self._image(tex, cadre))
                    t.tag_add(b.genre, debut)
                else:                               # rendue juste après, sans bloquer
                    marque = f"formule{len(attente)}"
                    t.mark_set(marque, "end-1c")
                    t.mark_gravity(marque, "left")
                    attente.append((marque, tex, cadre, b.genre))
                t.insert("end", "\n", b.genre)
            elif b.genre == "question":
                t.insert("end", insecable(b.texte) + "\n", "question")
            elif b.genre in ("ligne", "entete"):
                t.insert("end", b.texte + "\n", (f"tableau{etape}_{b.tableau}",)
                         + (("entete",) if b.genre == "entete" else ()))
            elif b.genre == "controle":
                t.insert("end", ("✓  " if b.ok else "✕  ") + b.texte + ("" if b.ok else "   non respecté") + "\n",
                         "respecte" if b.ok else "non_respecte")
            elif b.genre in ("texte", "detail", "donnees", "valeurs"):
                t.insert("end", insecable(b.texte) + "\n", (b.genre,) + apres)
        t.configure(state="disabled")
        t.yview_moveto(0)
        if attente:
            self.winfo_toplevel().after(1, self._rendre_suite, self._generation, attente)

    def copier(self) -> None:
        """Copie les étapes en texte simple (pour un compte rendu)."""
        if not self.blocs:
            return
        self.clipboard_clear()
        self.clipboard_append(gr.texte_etapes(self.blocs))
        self.lien.confirmer("Texte copié")


class CarteCellule(tk.Frame):
    """Carte d'une cellule dans la liste de l'onglet Composants : nom et fréquence, montage,
    puis Q, m et q. Un clic (ou Entrée, Espace) la choisit."""

    def __init__(self, parent, theme: Theme, etage: mt.Etage, commande: Callable[[], None]):
        super().__init__(parent, bg=UI["surface"], highlightthickness=1, highlightbackground=UI["trait"],
                         cursor="hand2", takefocus=1)
        px, P = theme.px, theme.polices
        m = etage.montage
        c = m.cellule
        self.etiquettes: List[tk.Widget] = []
        haut = tk.Frame(self, bg=UI["surface"])
        haut.pack(fill="x", padx=px(11), pady=(px(8), 0))
        nom = tk.Label(haut, text=f"Cellule {c.nom}", font=P["champ"], fg=UI["encre"], bg=UI["surface"], anchor="w")
        nom.pack(side="left")
        frequence = tk.Label(haut, text=mt.fmt_si(c.wn / (2 * math.pi), "Hz"), font=P["texte"], fg=UI["encre"],
                             bg=UI["surface"], anchor="e")
        frequence.pack(side="right")
        montage = tk.Label(self, text=m.libelle, font=P["petit"], fg=UI["encre2"], bg=UI["surface"], anchor="w")
        montage.pack(fill="x", padx=px(11))
        if c.ordre == 2:
            coefs = f"Q {mt.fmt_nombre(c.Q, 3)} · m {mt.fmt_decimales(m.m)} · q {mt.fmt_decimales(m.q)}"
        else:
            coefs = f"1er ordre · m {mt.fmt_decimales(m.m)}"
        coefficients = tk.Label(self, text=coefs, font=P["petit"], fg=UI["encre2"], bg=UI["surface"], anchor="w")
        coefficients.pack(fill="x", padx=px(11), pady=(0, px(8)))
        self.etiquettes = [haut, nom, frequence, montage, coefficients]
        for w in [self] + self.etiquettes:
            w.bind("<Button-1>", lambda _e: commande())
        for touche in ("<Return>", "<KP_Enter>", "<space>"):
            self.bind(touche, lambda _e: commande())
        self.bind("<FocusIn>", lambda _e: self._bordure(), add="+")
        self.bind("<FocusOut>", lambda _e: self._bordure(), add="+")
        self.actif = False

    def _bordure(self) -> None:
        try:
            focus = self.focus_get() is self
        except (KeyError, tk.TclError):
            focus = False
        self.configure(highlightbackground=UI["accent"] if (self.actif or focus) else UI["trait"])

    def selectionner(self, actif: bool) -> None:
        """Met la carte en avant (cellule affichée) ou la remet à l'état normal."""
        self.actif = actif
        fond = UI["accent_doux"] if actif else UI["surface"]
        self.configure(bg=fond)
        for w in self.etiquettes:
            w.configure(bg=fond)
        self._bordure()


class PanneauComposants(tk.Frame):
    """Composants du montage : une carte par cellule à gauche ; à droite, le schéma de la cellule
    choisie et le tableau de ses composants (repère, rôle, valeur à câbler, valeur calculée).
    Au-dessus, un seul message court sur les valeurs normalisées, détaillé à la demande."""

    def __init__(self, parent, theme: Theme, app: "Application"):
        super().__init__(parent, bg=UI["surface"])
        self.theme, self.app = theme, app
        px, P = theme.px, theme.polices
        self.etages: List[mt.Etage] = []                # cellules du montage réel (valeurs et repères)
        self.choix: Optional[mt.ChoixSeries] = None     # séries choisies (None : valeurs calculées)
        self.res: Optional[mt.Resultat] = None
        self.cartes: List[CarteCellule] = []
        self.actuelle = 0
        self.photo: Optional[tk.PhotoImage] = None
        self._largeur_schema = 0
        self._attente: Optional[str] = None

        self.legende, self.lien = entete_panneau(self, theme, "Copier le tableau", self.copier)
        info = self.info = tk.Label(self.lien.master, text="?", font=P["petit"], fg=UI["encre2"], bg=UI["surface"],
                                    highlightthickness=1, highlightbackground=UI["trait_fort"], width=2,
                                    cursor="question_arrow")
        info.pack(side="right", padx=(0, px(12)))
        Infobulle(info, theme,
                  "Repères du montage réel, comme dans l'onglet Câblage : R1, R2, R3… et C1, C2, C3… d'un bout à "
                  "l'autre. Dans chaque cellule : d'abord les éléments en série, dans l'ordre du signal, puis la "
                  "contre-réaction (en haut du schéma), puis l'élément vers la masse (en bas). « a + b » : deux "
                  "résistances en série ou deux condensateurs en parallèle, numérotés chacun.")
        defilant = CadreDefilant(self, UI["surface"])
        defilant.pack(fill="both", expand=True)
        zone = self.zone = defilant.interieur

        # Message sur les valeurs normalisées (vert : gabarit respecté, orangé : il ne l'est plus).
        # S'il ne l'est plus : « Corriger les valeurs » (sans toucher à R0 ni à C0) et « Que faire ? »,
        # qui déplie l'explication ; après une correction : ce qui a changé, et « Annuler la correction ».
        # (grille : bouton et liens gardent leur place, le message se replie dans la largeur restante)
        self.cadre_statut = tk.Frame(zone, bg=UI["succes_doux"])
        self.cadre_statut.columnconfigure(0, weight=1)
        self.note_serie = tk.Label(self.cadre_statut, text="", font=P["petit"], anchor="w", justify="left",
                                   bg=UI["succes_doux"])
        self.note_serie.grid(row=0, column=0, sticky="ew", padx=(px(12), px(8)), pady=px(8))
        self.bouton_corriger = BoutonPlat(self.cadre_statut, theme, "Corriger les valeurs", app.corriger_valeurs)
        self.bouton_corriger.configure(font=P["petit"], pady=px(4), padx=px(10))
        Infobulle(self.bouton_corriger, theme,
                  "Cherche d'autres valeurs normalisées qui respectent le gabarit, sans changer R0 ni C0 : pour "
                  "chaque composant, la valeur du dessous ou du dessus, ou une autre association ; si cela ne "
                  "suffit pas, les associations de deux valeurs, puis une série plus fine. Les valeurs trouvées "
                  "sont appliquées tout de suite ; « Annuler la correction » revient en arrière.")
        self.lien_pistes = Lien(self.cadre_statut, theme, "Que faire ?", self._basculer_pistes, UI["alerte_doux"])
        self.lien_pistes.configure(fg=UI["alerte"])
        self.lien_annuler = Lien(self.cadre_statut, theme, "Annuler la correction", app.annuler_correction,
                                 UI["succes_doux"])
        self.cadre_statut.bind("<Configure>", self._replier_statut, add="+")
        self.detail_pistes = tk.Label(zone, text="", font=P["petit"], fg=UI["alerte"], bg=UI["alerte_doux"],
                                      anchor="w", justify="left", padx=px(12), pady=px(8))
        self.detail_pistes.bind("<Configure>",
                                lambda e: self.detail_pistes.configure(wraplength=max(200, e.width - px(30))))
        self.pistes_ouvertes = False
        self._bleus: set = set()          # (cellule, repère) des valeurs ajustées (correction du gabarit)

        # Remarques sur le montage (gain du passe-bande, bande très large, valeurs peu réalistes…)
        self.note = tk.Label(zone, text="", font=P["petit"], fg=UI["encre2"], bg=UI["surface"], anchor="w",
                             justify="left")
        self.note.bind("<Configure>", lambda e: self.note.configure(wraplength=max(200, e.width - px(6))))

        # Corps : liste des cellules à gauche, détail de la cellule choisie à droite. Si la place
        # manque (petite fenêtre, grand zoom), les cartes passent au-dessus du détail, sur plusieurs
        # colonnes, pour laisser au schéma toute la largeur.
        self.corps = tk.Frame(zone, bg=UI["surface"])
        self.gauche = gauche = tk.Frame(self.corps, bg=UI["surface"])
        tk.Label(gauche, text="Cellules", font=P["champ"], fg=UI["encre"], bg=UI["surface"],
                 anchor="w").pack(fill="x", pady=(0, px(6)))
        self.liste = tk.Frame(gauche, bg=UI["surface"])
        self.liste.pack(fill="x")
        self.detail = tk.Frame(self.corps, bg=UI["surface"])
        self._etroit: Optional[bool] = None
        self._colonnes_cartes = 0
        self._disposer()
        self.corps.bind("<Configure>", self._disposer, add="+")
        ligne_titre = tk.Frame(self.detail, bg=UI["surface"])
        ligne_titre.pack(fill="x")
        self.lien_guide = Lien(ligne_titre, theme, "Comment fonctionne cette cellule ?", self._ouvrir_guide,
                               UI["surface"])
        self.lien_guide.pack(side="right")
        self.titre_cellule = tk.Label(ligne_titre, text="", font=P["titre_bloc"], fg=UI["encre"], bg=UI["surface"],
                                      anchor="w")
        self.titre_cellule.pack(side="left", fill="x", expand=True)
        self.sous_titre = tk.Label(self.detail, text="", font=P["petit"], fg=UI["encre2"], bg=UI["surface"],
                                   anchor="w", justify="left")
        self.sous_titre.pack(fill="x", pady=(px(1), px(6)))
        self.sous_titre.bind("<Configure>", lambda e: self.sous_titre.configure(wraplength=max(200, e.width - 4)))
        self.schema = tk.Label(self.detail, bg=UI["surface"], anchor="w")
        self.schema.pack(fill="x")
        self.detail.bind("<Configure>", self._redimensionne, add="+")
        cadre_table = tk.Frame(self.detail, bg=UI["trait"])
        cadre_table.pack(fill="x", pady=(px(8), 0))
        self.table = ttk.Treeview(cadre_table, show="headings", selectmode="none", height=4)
        self.table.pack(fill="x", padx=1, pady=1)
        self.table.tag_configure("pair", background="#F8FAFC")
        self.table.tag_configure("ajuste", foreground=UI["accent"])
        # Largeurs naturelles des colonnes ; la colonne « Rôle » prend la place qui reste
        self._largeurs: Dict[str, int] = {}
        self.table.bind("<Configure>", self._ajuster_colonnes, add="+")
        self.legende_schema = tk.Label(self.detail, text="", font=P["petit"], fg=UI["discret"], bg=UI["surface"],
                                       anchor="w", justify="left")
        self.legende_schema.pack(fill="x", pady=(px(6), px(10)))
        self.legende_schema.bind("<Configure>",
                                 lambda e: self.legende_schema.configure(wraplength=max(200, e.width - 4)))

        # Message pour le coupe-bande
        self.vide = tk.Label(zone, text="", font=P["texte"], fg=UI["encre2"], bg=UI["surface"],
                             justify="center", wraplength=px(600))

    # ------------------------------------------------------------------ affichage
    def afficher(self, res: mt.Resultat) -> None:
        """Remplit l'onglet pour le résultat donné : message, remarques, cartes et première cellule."""
        px = self.theme.px
        for w in (self.cadre_statut, self.detail_pistes, self.note, self.corps, self.vide):
            w.pack_forget()
        self.res = res
        g = res.gabarit
        choix = self.choix = self.app.choix_series()
        pont = self.app.pont_actif()
        # Étages du montage réel : valeurs à câbler et repères (R1, R2, R3… d'un bout à l'autre)
        self.etages = mt.etages_reels(res, choix, pont)

        self.lien.pack_forget()
        self.info.pack_forget()
        if not res.montages:      # coupe-bande : rien à dimensionner
            self.legende.configure(text="Aucun composant à calculer.")
            self.vide.configure(text=insecable("La structure de Sallen & Key ne permet pas de réaliser un "
                                               "coupe-bande.\nLes fonctions de transfert et les diagrammes de "
                                               "Bode restent disponibles."))
            self.vide.pack(fill="both", expand=True, pady=px(60))
            return
        self.lien.pack(side="right")
        self.info.pack(side="right", padx=(0, px(12)))

        # Ligne de résumé : nombre de cellules, séries et options du montage
        n = len(self.etages)
        morceaux = [f"{n} cellule{'s' if n > 1 else ''}"]
        ajustes = mt.composants_ajustes(res, choix, pont) if choix else []
        if choix:
            morceaux += [f"résistances {choix.resistances}" if choix.resistances else "résistances calculées",
                         f"condensateurs {choix.condensateurs}" if choix.condensateurs else "condensateurs calculés"]
            if choix.associations:
                morceaux.append("associations")
            if ajustes:
                morceaux.append(f"{len(ajustes)} valeur{'s' if len(ajustes) > 1 else ''} "
                                f"ajustée{'s' if len(ajustes) > 1 else ''}")
        else:
            morceaux.append("valeurs calculées")
        if pont:
            morceaux.append("pont diviseur d'entrée")
        if res.passe_haut_dabord:
            morceaux.append("passe-haut d'abord")
        self.legende.configure(text=insecable(" · ".join(morceaux)))

        # Message sur les valeurs normalisées : écart et contrôle du gabarit avec ces valeurs
        self._bleus = set()
        if choix:
            self._afficher_statut(res, choix, ajustes)

        # Remarques sur le montage, en une ou deux lignes discrètes
        notes = list(res.remarques_montage)
        if g.type == "PM":
            gain = 20 * math.log10(res.gain_montage())
            phrase = f"Gain du montage à f0 : {mt.fmt_nombre(gain, 3)} dB (les cellules ont un gain unité)."
            if res.attenuateur():
                phrase += " " + mt.phrase_pont(res, pont, choix)
            notes.append(phrase)
        self.note.configure(text=insecable("\n".join(notes)))
        if notes:
            self.note.pack(fill="x", pady=(px(8), 0))

        # Cartes des cellules
        for carte in self.cartes:
            carte.destroy()
        self.cartes = []
        for i, e in enumerate(self.etages):
            carte = CarteCellule(self.liste, self.theme, e, lambda i=i: self.choisir(i))
            for touche, pas in (("<Up>", -1), ("<Down>", 1), ("<Left>", -1), ("<Right>", 1)):
                carte.bind(touche, lambda _e, i=i, pas=pas: self._voisine(i + pas))
            self.cartes.append(carte)
        self._colonnes_cartes = 0
        self._disposer_cartes()
        self.corps.pack(fill="x", pady=(px(14), 0))
        self.choisir(min(self.actuelle, len(self.etages) - 1) if self.etages else 0, garder=True)

    def _afficher_statut(self, res: mt.Resultat, choix: mt.ChoixSeries,
                         ajustes: List[Tuple[mt.Etage, str, mt.Realisation]]) -> None:
        """Message sur les valeurs normalisées, ses actions et, en dessous, le détail : ce que la
        correction a changé, pourquoi elle n'a rien trouvé, ou l'explication de « Que faire ? »."""
        px = self.theme.px
        ecart, composant, cellule = mt.ecart_etages(self.etages)
        points = res.points_controle_serie(choix)
        respecte = all(p.ok for p in points)
        correction = self.app.correction_affichee()
        nom = composant.replace(" + ", "\u00a0+\u00a0")          # « R5 + R6 » jamais coupé
        ecart_txt = (f"Écart maximal {mt.fmt_compact(100 * ecart, 2)} %, sur {nom} (cellule\u00a0{cellule})."
                     if composant else "Écart nul.")
        detail: Optional[Tuple[str, bool]] = None          # (texte, vert ?)
        # En bleu dans le tableau : les valeurs ajustées, c'est-à-dire autres que la valeur
        # normalisée la plus proche (définition stable, reprise dans les étapes et les exports)
        self._bleus = {(e.montage.cellule.nom, e.designation(cle)) for e, cle, _ in ajustes}
        if correction is not None and correction.trouvee:
            texte = ("✓  Correction appliquée : avec ces valeurs normalisées, le gabarit est respecté, "
                     f"sans changer R0 ni C0. {ecart_txt}")
            detail = (self._texte_correction(correction), True)
        elif respecte and ajustes:
            n = len(ajustes)
            texte = (f"✓  {n} valeur{'s' if n > 1 else ''} ajustée{'s' if n > 1 else ''} pour respecter le "
                     f"gabarit (en bleu dans le tableau), sans changer R0 ni C0. {ecart_txt}")
        elif respecte:
            texte = f"✓  Avec ces valeurs normalisées, le gabarit reste respecté. {ecart_txt}"
        else:
            fautifs = [p for p in points if not p.ok]
            gains = ", ".join(f"G({p.nom}) = {mt.fmt_nombre(p.G, 3)} dB" for p in fautifs)
            texte = f"⚠  Avec ces valeurs normalisées, {gains} : le gabarit n'est plus respecté. {ecart_txt}"
            if correction is not None:                       # recherche faite, sans résultat
                detail = (self._texte_echec(res, choix), False)
            elif self.pistes_ouvertes:
                detail = (self._texte_pistes(res, choix), False)
        fond, encre = (UI["succes_doux"], UI["succes"]) if respecte else (UI["alerte_doux"], UI["alerte"])
        self.cadre_statut.configure(bg=fond)
        self.note_serie.configure(text=insecable(texte), fg=encre, bg=fond)
        # Actions : « Corriger les valeurs » et « Que faire ? » tant que rien n'a été essayé ;
        # « Annuler la correction » quand des valeurs ont été changées par la correction
        actions = []
        if not respecte and correction is None:
            actions += [self.bouton_corriger, self.lien_pistes]
        if (correction is not None and correction.trouvee) or ajustes:
            actions.append(self.lien_annuler)
        for w in (self.bouton_corriger, self.lien_pistes, self.lien_annuler):
            if w not in actions:
                w.grid_remove()
        for colonne, w in enumerate(actions, start=1):
            if w is not self.bouton_corriger:
                w.configure(bg=fond)
            w.grid(row=0, column=colonne, sticky="e", padx=(0, px(12)), pady=px(8))
        if respecte or correction is not None:
            self.pistes_ouvertes = False
        self._replier_statut()
        self.cadre_statut.pack(fill="x", pady=(px(8), 0))
        if detail is not None:
            vert = detail[1]
            self.detail_pistes.configure(text=insecable(detail[0]), fg=UI["succes"] if vert else UI["alerte"],
                                         bg=UI["succes_doux"] if vert else UI["alerte_doux"])
            self.detail_pistes.pack(fill="x")

    @staticmethod
    def _texte_correction(correction: mt.Correction) -> str:
        """Ce que la correction a changé : séries ou options, composants, gains obtenus."""
        lignes = []
        leviers = correction.leviers()
        if leviers:
            verbes = [f"activé les {l}" if l.startswith("associations") else f"choisi des {l}" for l in leviers]
            lignes.append("La correction a " + " et ".join(verbes) + ".")
        n = len(correction.changements)
        if n:
            lignes.append(f"Par rapport aux valeurs d'avant, {n} composant{'s' if n > 1 else ''} "
                          f"change{'nt' if n > 1 else ''} :")
            for c in correction.changements[:12]:
                lignes.append(f"   •  {c.designation} (cellule {c.cellule}, {c.role}) : {c.avant} → {c.apres}")
            if n > 12:
                lignes.append(f"   … et {n - 12} autre{'s' if n > 13 else ''} (voir le tableau de chaque cellule).")
        gains = ", ".join(f"G({p.nom}) = {mt.fmt_nombre(p.G, 3)} dB" for p in correction.points)
        lignes.append(f"Avec ces valeurs : {gains}. Le gain reste aussi au-dessus de Gp dans toute la bande passante.")
        return "\n".join(lignes)

    @staticmethod
    def _texte_echec(res: mt.Resultat, choix: mt.ChoixSeries) -> str:
        """La correction n'a rien trouvé : jusqu'où elle a cherché, et ce qui reste possible."""
        types = [t for t, s in (("résistances", choix.resistances), ("condensateurs", choix.condensateurs)) if s]
        quoi = " et des ".join(types)
        texte = (f"Aucune correction trouvée : même avec des {quoi} E24 et des associations de deux valeurs, "
                 "aucune combinaison de valeurs normalisées ne respecte le gabarit sans changer R0 ni C0.")
        q_max = max((c.Q for c in res.cellules if c.Q), default=0)
        if q_max > 3:
            texte += (f" Les cellules à Q élevé (jusqu'à Q = {mt.fmt_nombre(q_max, 3)} ici) sont trop sensibles "
                      "aux écarts des valeurs normalisées.")
        return texte + ("\nSolutions : gardez les valeurs calculées (« Calculées » dans les listes Résistances "
                        "et Condensateurs), ou laissez un peu de marge au gabarit.")

    @property
    def cellules_affichees(self) -> List[str]:
        """Noms des cellules, dans l'ordre des cartes (ordre de câblage)."""
        return [e.montage.cellule.nom for e in self.etages]

    def _voisine(self, i: int) -> str:
        if 0 <= i < len(self.cartes):
            self.choisir(i)
            self.cartes[i].focus_set()
        return "break"

    def choisir(self, i: int, garder: bool = False) -> None:
        """Affiche la cellule numéro i : carte en avant, titre, schéma et tableau de ses composants."""
        if not (0 <= i < len(self.etages)):
            return
        self.actuelle = i
        for j, carte in enumerate(self.cartes):
            carte.selectionner(j == i)
        e = self.etages[i]
        m = e.montage
        c = m.cellule
        f = mt.fmt_si(c.wn / (2 * math.pi), "Hz")
        self.titre_cellule.configure(text=f"Cellule {c.nom} · {m.libelle}")
        caracteristiques = (f"fréquence de coupure {f}" if c.ordre == 1 else f"f0 = {f} · Q = {mt.fmt_nombre(c.Q)}")
        # Valeurs de référence : celle qui a été choisie (R0 des cellules passe-bas, C0 des cellules
        # passe-haut), puis celle qui s'en déduit
        w_nom = "ω0" if self.res is not None and self.res.gabarit.type == "PM" else "ωp"
        R0 = mt.fmt_si(m.R0, "Ω", compact=True)
        C0 = mt.fmt_si(m.C0, "F", compact=True)
        if m.cellule.nature == "PH":
            reference = f"C0 = {C0} (choisi), R0 = {R0}"
        else:
            reference = f"R0 = {R0} (choisie), C0 = {C0}"
        self.sous_titre.configure(text=insecable(f"{caracteristiques} · valeurs de référence {reference} "
                                                 f"(R0·C0·{w_nom} = 1)"))
        self._largeur_schema = 0
        self._rendre_schema()

        # Tableau des composants de la cellule : repère, rôle, valeur à câbler (et valeur calculée)
        colonnes = ["repere", "role", "valeur"] + (["calculee"] if self.choix else [])
        titres = {"repere": "Repère", "role": "Rôle", "valeur": "À câbler" if self.choix else "Valeur",
                  "calculee": "Calculée"}
        lignes = []
        for cle in e.ordre:
            ligne = [e.designation(cle), e.role(cle).capitalize(), e.valeur(cle)]
            if self.choix:
                ligne.append(mt.fmt_si(e.calcules[cle], "Ω" if cle[0] == "R" else "F", 4))
            lignes.append(ligne)
        self.table.configure(columns=colonnes, height=len(lignes))
        police = tkfont.Font(font=self.theme.polices["texte"])
        police_titre = tkfont.Font(font=self.theme.polices["petit"])
        self._largeurs = {}
        for j, col in enumerate(colonnes):
            largeur = max([police.measure(l[j]) for l in lignes] + [police_titre.measure(titres[col])])
            self._largeurs[col] = largeur + self.theme.px(26)
            self.table.heading(col, text=titres[col], anchor="w")
            self.table.column(col, width=self._largeurs[col], minwidth=self.theme.px(40), anchor="w", stretch=False)
        self._ajuster_colonnes()
        self.table.delete(*self.table.get_children())
        bleues = 0
        for k, valeurs in enumerate(lignes):
            tags = ("pair",) if k % 2 else ()
            if (c.nom, valeurs[0]) in self._bleus:            # valeur ajustée par la correction
                tags += ("ajuste",)
                bleues += 1
            self.table.insert("", "end", values=valeurs, tags=tags)

        # Sous le tableau : précisions propres à la cellule
        precisions = []
        if self.choix:
            precisions.append(f"Valeurs normalisées ({self.choix.court()}) ; « Calculée » : valeur exacte du calcul.")
        if bleues:
            precisions.append("En bleu : valeur" + ("s" if bleues > 1 else "") + " ajustée" + ("s" if bleues > 1
                              else "") + " pour respecter le gabarit, à la place de la valeur normalisée la plus "
                              "proche.")
        if m.structure == "RAUCH":
            precisions.append("Passe-bande de Rauch : une cellule de Sallen & Key à gain unité ne dépasse pas "
                              "Q = 0,5. Cette cellule, inverseuse, a un gain de −1/2 à f0.")
        if e.pont:
            precisions.append(f"Pont diviseur d'entrée : {e.designation('R1')} côté entrée et "
                              f"{e.designation('Rb')} vers la masse remplacent la résistance d'entrée.")
        if e.suiveur:
            precisions.append(f"Suivie d'un µA741 monté en suiveur ({e.suiveur}) : le calcul suppose des étages "
                              "isolés.")
        self.legende_schema.configure(text=insecable(" ".join(precisions)))

    def _ouvrir_guide(self) -> None:
        """« Comment fonctionne cette cellule ? » : le chapitre du guide qui l'explique."""
        if self.etages:
            structure = self.etages[self.actuelle].montage.structure
            self.app.ouvrir_guide(guide.CHAPITRE_DE_STRUCTURE.get(structure, 5))

    # ------------------------------------------------------------------ disposition
    def _disposer(self, _e=None) -> None:
        """Cartes à gauche du détail, ou au-dessus quand le détail aurait moins de 560 px
        (à 100 %) : le schéma reste lisible dans une petite fenêtre."""
        px = self.theme.px
        largeur = self.corps.winfo_width()
        etroit = bool(largeur > 1 and largeur < px(236 + 20 + 560))
        if etroit != self._etroit:
            self._etroit = etroit
            self.gauche.grid_forget()
            self.detail.grid_forget()
            if etroit:
                self.corps.columnconfigure(0, minsize=0, weight=1)
                self.corps.columnconfigure(1, minsize=0, weight=0)
                self.gauche.grid(row=0, column=0, sticky="new", pady=(0, px(12)))
                self.detail.grid(row=1, column=0, sticky="new")
            else:
                self.corps.columnconfigure(0, minsize=px(236), weight=0)
                self.corps.columnconfigure(1, minsize=0, weight=1)
                self.gauche.grid(row=0, column=0, sticky="new", padx=(0, px(20)))
                self.detail.grid(row=0, column=1, sticky="new")
        self._disposer_cartes()

    def _disposer_cartes(self) -> None:
        """Cartes en une colonne (à gauche) ou sur autant de colonnes que la largeur le permet."""
        if not self.cartes:
            return
        px = self.theme.px
        k = 1
        if self._etroit:
            k = max(1, min(len(self.cartes), (self.corps.winfo_width() + px(8)) // px(228)))
        if k == self._colonnes_cartes:
            return
        self._colonnes_cartes = k
        for j in range(max(k, len(self.cartes)) + 1):
            self.liste.columnconfigure(j, weight=1 if j < k else 0, uniform="cartes" if j < k else "")
        for i, carte in enumerate(self.cartes):
            carte.grid(row=i // k, column=i % k, sticky="nsew", padx=(0 if i % k == 0 else px(8), 0),
                       pady=(0, px(6)))

    def _ajuster_colonnes(self, _e=None) -> None:
        """Colonnes du tableau à leur largeur naturelle ; la colonne « Rôle » prend la place qui
        reste, pour que le tableau occupe toute la largeur du détail."""
        if not self._largeurs:
            return
        dispo = self.table.winfo_width() - 2
        if dispo < 100:
            return
        reste = max(0, dispo - sum(self._largeurs.values()))
        for col, largeur in self._largeurs.items():
            voulue = largeur + (reste if col == "role" else 0)
            if int(self.table.column(col, "width")) != voulue:
                self.table.column(col, width=voulue)

    def _replier_statut(self, _e=None) -> None:
        """Message sur les valeurs normalisées replié dans la largeur laissée par le bouton et
        les liens affichés à sa droite."""
        largeur = self.cadre_statut.winfo_width()
        if largeur <= 1:
            largeur = self.zone.winfo_width()
        if largeur <= 1:
            return
        px = self.theme.px
        place = largeur - px(20) - 4
        for w in (self.bouton_corriger, self.lien_pistes, self.lien_annuler):
            if w.winfo_manager():
                place -= w.winfo_reqwidth() + px(12)
        place = max(px(200), place)
        if int(self.note_serie.cget("wraplength")) != place:
            self.note_serie.configure(wraplength=place)

    # ------------------------------------------------------------------ schéma
    def _redimensionne(self, _e=None) -> None:
        """Largeur du détail changée : le schéma est redessiné un peu plus tard (une seule fois)."""
        if self._attente is not None:
            self.after_cancel(self._attente)
        self._attente = self.after(150, self._rendre_schema)

    def _rendre_schema(self) -> None:
        """Schéma de la cellule choisie, rendu à la largeur du détail (au plus 760 px à 100 %) :
        tout est réduit d'un même rapport, les étiquettes restent à leur place."""
        self._attente = None
        if not self.etages or not self.winfo_exists():
            return
        largeur = min(self.detail.winfo_width() - 2, self.theme.px(760))
        if largeur < 200:
            largeur = self.theme.px(640)
        if abs(largeur - self._largeur_schema) < 8 and self.photo is not None:
            return
        self._largeur_schema = largeur
        fig = Figure(figsize=(8, 2.6), dpi=100, facecolor=UI["surface"])
        FigureCanvasAgg(fig)
        gr.dessiner_cellule(fig, self.etages[self.actuelle])
        tampon = io.BytesIO()
        fig.savefig(tampon, format="png", dpi=largeur / 8, facecolor=UI["surface"])
        self.photo = tk.PhotoImage(data=base64.b64encode(tampon.getvalue()).decode("ascii"))
        self.schema.configure(image=self.photo)

    # ------------------------------------------------------------------ que faire ?
    def _basculer_pistes(self) -> None:
        """« Que faire ? » : explication et solutions, sous le message."""
        self.pistes_ouvertes = not self.pistes_ouvertes
        if self.pistes_ouvertes and self.res is not None and self.choix is not None:
            self.detail_pistes.configure(text=insecable(self._texte_pistes(self.res, self.choix)),
                                         fg=UI["alerte"], bg=UI["alerte_doux"])
            self.detail_pistes.pack(fill="x", after=self.cadre_statut)
        else:
            self.detail_pistes.pack_forget()

    @staticmethod
    def _texte_pistes(res: mt.Resultat, choix: mt.ChoixSeries) -> str:
        """Pourquoi le gabarit n'est plus respecté, et ce qu'on peut changer."""
        texte = ("Le calcul place le gain exactement à Gp en fp : il n'y a aucune marge, et l'arrondi des "
                 "valeurs suffit à franchir la limite.")
        q_max = max((c.Q for c in res.cellules if c.Q), default=0)
        if q_max > 3:
            texte += (f" Les cellules à Q élevé (jusqu'à Q = {mt.fmt_nombre(q_max, 3)} ici) sont très sensibles "
                      "aux valeurs des composants.")
        return texte + ("\n« Corriger les valeurs » cherche d'autres valeurs normalisées qui respectent le "
                        "gabarit, sans changer R0 ni C0 : pour chaque composant, la valeur du dessous ou du "
                        "dessus, ou une autre association ; si cela ne suffit pas, les associations de deux "
                        "valeurs, puis une série plus fine. Autre solution : laisser un peu de marge au gabarit.")

    # ------------------------------------------------------------------ copie
    def copier(self) -> None:
        """Copie les composants, un par ligne (colonnes séparées par des tabulations : se colle
        dans Excel ou Word) : repère, cellule, montage, rôle, valeur (et valeur calculée)."""
        if not self.etages:
            return
        lignes = []
        if self.choix:
            lignes.append(f"Valeurs normalisées : {self.choix.libelle()}")
        lignes.append("\t".join(["Repère", "Cellule", "Montage", "Rôle", "Valeur"]
                                + (["Valeur calculée"] if self.choix else [])))
        for e in self.etages:
            for cle in e.ordre:
                ligne = [e.designation(cle), e.montage.cellule.nom, e.montage.libelle, e.role(cle), e.valeur(cle)]
                if self.choix:
                    ligne.append(mt.fmt_si(e.calcules[cle], "Ω" if cle[0] == "R" else "F", 4))
                lignes.append("\t".join(ligne))
        self.clipboard_clear()
        self.clipboard_append("\n".join(lignes))
        self.lien.confirmer("Tableau copié")


class PanneauCablage(tk.Frame):
    """Schéma de câblage du montage réel : cellules câblées avec des µA741 (broches,
    alimentation ±15 V), brochage du circuit, nomenclature et notes pratiques."""

    def _menu_netlist(self) -> None:
        """« Netlist SPICE… » : LTspice ou PSpice, au choix, dans un petit menu sous le lien."""
        menu = tk.Menu(self, tearoff=False, font=self.theme.polices["texte"])
        menu.add_command(label="Pour LTspice…", command=lambda: self.app.exporter_netlist("ltspice"))
        menu.add_command(label="Pour PSpice (version étudiante comprise)…",
                         command=lambda: self.app.exporter_netlist("pspice"))
        x = self.lien_netlist.winfo_rootx()
        y = self.lien_netlist.winfo_rooty() + self.lien_netlist.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def __init__(self, parent, theme: Theme, app: "Application"):
        super().__init__(parent, bg=UI["surface"])
        self.theme, self.app = theme, app
        self.res: Optional[mt.Resultat] = None
        self.figure: Optional[Figure] = None
        self.photo: Optional[tk.PhotoImage] = None
        self._largeur_rendue = 0
        self._attente: Optional[str] = None

        self.legende, self.lien = entete_panneau(self, theme, "Enregistrer le schéma…", self.enregistrer)
        self.lien_copie = Lien(self.lien.master, theme, "Copier la nomenclature", self.copier, UI["surface"])
        self.lien_copie.pack(side="right", padx=(0, theme.px(18)))
        self.lien_netlist = Lien(self.lien.master, theme, "Netlist SPICE…", self._menu_netlist, UI["surface"])
        self.lien_netlist.pack(side="right", padx=(0, theme.px(18)))
        Infobulle(self.lien_netlist, theme,
                  "Exporte le montage pour un simulateur : LTspice ou PSpice (version étudiante comprise). "
                  "Mêmes repères et mêmes valeurs que ce schéma ; amplificateurs décrits par un modèle à un "
                  "pôle, sans transistor (comme la courbe « µA741 réel »).")
        self.zone = ZoneImage(self, UI["surface"])
        self.zone.pack(fill="both", expand=True, pady=(theme.px(8), 0))
        self.zone.bind("<Configure>", self._redimensionne)
        self.vide = tk.Label(self, text="", font=theme.polices["texte"], fg=UI["encre2"], bg=UI["surface"],
                             justify="center", wraplength=theme.px(520))

    def afficher(self, res: mt.Resultat) -> None:
        """Dessine le schéma de câblage du résultat (rien pour le coupe-bande)."""
        nouveau = res is not self.res
        self.res = res
        if not res.montages:
            for w in (self.zone, self.lien, self.lien_copie):
                w.pack_forget()
            self.legende.configure(text="Aucun montage à câbler.")
            self.vide.configure(text="La structure de Sallen & Key ne permet pas de réaliser un coupe-bande : "
                                     "il n'y a pas de schéma de câblage.")
            self.vide.pack(fill="both", expand=True, pady=self.theme.px(60))
            self.figure = None
            return
        if not self.zone.winfo_ismapped():
            self.vide.pack_forget()
            self.lien.pack(side="right")
            self.lien_copie.pack(side="right", padx=(0, self.theme.px(18)))
            self.zone.pack(fill="both", expand=True, pady=(self.theme.px(8), 0))
        self._dessiner(garder_position=not nouveau)

    def _largeur_disponible(self) -> int:
        """Largeur utile pour l'image (pixels), barre de défilement déduite."""
        largeur = self.zone.winfo_width() if self.zone.winfo_width() > 1 else self.winfo_width()
        return max(largeur, self.theme.px(480)) - self.theme.px(14)

    # Le schéma est affiché 10 % plus grand que sa taille nominale, pour des textes bien lisibles.
    ZOOM = 1.1

    def _dessiner(self, garder_position: bool = False) -> None:
        """Construit la figure (graphes.schema_cablage) et l'affiche sous forme d'image."""
        self._attente = None
        if self.res is None or not self.res.montages:
            return
        choix = self.app.choix_series()
        largeur = self._largeur_disponible()
        dpi = 96 * self.theme.echelle * self.ZOOM
        pont = self.app.pont_actif()
        self.figure = gr.schema_cablage(self.res, choix, largeur / dpi, pont)
        self.photo = image_tk(self.figure, dpi)
        self.zone.afficher(self.photo, garder_position)
        self._largeur_rendue = largeur
        aops = mt.amplificateurs(mt.etages_reels(self.res, choix, pont))
        valeurs = f"valeurs normalisées ({choix.court()})" if choix else "valeurs calculées"
        gain = ""
        if self.res.attenuateur():
            gain = (", avec pont diviseur d'entrée (gain 0 dB à f0)" if pont else
                    f", sans pont diviseur (gain {mt.fmt_nombre(20 * math.log10(self.res.gain_montage()), 3)} dB "
                    "à f0)")
        self.legende.configure(text=f"Montage réel : {len(aops)} {mt.AOP_NOM}, {valeurs}{gain}. "
                                    "Brochage, nomenclature et notes sous le schéma.")

    def _redimensionne(self, event) -> None:
        """Nouvelle largeur : le schéma est réorganisé (lignes d'étages) après une courte pause."""
        if self.res is None or abs(event.width - self.theme.px(14) - self._largeur_rendue) < self.theme.px(40):
            return
        if self.app.onglets.actif != self.app.ONGLETS.index("Câblage"):
            self.app._a_jour[self.app.ONGLETS.index("Câblage")] = False     # redessiné à l'affichage
            return
        racine = self.winfo_toplevel()
        if self._attente is not None:
            racine.after_cancel(self._attente)
        self._attente = racine.after(250, lambda: self.winfo_exists() and self._dessiner(garder_position=True))

    def enregistrer(self) -> None:
        """Enregistre le schéma complet (avec nomenclature et notes) en PNG, PDF ou SVG."""
        if self.figure is None:
            return
        chemin = self.app.demander_enregistrement(
            "Enregistrer le schéma de câblage", f"{self.app.nom_base()}_cablage.png", ".png",
            [("Image PNG", "*.png"), ("Document PDF", "*.pdf"), ("Image vectorielle SVG", "*.svg")])
        if chemin:
            self.figure.savefig(chemin, dpi=200, facecolor="white")
            self.lien.confirmer("Schéma enregistré")

    def copier(self) -> None:
        """Copie la nomenclature (colonnes séparées par des tabulations : se colle dans Excel)."""
        if self.res is None or not self.res.montages:
            return
        choix = self.app.choix_series()
        lignes = ["Catégorie\tValeur\tQuantité\tRepères"]
        lignes += [f"{l.categorie}\t{l.valeur}\t{l.quantite}\t{l.reperes}"
                   for l in mt.nomenclature(mt.etages_reels(self.res, choix, self.app.pont_actif()), choix)]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lignes))
        self.lien_copie.confirmer("Nomenclature copiée")


class Accueil(tk.Frame):
    """Zone des résultats tant qu'aucun filtre n'est calculé (filtre neuf, gabarit incomplet,
    autre type de filtre) : ce qu'il reste à faire, et ce que montreront les onglets."""

    ETAPES = [
        "Choisissez le type de filtre.",
        "Saisissez le gabarit : les fréquences limites en Hz, puis Gp et Ga en dB. Le croquis montre "
        "les zones interdites au fur et à mesure.",
        "Cliquez sur « Calculer le filtre » ou appuyez sur Entrée. Avec « Calcul automatique », le calcul "
        "part dès que le gabarit est complet.",
    ]

    def __init__(self, parent, theme: Theme, visite: Optional[Callable[[], None]] = None,
                 cours: Optional[Callable[[], None]] = None):
        super().__init__(parent, bg=UI["surface"])
        self.theme = theme
        px, P = theme.px, theme.polices
        self.bloc = tk.Frame(self, bg=UI["surface"])
        self.textes: List[Tuple[tk.Label, int]] = []      # (texte, retrait) : largeur de coupure

        def texte(parent, contenu: str, police, couleur: str, retrait: int = 0) -> tk.Label:
            etiquette = tk.Label(parent, text=insecable(contenu), font=police, fg=couleur, bg=UI["surface"],
                                 anchor="w", justify="left")
            self.textes.append((etiquette, retrait))
            return etiquette

        texte(self.bloc, "Aucun filtre calculé", P["marque"], UI["encre"]).pack(fill="x")
        texte(self.bloc, "Les diagrammes de Bode, les étapes du calcul, les composants et le câblage "
                         "s'afficheront ici.", P["texte"], UI["encre2"]).pack(fill="x", pady=(px(4), px(22)))
        diametre = px(26)
        for numero, contenu in enumerate(self.ETAPES, start=1):
            ligne = tk.Frame(self.bloc, bg=UI["surface"])
            ligne.pack(fill="x", pady=(0, px(14)))
            pastille = tk.Canvas(ligne, width=diametre, height=diametre, bg=UI["surface"], highlightthickness=0)
            pastille.create_oval(1, 1, diametre - 1, diametre - 1, fill=UI["accent_doux"], outline=UI["accent"])
            pastille.create_text(diametre / 2, diametre / 2, text=str(numero), font=P["champ"], fill=UI["accent"])
            pastille.pack(side="left", anchor="n")
            texte(ligne, contenu, P["texte"], UI["encre"], retrait=diametre + px(12)).pack(
                side="left", fill="x", padx=(px(12), 0))
        texte(self.bloc, "Un filtre déjà enregistré : Fichier > Ouvrir un filtre (Ctrl+O).", P["petit"],
              UI["discret"]).pack(fill="x", pady=(px(4), 0))
        if visite is not None:
            Lien(self.bloc, theme, "Découvrir la fenêtre : visite guidée", visite, UI["surface"]).pack(
                anchor="w", pady=(px(6), 0))
        if cours is not None:
            Lien(self.bloc, theme, "Débutant ? Comprendre Sallen & Key en dix chapitres (F2)", cours,
                 UI["surface"]).pack(anchor="w", pady=(px(4), 0))
        self.bind("<Configure>", lambda _e: self._disposer())

    def _disposer(self) -> None:
        """Bloc d'au plus 560 px de large, centré, un peu au-dessus du milieu de la zone."""
        px = self.theme.px
        utile = max(px(220), min(px(560), self.winfo_width() - px(48)))
        for etiquette, retrait in self.textes:
            etiquette.configure(wraplength=max(px(120), utile - retrait))
        self._largeur = utile
        self.after_idle(self._placer)

    def _placer(self) -> None:
        if not self.winfo_exists():
            return
        px = self.theme.px
        largeur, hauteur = self.winfo_width(), self.winfo_height()
        utile = getattr(self, "_largeur", px(560))
        y = max(px(16), int((hauteur - self.bloc.winfo_reqheight()) * 0.4))
        self.bloc.place(x=max(0, (largeur - utile) // 2), y=y, width=utile)


class VisiteGuidee:
    """Visite guidée de la fenêtre (premier lancement, menu Aide, lien de l'accueil) : chaque
    étape éclaire une zone et l'explique dans une bulle. Rien n'est saisi ni modifié.

    La fenêtre est photographiée (Pillow, installé avec matplotlib), puis recouverte de cette
    photo assombrie où seule la zone de l'étape reste claire. Si la photo est impossible
    (macOS, qui demanderait l'autorisation d'enregistrer l'écran), un cadre bleu entoure la
    zone et la bulle s'affiche par-dessus la fenêtre.
    """

    # (zone, titre, texte) ; zone : clé de Application.zone_visite(), ou « menu:Nom »
    ETAPES = [
        ("types", "Type de filtre",
         "Choisissez le filtre à calculer : passe-bas, passe-haut, passe-bande ou coupe-bande. "
         "Chaque type garde ses propres valeurs."),
        ("gabarit", "Gabarit",
         "Saisissez les fréquences limites (en Hz) et les gains Gp et Ga (en dB). Le croquis dessine "
         "les zones interdites pendant la frappe et signale une incohérence. Formats acceptés : "
         "2400, 2,4k, 10n, 4k7."),
        ("composants", "Composants et options",
         "Composant de référence (R0 ou C0), choisi librement, puis séries des résistances et des "
         "condensateurs : valeurs calculées, ou E6, E12, E24. Les options se déplient en dessous : "
         "associations de deux valeurs, pont diviseur du passe-bande, calcul automatique."),
        ("calcul", "Calcul",
         "« Calculer le filtre » (ou la touche Entrée) lance la synthèse ; la ligne d'état confirme la "
         "fin du calcul. Avec l'option « Calcul automatique », le filtre est recalculé dès que le gabarit "
         "est complet."),
        ("bandeau", "Résultats clés",
         "Après le calcul : ordre minimal, sélectivité k, ondulation ε, valeur de référence et nombre "
         "de cellules du montage."),
        ("onglets", "Onglets",
         "Diagrammes de Bode normalisé et réel, étapes du calcul détaillées, composants de "
         "chaque cellule (« Corriger les valeurs » si les valeurs normalisées sortent du gabarit) "
         "et câblage avec des µA741. Ctrl+1 à Ctrl+5 changent d'onglet ; à droite, l'indicateur "
         "« Gabarit respecté »."),
        ("menu:Fichier", "Menu Fichier",
         "Enregistrer le filtre (fichier .filtre) pour le rouvrir ou l'envoyer, créer le compte rendu "
         "PDF (Ctrl+P), exporter le rapport, les images et la netlist pour LTspice ou PSpice. La "
         "saisie est aussi gardée à la fermeture."),
        ("menu:Aide", "Aide",
         "Laissez la souris un instant sur un élément pour lire son explication. Le menu Aide contient "
         "le mode d'emploi (F1), un petit cours pour comprendre Sallen & Key (F2), les raccourcis "
         "clavier, les nouveautés de la version et cette visite."),
    ]
    MENUS = ["Fichier", "Affichage", "Aide"]        # ordre de la barre de menus
    TEINTE = (27, 42, 58)                            # UI["encre"] : couleur du voile

    def __init__(self, app: "Application", etape: int = 0):
        self.app, self.theme = app, app.theme
        self.etape = max(0, min(etape, len(self.ETAPES) - 1))
        self.active = True
        self.photo = None                          # photo de la fenêtre (PIL.Image), ou None
        self.photo_possible = sys.platform != "darwin"
        self._fond = self._clair = None            # images Tk du voile (gardées en mémoire)
        self.voile: Optional[tk.Canvas] = None
        self.bulle: Optional[tk.Frame] = None
        self.cadre: List[tk.Frame] = []
        # Sonde invisible (sous tout le reste) : signale les changements de taille de la fenêtre
        self.sonde = tk.Frame(app, bg=UI["surface"])
        self.sonde.place(x=0, y=0, relwidth=1, relheight=1)
        self.sonde.lower()
        self._taille = (app.winfo_width(), app.winfo_height())
        self.sonde.bind("<Configure>", self._taille_changee)
        # Démarrage différé : un menu qui vient de se fermer est d'abord effacé de l'écran
        self._attente: Optional[str] = app.after(150, lambda: self._photographier_puis(
            lambda: self.afficher(self.etape)))

    # ------------------------------------------------------------------ cycle
    def arreter(self) -> None:
        """Fin de la visite (Passer, Terminer, Échap) ou fenêtre reconstruite."""
        if not self.active:
            return
        self.active = False
        if self._attente is not None:
            self.app.after_cancel(self._attente)
            self._attente = None
        for widget in [self.voile, self.bulle, self.sonde] + self.cadre:
            if widget is not None and widget.winfo_exists():
                widget.destroy()
        self.voile = self.bulle = None
        self.cadre = []
        self._fond = self._clair = None

    def terminer(self) -> None:
        self.arreter()
        self.app.fin_visite()

    def suivant(self) -> None:
        if self.etape + 1 < len(self.ETAPES):
            self.afficher(self.etape + 1)
        else:
            self.terminer()

    def precedent(self) -> None:
        if self.etape > 0:
            self.afficher(self.etape - 1)

    def _touches(self, widget: tk.Widget) -> None:
        for touche in ("<Right>", "<Return>", "<KP_Enter>", "<space>"):
            widget.bind(touche, lambda _e: self.suivant())
        for touche in ("<Left>", "<BackSpace>"):
            widget.bind(touche, lambda _e: self.precedent())
        widget.bind("<Escape>", lambda _e: self.terminer())

    # ------------------------------------------------------------------ photo
    def _photographier_puis(self, suite: Callable[[], None]) -> None:
        """Photo de la fenêtre telle qu'elle est (voile et bulle retirés), puis `suite`."""
        self._attente = None
        if not self.active:
            return
        if not self.photo_possible:
            suite()
            return
        self._effacer()
        if self.voile is not None:
            self.voile.place_forget()
        self.app.update_idletasks()

        def prendre() -> None:
            self._attente = None
            if not self.active:
                return
            self.photo, self._fond = self._capture(), None
            if self.photo is not None:
                try:                               # photo assombrie, prête à afficher
                    from PIL import Image, ImageTk
                    sombre = Image.blend(self.photo, Image.new("RGB", self.photo.size, self.TEINTE), 0.62)
                    self._fond = ImageTk.PhotoImage(sombre, master=self.app)
                except Exception:                  # lien Pillow–Tk absent
                    self.photo = None
            if self.photo is None:
                self.photo_possible = False        # mode simple : cadre bleu et bulle
            suite()

        self._attente = self.app.after(120, prendre)          # le temps que la fenêtre se redessine

    def _capture(self):
        try:
            from PIL import ImageGrab
            self.app.update_idletasks()
            x, y = self.app.winfo_rootx(), self.app.winfo_rooty()
            largeur, hauteur = self.app.winfo_width(), self.app.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + largeur, y + hauteur), all_screens=True).convert("RGB")
            return image if image.size == (largeur, hauteur) else None
        except Exception:                          # Pillow absent ou trop ancien, écran inaccessible…
            return None

    def _taille_changee(self, event) -> None:
        """Fenêtre agrandie ou réduite : nouvelle photo une fois le redimensionnement fini."""
        taille = (event.width, event.height)
        if not self.active or taille == self._taille:
            return
        self._taille = taille
        if self._attente is not None:
            self.app.after_cancel(self._attente)
        self._effacer()
        if self.voile is not None:
            self.voile.place_forget()
        self._attente = self.app.after(350, lambda: self._photographier_puis(lambda: self._dessiner(self.etape)))

    # ------------------------------------------------------------------ étapes
    def afficher(self, i: int) -> None:
        """Étape i : la zone est d'abord amenée à l'écran si la colonne de saisie doit défiler."""
        if not self.active:
            return
        self.etape = i
        zone = self.ETAPES[i][0]
        widgets = self.app.zone_visite(zone)
        if widgets and self._defiler_vers(widgets) and self.photo is not None:
            self._photographier_puis(lambda: self._dessiner(i))   # la photo ne correspond plus
            return
        self._dessiner(i)

    def _defiler_vers(self, widgets: List[tk.Widget]) -> bool:
        """Fait défiler la colonne de saisie pour montrer la zone. Renvoie True si elle a défilé."""
        colonne = self.app.colonne
        dedans = [w for w in widgets if str(w).startswith(str(colonne.interieur))]
        if not dedans:
            return False
        avant = colonne.canvas.yview()
        colonne.montrer(dedans[-1])
        colonne.montrer(dedans[0])                 # le haut de la zone en priorité
        return colonne.canvas.yview() != avant

    def _rectangle(self, widgets: List[tk.Widget]) -> Optional[Tuple[int, int, int, int]]:
        """Rectangle de la zone dans la fenêtre (partie visible seulement), avec une marge."""
        ax, ay = self.app.winfo_rootx(), self.app.winfo_rooty()
        boites = [(w.winfo_rootx() - ax, w.winfo_rooty() - ay,
                   w.winfo_rootx() - ax + w.winfo_width(), w.winfo_rooty() - ay + w.winfo_height())
                  for w in widgets if w.winfo_ismapped()]
        if not boites:
            return None
        x1, y1 = min(b[0] for b in boites), min(b[1] for b in boites)
        x2, y2 = max(b[2] for b in boites), max(b[3] for b in boites)
        colonne = self.app.colonne
        if any(str(w).startswith(str(colonne.interieur)) for w in widgets):
            c = colonne.canvas
            cx, cy = c.winfo_rootx() - ax, c.winfo_rooty() - ay
            x1, y1 = max(x1, cx), max(y1, cy)
            x2, y2 = min(x2, cx + c.winfo_width()), min(y2, cy + c.winfo_height())
        m = self.theme.px(6)
        largeur, hauteur = self.app.winfo_width(), self.app.winfo_height()
        x1, y1, x2, y2 = max(0, x1 - m), max(0, y1 - m), min(largeur, x2 + m), min(hauteur, y2 + m)
        return (x1, y1, x2, y2) if x2 - x1 > 8 and y2 - y1 > 8 else None

    def _effacer(self) -> None:
        if self.bulle is not None and self.bulle.winfo_exists():
            self.bulle.destroy()
        self.bulle = None
        for cadre in self.cadre:
            if cadre.winfo_exists():
                cadre.destroy()
        self.cadre = []
        if self.voile is not None and self.voile.winfo_exists():
            self.voile.delete("all")

    def _dessiner(self, i: int) -> None:
        if not self.active:
            return
        zone = self.ETAPES[i][0]
        widgets = self.app.zone_visite(zone)
        rect = self._rectangle(widgets) if widgets else None
        self._effacer()
        if self.photo is not None:
            self._dessiner_voile(rect)
        else:
            self._dessiner_cadre(rect)
        self.bulle = self._creer_bulle(i)
        self._placer_bulle(rect, zone)

    def _dessiner_voile(self, rect: Optional[Tuple[int, int, int, int]]) -> None:
        """Photo assombrie sur toute la fenêtre, zone de l'étape en clair, cerclée de bleu."""
        from PIL import ImageTk
        if self.voile is None or not self.voile.winfo_exists():
            self.voile = tk.Canvas(self.app, highlightthickness=0, bd=0, bg=UI["encre"], cursor="arrow",
                                   takefocus=1)
            self._touches(self.voile)
        self.voile.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(self.voile)                   # (Canvas.lift déplace les éléments dessinés)
        self.voile.create_image(0, 0, image=self._fond, anchor="nw")
        if rect is not None:
            x1, y1, x2, y2 = rect
            self._clair = ImageTk.PhotoImage(self.photo.crop(rect), master=self.app)
            self.voile.create_image(x1, y1, image=self._clair, anchor="nw")
            e = max(2, self.theme.px(2.5))
            self.voile.create_rectangle(x1 - e / 2, y1 - e / 2, x2 + e / 2, y2 + e / 2, outline=UI["accent"],
                                        width=e)
        self.voile.focus_set()

    def _dessiner_cadre(self, rect: Optional[Tuple[int, int, int, int]]) -> None:
        """Sans photo : cadre bleu autour de la zone, la fenêtre restant visible."""
        if rect is None:
            return
        x1, y1, x2, y2 = rect
        e = max(2, self.theme.px(3))
        for x, y, largeur, hauteur in ((x1, y1, x2 - x1, e), (x1, y2 - e, x2 - x1, e),
                                       (x1, y1, e, y2 - y1), (x2 - e, y1, e, y2 - y1)):
            trait = tk.Frame(self.app, bg=UI["accent"])
            trait.place(x=x, y=y, width=largeur, height=hauteur)
            trait.lift()
            self.cadre.append(trait)

    def _creer_bulle(self, i: int) -> tk.Frame:
        px, P = self.theme.px, self.theme.polices
        _zone, titre, texte = self.ETAPES[i]
        derniere = i == len(self.ETAPES) - 1
        fond = UI["surface"]
        parent = self.voile if self.photo is not None else self.app
        bulle = tk.Frame(parent, bg=fond, takefocus=1, highlightthickness=0 if self.photo is not None else 2,
                         highlightbackground=UI["accent"], highlightcolor=UI["accent"])
        corps = tk.Frame(bulle, bg=fond)
        corps.pack(fill="both", expand=True, padx=px(18), pady=px(14))
        tk.Frame(corps, bg=fond, width=px(336), height=1).pack()     # même largeur à chaque étape
        tk.Label(corps, text=f"Visite guidée · {i + 1}/{len(self.ETAPES)}", font=P["petit"], fg=UI["discret"],
                 bg=fond, anchor="w").pack(fill="x")
        tk.Label(corps, text=titre, font=P["titre_bloc"], fg=UI["encre"], bg=fond, anchor="w").pack(
            fill="x", pady=(px(2), px(6)))
        tk.Label(corps, text=insecable(texte), font=P["texte"], fg=UI["encre2"], bg=fond, anchor="w",
                 justify="left", wraplength=px(320)).pack(fill="x")
        if i == 0:
            tk.Label(corps, text=insecable("Flèches ← → ou Entrée pour avancer ou reculer, Échap pour quitter."),
                     font=P["petit"], fg=UI["discret"], bg=fond, anchor="w", justify="left",
                     wraplength=px(320)).pack(fill="x", pady=(px(8), 0))
        boutons = tk.Frame(corps, bg=fond)
        boutons.pack(fill="x", pady=(px(14), 0))
        if not derniere:
            Lien(boutons, self.theme, "Passer", self.terminer, fond).pack(side="left")
        bouton = BoutonPlat(boutons, self.theme, "Terminer" if derniere else "Suivant  ▸", self.suivant)
        bouton.configure(pady=px(6), padx=px(16))
        bouton.pack(side="right")
        if i > 0:
            Lien(boutons, self.theme, "◂  Précédent", self.precedent, fond).pack(side="right", padx=(0, px(16)))
        if self.photo is None:
            self._touches(bulle)
        return bulle

    def _x_menu(self, nom: str) -> int:
        """Abscisse (approchée) du milieu d'un menu de la barre, au-dessus de la fenêtre."""
        try:
            police = tkfont.nametofont("TkMenuFont")
        except tk.TclError:
            police = tkfont.Font(font=self.theme.polices["petit"])
        marge = round((8 if sys.platform.startswith("win") else 6) * self.theme.ecran)
        x = 0
        for libelle in self.MENUS:
            largeur = police.measure(libelle)
            if libelle == nom:
                return x + marge + largeur // 2
            x += largeur + 2 * marge
        return marge

    def _placer_bulle(self, rect: Optional[Tuple[int, int, int, int]], zone: str) -> None:
        """Bulle à droite de la zone, sinon dessous, au-dessus ou à gauche, avec sa flèche ;
        pour un menu, en haut, la flèche pointant vers la barre de menus."""
        px = self.theme.px
        bulle = self.bulle
        bulle.update_idletasks()
        bw, bh = bulle.winfo_reqwidth(), bulle.winfo_reqheight()
        largeur, hauteur = self.app.winfo_width(), self.app.winfo_height()
        marge, ecart, demi = px(12), px(18), px(10)

        def borner(v: float, bas: float, haut: float) -> int:
            return int(max(bas, min(v, haut)))

        fleche = None
        if rect is None:
            mx = self._x_menu(zone.split(":", 1)[1]) if zone.startswith("menu:") else largeur // 2
            bx = borner(mx - px(48), marge, largeur - bw - marge)
            by = ecart + px(6)
            if zone.startswith("menu:"):
                fleche = ((mx, 1), (mx - demi, by), (mx + demi, by))
        else:
            x1, y1, x2, y2 = rect
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if x2 + ecart + bw + marge <= largeur:                    # à droite
                bx, by = x2 + ecart, borner(y1, marge, hauteur - bh - marge)
                py = borner(cy, by + px(26), by + bh - px(26))
                fleche = ((x2 + 3, py), (bx, py - demi), (bx, py + demi))
            elif y2 + ecart + bh + marge <= hauteur:                  # dessous
                bx, by = borner(x1 + px(24), marge, largeur - bw - marge), y2 + ecart
                fx = borner(cx, bx + px(30), bx + bw - px(30))
                fleche = ((fx, y2 + 3), (fx - demi, by), (fx + demi, by))
            elif y1 - ecart - bh >= marge:                            # au-dessus
                bx, by = borner(x1 + px(24), marge, largeur - bw - marge), y1 - ecart - bh
                fx = borner(cx, bx + px(30), bx + bw - px(30))
                fleche = ((fx, y1 - 3), (fx - demi, by + bh), (fx + demi, by + bh))
            elif x1 - ecart - bw >= marge:                            # à gauche
                bx, by = x1 - ecart - bw, borner(y1, marge, hauteur - bh - marge)
                py = borner(cy, by + px(26), by + bh - px(26))
                fleche = ((x1 - 3, py), (bx + bw, py - demi), (bx + bw, py + demi))
            else:                                                     # fenêtre trop petite : au centre
                bx, by = max(0, (largeur - bw) // 2), max(0, (hauteur - bh) // 2)
        if self.photo is not None:
            if fleche is not None:
                self.voile.create_polygon(*[v for point in fleche for v in point], fill=UI["surface"], outline="")
            self.voile.create_window(bx, by, window=bulle, anchor="nw")
        else:
            bulle.place(x=bx, y=by)
            bulle.lift()
            bulle.focus_set()


class FenetreGuide(tk.Toplevel):
    """Aide > Comprendre Sallen & Key (F2) : petit cours pour débutant, en dix chapitres
    progressifs (contenu dans guide.py). Sommaire à gauche ; à droite, le chapitre : texte,
    formules, schémas et courbes, encadrés « À retenir » et, si un filtre est calculé,
    « Dans votre filtre ». Flèches gauche et droite (ou Page précédente / suivante) : chapitre
    précédent ou suivant ; Échap : fermer."""

    LARGEUR_FIGURE = 700          # largeur maximale des figures (px, texte à 100 %)

    def __init__(self, app: "Application", chapitre: int = 0):
        super().__init__(app, bg=UI["surface"])
        self.app, self.theme = app, app.theme
        px, P = self.theme.px, self.theme.polices
        self.title("Comprendre Sallen & Key")
        self.transient(app)
        largeur = min(px(1080), self.winfo_screenwidth() - px(40))
        hauteur = min(px(800), self.winfo_screenheight() - px(80))
        self.geometry(f"{largeur}x{hauteur}+{app.winfo_rootx() + px(40)}+{app.winfo_rooty() + px(30)}")
        self.minsize(px(640), px(420))
        self.actuel = -1
        self.images: List[tk.PhotoImage] = []
        self._figures: Dict[tuple, tk.PhotoImage] = {}        # figures déjà rendues (dessin, largeur)
        self._largeur = 0
        self._attente: Optional[str] = None

        # Sommaire
        sommaire = tk.Frame(self, bg=UI["plan"], width=px(260))
        sommaire.pack(side="left", fill="y")
        sommaire.pack_propagate(False)
        tk.Label(sommaire, text="Comprendre\nSallen & Key", font=P["marque"], fg=UI["encre"], bg=UI["plan"],
                 anchor="w", justify="left").pack(fill="x", padx=px(20), pady=(px(22), px(6)))
        tk.Label(sommaire, text=insecable("Un petit cours en dix chapitres, du signal au montage réel. Chaque "
                                          "chapitre s'appuie sur le précédent."),
                 font=P["petit"], fg=UI["encre2"], bg=UI["plan"], anchor="w", justify="left",
                 wraplength=px(220)).pack(fill="x", padx=px(20), pady=(0, px(16)))
        self.entrees: List[tk.Label] = []
        for i, ch in enumerate(guide.CHAPITRES):
            entree = tk.Label(sommaire, text=f"{i + 1}.  {ch.titre}", font=P["texte"], fg=UI["encre2"],
                              bg=UI["plan"], anchor="w", justify="left", wraplength=px(212), padx=px(20),
                              pady=px(5), cursor="hand2")
            entree.pack(fill="x")
            entree.bind("<Button-1>", lambda _e, i=i: self.afficher(i))
            self.entrees.append(entree)

        # Chapitre et navigation
        droite = tk.Frame(self, bg=UI["surface"])
        droite.pack(side="left", fill="both", expand=True)
        pied = tk.Frame(droite, bg=UI["surface"])
        pied.pack(side="bottom", fill="x", padx=px(28), pady=(px(8), px(14)))
        self.precedent = BoutonPlat(pied, self.theme, "◀  Précédent", lambda: self.afficher(self.actuel - 1),
                                    "secondaire")
        self.precedent.pack(side="left", ipadx=px(12))
        self.suivant = BoutonPlat(pied, self.theme, "Suivant  ▶", self._suivant)
        self.suivant.pack(side="right", ipadx=px(12))
        self.lien_copier = Lien(pied, self.theme, "Copier le chapitre", self.copier, UI["surface"])
        self.lien_copier.pack(side="right", padx=(0, px(18)))
        self.position = tk.Label(pied, text="", font=P["petit"], fg=UI["discret"], bg=UI["surface"])
        self.position.pack(side="left", padx=px(18))
        cadre = tk.Frame(droite, bg=UI["surface"])
        cadre.pack(fill="both", expand=True, padx=(px(32), px(8)), pady=(px(20), 0))
        t = self.texte = tk.Text(cadre, bg=UI["surface"], fg=UI["encre"], relief="flat", bd=0,
                                 highlightthickness=0, wrap="word", cursor="arrow", width=1, height=1,
                                 font=P["texte"], padx=0, pady=0)
        defil = ttk.Scrollbar(cadre, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=barre_automatique(defil, side="right", fill="y", before=t))
        t.pack(side="left", fill="both", expand=True, padx=(0, px(16)))
        t.tag_configure("numero", font=P["champ"], foreground=UI["accent"], spacing3=px(2))
        t.tag_configure("titre", font=P["marque"], foreground=UI["encre"], spacing3=px(4))
        t.tag_configure("accroche", font=P["texte"], foreground=UI["discret"], spacing3=px(14))
        t.tag_configure("intertitre", font=P["titre_bloc"], foreground=UI["encre"], spacing1=px(16),
                        spacing3=px(4))
        t.tag_configure("texte", font=P["texte"], foreground=UI["encre2"], spacing1=px(4), spacing3=px(4))
        t.tag_configure("puce", font=P["texte"], foreground=UI["encre2"], lmargin1=px(8), lmargin2=px(26),
                        spacing1=px(2), spacing3=px(3))
        t.tag_configure("formule", justify="center", spacing1=px(8), spacing3=px(8))
        t.tag_configure("figure", justify="center", spacing1=px(10), spacing3=px(10))
        for nom, fond, encre in (("retenir", UI["accent_doux"], UI["encre"]), ("filtre", UI["succes_doux"], UI["succes"])):
            # « À retenir » : des puces (retrait des lignes suivantes) ; « Dans votre filtre » : un paragraphe
            t.tag_configure(nom, font=P["texte"], foreground=encre, background=fond, lmargin1=px(16),
                            lmargin2=px(34) if nom == "retenir" else px(16), rmargin=px(16), spacing1=px(2),
                            spacing3=px(2))
            t.tag_configure(nom + "_titre", font=P["champ"], foreground=UI["accent"] if nom == "retenir"
                            else UI["succes"], background=fond, lmargin1=px(16), rmargin=px(16),
                            spacing1=px(10), spacing3=px(2))
            t.tag_configure(nom + "_fin", background=fond, font=(P["petit"][0], 4), spacing3=px(6))
        t.tag_configure("ecart", font=(P["petit"][0], 4))           # blanc entre deux encadrés
        t.tag_raise("retenir_titre")
        t.tag_raise("filtre_titre")
        t.bind("<Configure>", self._redimensionne, add="+")
        for touche, pas in (("<Left>", -1), ("<Prior>", -1), ("<Right>", 1), ("<Next>", 1)):
            self.bind(touche, lambda _e, pas=pas: self.afficher(self.actuel + pas))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.afficher(chapitre)
        self.focus_set()

    # ------------------------------------------------------------------ navigation
    def _suivant(self) -> None:
        if self.actuel >= len(guide.CHAPITRES) - 1:
            self.destroy()
        else:
            self.afficher(self.actuel + 1)

    def afficher(self, i: int) -> None:
        """Affiche le chapitre i (0 à 9), en haut de page."""
        if not 0 <= i < len(guide.CHAPITRES):
            return
        self.actuel = i
        P = self.theme.polices
        for j, entree in enumerate(self.entrees):
            actif = j == i
            entree.configure(fg=UI["accent"] if actif else UI["encre2"], bg=UI["accent_doux"] if actif else UI["plan"],
                             font=P["champ"] if actif else P["texte"])
        dernier = i == len(guide.CHAPITRES) - 1
        self.suivant.texte = "Fermer" if dernier else "Suivant  ▶"
        self.suivant.configure(text=self.suivant.texte)
        self.precedent.configure(fg=UI["discret"] if i == 0 else UI["encre"])
        self.position.configure(text=f"Chapitre {i + 1} sur {len(guide.CHAPITRES)}")
        self._remplir()
        self.texte.yview_moveto(0)

    def actualiser(self) -> None:
        """Nouveau filtre calculé : l'encadré « Dans votre filtre » est réécrit, à la même place."""
        if self.actuel >= 0:
            position = self.texte.yview()[0]
            self._remplir()
            self.texte.yview_moveto(position)

    # ------------------------------------------------------------------ contenu
    def _largeur_figures(self) -> int:
        place = self.texte.winfo_width() - self.theme.px(8)
        if place < 200:
            place = self.theme.px(self.LARGEUR_FIGURE)
        return min(place, self.theme.px(self.LARGEUR_FIGURE))

    def _formule(self, tex: str) -> tk.PhotoImage:
        """Image d'une formule ; réduite (jusqu'à 60 %) si elle dépasse la largeur du texte."""
        reglages = dict(taille=15, dpi=96 * self.theme.echelle, couleur=UI["encre"], fond=UI["surface"])
        image = tk.PhotoImage(data=base64.b64encode(gr.formule_png(tex, **reglages)).decode("ascii"))
        place = self.texte.winfo_width() - self.theme.px(14)
        if place > 100 and image.width() > place:
            reglages["dpi"] *= max(0.6, place / image.width())
            image = tk.PhotoImage(data=base64.b64encode(gr.formule_png(tex, **reglages)).decode("ascii"))
        return image

    def _figure(self, dessin: Callable, hauteur: float, largeur: int) -> tk.PhotoImage:
        """Image d'une figure du guide (schéma ou courbe) à la largeur donnée."""
        cle = (dessin.__name__, largeur)
        if cle not in self._figures:
            fig = Figure(figsize=(8, 8 * hauteur), dpi=100, facecolor=UI["surface"])
            FigureCanvasAgg(fig)
            guide.dessiner(fig, dessin)
            tampon = io.BytesIO()
            fig.savefig(tampon, format="png", dpi=largeur / 8, facecolor=UI["surface"])
            self._figures[cle] = tk.PhotoImage(data=base64.b64encode(tampon.getvalue()).decode("ascii"))
        return self._figures[cle]

    def _remplir(self) -> None:
        """Écrit le chapitre courant."""
        t = self.texte
        ch = guide.CHAPITRES[self.actuel]
        res = self.app.resultat
        t.configure(state="normal")
        t.delete("1.0", "end")
        self.images.clear()
        self._largeur = largeur = self._largeur_figures()
        t.insert("end", f"Chapitre {self.actuel + 1}\n", "numero")
        t.insert("end", ch.titre + "\n", "titre")
        t.insert("end", insecable(ch.accroche) + "\n", "accroche")

        def image(photo: tk.PhotoImage, etiquette: str) -> None:
            debut = t.index("end-1c")
            t.image_create(debut, image=photo)
            t.insert("end", "\n")
            t.tag_add(etiquette, debut, "end-1c")
            self.images.append(photo)

        def encadre(nom: str, titre: str, lignes: List[str]) -> None:
            t.insert("end", "\n", "ecart")
            t.insert("end", titre + "\n", nom + "_titre")
            for ligne in lignes:
                t.insert("end", ligne + "\n", nom)
            t.insert("end", "\n", nom + "_fin")
            t.insert("end", "\n", "ecart")

        for genre, contenu in ch.blocs:
            if genre == "texte":
                t.insert("end", insecable(contenu) + "\n", "texte")
            elif genre == "intertitre":
                t.insert("end", contenu + "\n", "intertitre")
            elif genre == "puces":
                for puce in contenu:
                    t.insert("end", "•  " + insecable(puce) + "\n", "puce")
            elif genre == "formule":
                image(self._formule(contenu[0]), "formule")
            elif genre == "figure":
                dessin, hauteur = contenu
                image(self._figure(dessin, hauteur, largeur), "figure")
            elif genre == "retenir":
                encadre("retenir", "À retenir", ["•  " + insecable(p) for p in contenu])
            elif genre == "filtre" and res is not None:
                texte = contenu(res)
                if texte:
                    encadre("filtre", "Dans votre filtre", [insecable(texte)])
        t.configure(state="disabled")

    def _redimensionne(self, _e=None) -> None:
        """Largeur du texte changée : figures redessinées un peu plus tard, si elle a assez changé."""
        if self._attente is not None:
            self.after_cancel(self._attente)
        self._attente = self.after(250, self._apres_redimension)

    def _apres_redimension(self) -> None:
        self._attente = None
        if self.winfo_exists() and abs(self._largeur_figures() - self._largeur) > self.theme.px(40):
            self.actualiser()

    def copier(self) -> None:
        """Copie le chapitre en texte simple (formules écrites en ligne)."""
        self.clipboard_clear()
        self.clipboard_append(guide.texte_chapitre(self.actuel, self.app.resultat))
        self.lien_copier.confirmer("Chapitre copié")


class Dialogue(tk.Toplevel):
    """Question modale aux couleurs du programme, dont les boutons portent le nom de l'action
    (« Enregistrer », « Ne pas enregistrer », « Annuler ») plutôt que Oui / Non.

    boutons : [(clé, libellé)], le premier est l'action proposée (bouton bleu, touche Entrée) ;
    Échap et la croix de la fenêtre valent `annuler`. reponse : clé du bouton choisi.
    """

    def __init__(self, app: tk.Tk, theme: Theme, titre: str, question: str, explication: str,
                 boutons: List[Tuple[str, str]], annuler: str = "annuler"):
        super().__init__(app, bg=UI["surface"])
        self.reponse: Optional[str] = None
        self.annuler = annuler
        px, P = theme.px, theme.polices
        self.title(titre)
        self.resizable(False, False)
        self.transient(app)
        cadre = tk.Frame(self, bg=UI["surface"])
        cadre.pack(fill="both", expand=True, padx=px(26), pady=(px(22), px(18)))
        tk.Label(cadre, text=insecable(question), font=P["titre_bloc"], fg=UI["encre"], bg=UI["surface"],
                 anchor="w", justify="left", wraplength=px(420)).pack(fill="x")
        if explication:
            tk.Label(cadre, text=insecable(explication), font=P["texte"], fg=UI["encre2"], bg=UI["surface"],
                     anchor="w", justify="left", wraplength=px(420)).pack(fill="x", pady=(px(8), 0))
        rangee = tk.Frame(cadre, bg=UI["surface"])
        rangee.pack(fill="x", pady=(px(22), 0))
        self.boutons: Dict[str, BoutonPlat] = {}
        for rang, (cle, libelle) in reversed(list(enumerate(boutons))):      # alignés à droite, dans l'ordre
            bouton = BoutonPlat(rangee, theme, libelle, lambda c=cle: self.choisir(c),
                                style="principal" if rang == 0 else "secondaire")
            bouton.configure(padx=px(16), pady=px(7))
            bouton.pack(side="right", padx=(px(8), 0))
            self.boutons[cle] = bouton
        self.defaut = boutons[0][0]
        self.bind("<Return>", lambda _e: self.choisir(self.defaut))
        self.bind("<KP_Enter>", lambda _e: self.choisir(self.defaut))
        self.bind("<Escape>", lambda _e: self.choisir(annuler))
        self.protocol("WM_DELETE_WINDOW", lambda: self.choisir(annuler))
        # Centrée sur la fenêtre du programme
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + max(0, (app.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def choisir(self, cle: str) -> None:
        if self.reponse is None:
            self.reponse = cle
            self.destroy()

    def attendre(self) -> str:
        """Affiche la question et attend la réponse (fenêtre du programme bloquée entre-temps)."""
        def bloquer(essais: int = 0) -> None:
            if not self.winfo_exists():
                return
            try:
                self.grab_set()
            except tk.TclError:                    # pas encore affichée : nouvel essai
                if essais < 40:                    # (programmé sur la fenêtre principale, qui reste)
                    self.master.after(50, lambda: bloquer(essais + 1))
        self.lift()
        self.focus_force()
        self.boutons[self.defaut].focus_set()
        bloquer()
        self.wait_window(self)
        return self.reponse or self.annuler


# =============================================================================
# Fenêtre principale
# =============================================================================

class Application(tk.Tk):
    """Fenêtre principale : saisie du gabarit à gauche, résultats à droite."""
    ONGLETS = ["Bode normalisé", "Bode réel", "Étapes du calcul", "Composants", "Câblage"]

    def __init__(self, fichier: Optional[str] = None, annoncer_nouveautes: bool = False):
        activer_haute_resolution()
        identifier_application()
        super().__init__()
        self.preferences = lire_preferences()
        zoom = self.preferences.get("zoom", 1.0)
        if zoom not in [t for _n, t in TAILLES_TEXTE]:
            zoom = 1.0
        self.theme = Theme(self, zoom)
        gr.configurer_matplotlib(self.theme.famille)
        self.title("Synthèse de filtres de Butterworth – Sallen & Key")
        self.configure(bg=UI["surface"])
        self._styles()
        self._icone()

        self.type_courant = "PB"
        self.valeurs: Dict[str, Dict[str, str]] = valeurs_de_depart()     # gabarit vide
        self.entrees: Dict[str, ttk.Entry] = {}
        self.resultat: Optional[mt.Resultat] = None
        # Valeurs des composants : "" (calculées) ou série "E6", "E12", "E24", choisie
        # séparément pour les résistances et les condensateurs.
        self.serie_R = ""
        self.serie_C = ""
        self.associations = False
        # Passe-bande : pont diviseur d'entrée qui ramène le gain à 0 dB (option, décochée par
        # défaut), et ordre des cellules de chaque paire (passe-bas d'abord par défaut)
        self.pont = False
        self.ph_dabord = False
        # Correction du gabarit (onglet Composants) : valeurs choisies à la place de la valeur
        # normalisée la plus proche, pour les séries, les options et le calcul avec lesquels elles
        # ont été trouvées (serie_R, serie_C, associations, pont, signature du calcul) ; dernière
        # recherche, et ce qu'il faut rétablir pour l'annuler. R0 et C0 ne sont jamais modifiés.
        self.ajustements: Tuple[mt.Ajustement, ...] = ()
        self.config_ajustements: Optional[tuple] = None
        self.correction: Optional[mt.Correction] = None
        self._avant_correction: Optional[dict] = None
        # Bode réel : courbe du montage avec de vrais µA741 (option gardée d'une séance à l'autre)
        self.aop_reel = bool(self.preferences.get("aop_reel", False))
        self.var_aop = tk.BooleanVar(value=self.aop_reel)
        # Bode réel : dispersion des composants (montages tirés au hasard dans les tolérances)
        self.dispersion = bool(self.preferences.get("dispersion", False))
        self.var_dispersion = tk.BooleanVar(value=self.dispersion)
        self._a_jour = [False] * len(self.ONGLETS)   # onglets déjà redessinés pour ce résultat
        self._calcul_prevu: Optional[str] = None     # calcul programmé (identifiant de after)
        self._saisie_calculee: Optional[tuple] = None   # saisie du dernier calcul (type, valeurs)
        self.fichier: Optional[str] = None           # filtre ouvert ou enregistré (.filtre)
        self._enregistre: Optional[dict] = None      # son contenu à l'ouverture ou au dernier enregistrement
        self._dialogue: Optional[Dialogue] = None    # question en cours (quitter, enregistrer…)
        # Calcul automatique (option) : recalcul après une courte pause de frappe
        self.calcul_auto = bool(self.preferences.get("calcul_auto", False))
        self._auto_prevu: Optional[str] = None

        # Reprise de la séance précédente : type, valeurs saisies, séries, options, onglet
        onglet = 0
        session = self.preferences.get("session")
        if isinstance(session, dict) and self._appliquer_etat(self._sans_exemples(session)):
            if session.get("onglet") in range(len(self.ONGLETS)):
                onglet = session["onglet"]
            if isinstance(session.get("fichier"), str) and os.path.isfile(session["fichier"]):
                self.fichier = session["fichier"]
                if isinstance(session.get("enregistre"), dict):
                    self._enregistre = session["enregistre"]
        # Tant qu'aucun filtre n'est calculé, la zone des résultats montre l'accueil.
        self._accueil_actif = False
        self.visite: Optional[VisiteGuidee] = None   # visite guidée en cours

        self._construire()
        self._menu()
        self._dimensionner_fenetre()
        self.choisir_type(self.type_courant, calculer=False)
        self.choisir_onglet(onglet)
        self._maj_titre()
        self.protocol("WM_DELETE_WINDOW", self.quitter)
        if fichier:                                  # double-clic sur un fichier .filtre
            self.after(80, lambda: self.ouvrir_filtre(fichier))
        elif self._saisie_complete():                # séance reprise : résultats recalculés
            self.after(80, self.calculer)
        else:                                        # filtre neuf ou gabarit incomplet
            self._vider_resultats()
        if not fichier and not self.preferences.get("visite_vue"):
            self.after(700, self._visite_premier_lancement)    # une seule fois, fenêtre affichée
        elif annoncer_nouveautes and not fichier and self.preferences.get("version") != VERSION:
            self.after(700, self._nouveautes_mise_a_jour)      # nouvelle version : une seule fois

    # ------------------------------------------------------------------ styles
    def _styles(self) -> None:
        """Apparence des widgets ttk : champs de saisie, tableau, barres de défilement."""
        px = self.theme.px
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Champ.TEntry", fieldbackground=UI["surface"], foreground=UI["encre"],
                        bordercolor=UI["trait_fort"], lightcolor=UI["trait_fort"], darkcolor=UI["trait_fort"],
                        insertcolor=UI["encre"], padding=(px(8), px(5)))
        style.map("Champ.TEntry", bordercolor=[("focus", UI["accent"])], lightcolor=[("focus", UI["accent"])],
                  darkcolor=[("focus", UI["accent"])])
        style.configure("Lecture.TEntry", fieldbackground=UI["surface"], foreground=UI["encre"],
                        bordercolor=UI["trait_fort"], lightcolor=UI["trait_fort"], darkcolor=UI["trait_fort"],
                        insertcolor=UI["encre"], padding=(px(6), px(2)))
        style.map("Lecture.TEntry", bordercolor=[("focus", UI["accent"])], lightcolor=[("focus", UI["accent"])],
                  darkcolor=[("focus", UI["accent"])])
        style.configure("Erreur.TEntry", fieldbackground=UI["erreur_doux"], foreground=UI["encre"],
                        bordercolor=UI["erreur"], lightcolor=UI["erreur"], darkcolor=UI["erreur"],
                        insertcolor=UI["encre"], padding=(px(8), px(5)))
        # Champ sans bordure propre, dans le cadre de ChampUnite (qui porte la bordure et l'unité)
        for nom, fond in (("Nu.TEntry", UI["surface"]), ("NuErreur.TEntry", UI["erreur_doux"])):
            style.configure(nom, fieldbackground=fond, foreground=UI["encre"], bordercolor=fond, lightcolor=fond,
                            darkcolor=fond, insertcolor=UI["encre"], padding=(px(8), px(5), px(2), px(5)))
            style.map(nom, bordercolor=[("focus", fond)], lightcolor=[("focus", fond)], darkcolor=[("focus", fond)])
        style.configure("Treeview", background=UI["surface"], fieldbackground=UI["surface"],
                        foreground=UI["encre"], rowheight=px(32), borderwidth=0,
                        font=self.theme.polices["texte"])
        style.map("Treeview", background=[("selected", UI["accent_doux"])],
                  foreground=[("selected", UI["encre"])])
        style.configure("Treeview.Heading", background=UI["surface"], foreground=UI["discret"],
                        font=self.theme.polices["petit"], relief="flat", borderwidth=0,
                        padding=(px(4), px(6)))
        style.map("Treeview.Heading", background=[("active", UI["surface"])])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        # Case à cocher sobre : carré blanc bordé de gris, bleu coché
        style.configure("Choix.TCheckbutton", background=UI["plan"], foreground=UI["encre"],
                        font=self.theme.polices["texte"], indicatorbackground=UI["surface"],
                        indicatorforeground=UI["surface"], upperbordercolor=UI["trait_fort"],
                        lowerbordercolor=UI["trait_fort"], indicatorsize=px(12),
                        indicatormargin=(0, 0, px(8), 0), focuscolor=UI["plan"], padding=(0, px(2)))
        style.map("Choix.TCheckbutton",
                  background=[("active", UI["plan"])],
                  foreground=[("disabled", UI["discret"])],
                  indicatorbackground=[("disabled", UI["plan"]), ("selected", UI["accent"])],
                  indicatorforeground=[("disabled", UI["plan"]), ("selected", "white")],
                  upperbordercolor=[("selected", UI["accent"])],
                  lowerbordercolor=[("selected", UI["accent"])])
        # Même case, plus petite, sur le fond blanc des onglets (option du Bode réel)
        style.configure("Option.TCheckbutton", background=UI["surface"], foreground=UI["encre2"],
                        font=self.theme.polices["petit"], indicatorbackground=UI["surface"],
                        indicatorforeground=UI["surface"], upperbordercolor=UI["trait_fort"],
                        lowerbordercolor=UI["trait_fort"], indicatorsize=px(11),
                        indicatormargin=(0, 0, px(6), 0), focuscolor=UI["surface"], padding=(0, px(1)))
        style.map("Option.TCheckbutton",
                  background=[("active", UI["surface"])],
                  foreground=[("disabled", UI["trait_fort"]), ("active", UI["encre"])],
                  indicatorbackground=[("disabled", UI["surface"]), ("selected", UI["accent"])],
                  indicatorforeground=[("disabled", UI["surface"]), ("selected", "white")],
                  upperbordercolor=[("selected", UI["accent"])],
                  lowerbordercolor=[("selected", UI["accent"])])
        style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
            "sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("Vertical.TScrollbar", troughcolor=UI["surface"], background=UI["trait_fort"],
                        bordercolor=UI["surface"], lightcolor=UI["trait_fort"], darkcolor=UI["trait_fort"],
                        gripcount=0, arrowsize=px(9))
        style.map("Vertical.TScrollbar", background=[("active", UI["discret"])])
        style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {
            "sticky": "ew", "children": [("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("Horizontal.TScrollbar", troughcolor=UI["surface"], background=UI["trait_fort"],
                        bordercolor=UI["surface"], lightcolor=UI["trait_fort"], darkcolor=UI["trait_fort"],
                        gripcount=0, arrowsize=px(9))
        style.map("Horizontal.TScrollbar", background=[("active", UI["discret"])])

    def _icone(self) -> None:
        """Icône de la fenêtre et de la barre des tâches.

        Sous Windows, le fichier icone.ico (plusieurs tailles) donne une icône nette
        partout ; ailleurs, l'icône est dessinée par graphes.icone_png en trois tailles.
        """
        ico = chemin_ressource("icone.ico")
        if sys.platform.startswith("win") and os.path.exists(ico):
            try:
                self.iconbitmap(default=ico)
                return
            except tk.TclError:
                pass
        try:
            self._images_icone = [tk.PhotoImage(data=base64.b64encode(gr.icone_png(t)).decode("ascii"))
                                  for t in (128, 64, 32)]
            self.iconphoto(True, *self._images_icone)
        except tk.TclError:
            pass

    def report_callback_exception(self, exc, valeur, trace) -> None:
        """Erreur imprévue pendant une action : message clair plutôt qu'un plantage silencieux
        (le programme installé n'a pas de console). Le détail va dans la console ou le journal."""
        traceback.print_exception(exc, valeur, trace)
        messagebox.showerror("Erreur inattendue",
                             f"Une erreur inattendue s'est produite :\n{valeur}\n\n"
                             "Vous pouvez corriger la saisie et relancer le calcul.", parent=self)

    def _menu(self) -> None:
        """Menus Fichier (filtres, exports), Affichage (taille du texte, onglets, options)."""
        barre = tk.Menu(self)
        fichier = tk.Menu(barre, tearoff=False)
        fichier.add_command(label="Nouveau filtre", accelerator="Ctrl+N", command=self.nouveau)
        fichier.add_command(label="Ouvrir un filtre…", accelerator="Ctrl+O", command=self.ouvrir_filtre)
        fichier.add_command(label="Enregistrer le filtre", accelerator="Ctrl+S", command=self.enregistrer_filtre)
        fichier.add_command(label="Enregistrer le filtre sous…", accelerator="Ctrl+Maj+S",
                            command=lambda: self.enregistrer_filtre(sous=True))
        fichier.add_separator()
        # Exports du résultat : grisés tant qu'aucun filtre n'est calculé
        self._exports = []
        for libelle, raccourci, commande in (
                ("Compte rendu PDF…", "Ctrl+P", self.enregistrer_compte_rendu),
                ("Enregistrer le rapport texte…", "", self.enregistrer_rapport),
                ("Enregistrer le Bode normalisé…", "", lambda: self._enregistrer_bode(0)),
                ("Enregistrer le Bode réel…", "", lambda: self._enregistrer_bode(1)),
                ("Enregistrer le schéma de câblage…", "", lambda: self._enregistrer_bode(4)),
                ("Exporter la netlist LTspice…", "", lambda: self.exporter_netlist("ltspice")),
                ("Exporter la netlist PSpice…", "", lambda: self.exporter_netlist("pspice"))):
            fichier.add_command(label=libelle, accelerator=raccourci, command=commande)
            self._exports.append(fichier.index("end"))
        fichier.add_separator()
        fichier.add_command(label="Quitter", accelerator="Ctrl+Q", command=self.quitter)
        barre.add_cascade(label="Fichier", menu=fichier)
        self.menu_fichier = fichier
        self._maj_exports()

        # Affichage : taille du texte (toute la fenêtre suit), gardée d'une séance à l'autre
        affichage = tk.Menu(barre, tearoff=False)
        self.var_taille = tk.DoubleVar(value=self.theme.zoom)
        for nom, zoom in TAILLES_TEXTE:
            affichage.add_radiobutton(label=f"{nom} ({round(zoom * 100)} %)", variable=self.var_taille,
                                      value=zoom, command=lambda z=zoom: self.changer_taille_texte(z))
        affichage.add_separator()
        for i, nom in enumerate(self.ONGLETS):
            affichage.add_command(label=f"Onglet {nom}", accelerator=f"Ctrl+{i + 1}",
                                  command=lambda i=i: self.choisir_onglet(i))
            self.bind_all(f"<Control-Key-{i + 1}>", lambda _e, i=i: self.choisir_onglet(i))
        affichage.add_command(label="Onglet suivant", accelerator="Ctrl+Tab",
                              command=lambda: self._onglet_voisin(+1))
        # Liées à la fenêtre (et non à « all ») : elles passent avant le Tab de Tk, qui
        # déplacerait seulement le curseur de saisie.
        for touche, sens in (("<Control-Tab>", +1), ("<Control-Shift-Tab>", -1), ("<Control-ISO_Left_Tab>", -1)):
            try:
                self.bind(touche, lambda _e, s=sens: self._onglet_voisin(s))
            except tk.TclError:
                pass                                  # touche inconnue sur ce système
        affichage.add_separator()
        affichage.add_command(label="Agrandir le texte", accelerator="Ctrl++",
                              command=lambda: self._pas_taille(+1))
        affichage.add_command(label="Réduire le texte", accelerator="Ctrl+−",
                              command=lambda: self._pas_taille(-1))
        affichage.add_separator()
        affichage.add_checkbutton(label=f"Bode réel : courbe du {mt.AOP_NOM} réel", variable=self.var_aop,
                                  command=self.basculer_aop)
        affichage.add_checkbutton(label="Bode réel : dispersion des composants", variable=self.var_dispersion,
                                  command=self.basculer_dispersion)
        barre.add_cascade(label="Affichage", menu=affichage)

        # Aide : mode d'emploi et raccourcis (sans Internet), version du programme
        aide = tk.Menu(barre, tearoff=False)
        aide.add_command(label="Visite guidée", command=self.lancer_visite)
        aide.add_command(label="Mode d'emploi", accelerator="F1", command=self.mode_emploi)
        aide.add_command(label="Comprendre Sallen & Key", accelerator="F2", command=self.ouvrir_guide)
        aide.add_command(label="Raccourcis clavier", command=self.raccourcis)
        aide.add_command(label=f"Nouveautés de la version {VERSION}", command=self.nouveautes)
        aide.add_separator()
        aide.add_command(label="À propos", command=self.a_propos)
        barre.add_cascade(label="Aide", menu=aide)
        self.bind_all("<F1>", lambda _e: self.mode_emploi())
        self.bind_all("<F2>", lambda _e: self.ouvrir_guide())
        for touche in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind_all(touche, lambda _e: self._pas_taille(+1))
        for touche in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind_all(touche, lambda _e: self._pas_taille(-1))
        for touche in ("<Control-0>", "<Control-KP_0>"):
            self.bind_all(touche, lambda _e: self.changer_taille_texte(1.0))
        self.configure(menu=barre)
        self.bind_all("<Control-n>", lambda _e: self.nouveau())
        self.bind_all("<Control-o>", lambda _e: self.ouvrir_filtre())
        self.bind_all("<Control-s>", lambda _e: self.enregistrer_filtre())
        self.bind_all("<Control-S>", lambda _e: self.enregistrer_filtre(sous=True))      # Ctrl+Maj+S
        self.bind_all("<Control-q>", lambda _e: self.quitter())
        self.bind_all("<Control-p>", lambda _e: self.enregistrer_compte_rendu())

    def _dimensionner_fenetre(self) -> None:
        """Taille de départ adaptée à l'écran ; plein écran sur les petits écrans."""
        px = self.theme.px
        ecran_l, ecran_h = self.winfo_screenwidth(), self.winfo_screenheight()
        largeur = min(px(1320), ecran_l - px(60))
        hauteur = min(px(880), ecran_h - px(90))
        self.geometry(f"{largeur}x{hauteur}+{max(0, (ecran_l - largeur) // 2)}+"
                      f"{max(0, (ecran_h - hauteur) // 3)}")
        self._ajuster_taille_minimale()
        if ecran_h < px(860):                 # petit écran : fenêtre agrandie au maximum
            try:
                self.state("zoomed")              # Windows
            except tk.TclError:
                try:
                    self.attributes("-zoomed", True)   # Linux
                except tk.TclError:
                    pass

    def _ajuster_taille_minimale(self) -> None:
        """Taille minimale de la fenêtre, à l'échelle de la taille de texte choisie."""
        px = self.theme.px
        ecran_l, ecran_h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.minsize(min(px(980), ecran_l - 40), min(px(600), ecran_h - 80))

    # ------------------------------------------------------------ taille du texte
    def _pas_taille(self, sens: int) -> None:
        """Ctrl+ / Ctrl− : taille de texte suivante ou précédente."""
        tailles = [z for _nom, z in TAILLES_TEXTE]
        rang = min(range(len(tailles)), key=lambda i: abs(tailles[i] - self.theme.zoom))
        self.changer_taille_texte(tailles[max(0, min(len(tailles) - 1, rang + sens))])

    def changer_taille_texte(self, zoom: float) -> None:
        """Affichage > taille du texte : la fenêtre est reconstruite à la nouvelle échelle
        (textes, marges, largeurs et graphiques), avec la même saisie et le même onglet."""
        self.var_taille.set(zoom)
        if abs(zoom - self.theme.zoom) < 1e-6:
            return
        self.preferences["zoom"] = zoom
        enregistrer_preferences(self.preferences)
        if self.entrees:
            self._memoriser_saisies()
        onglet = self.onglets.actif
        if self._calcul_prevu is not None:
            self.after_cancel(self._calcul_prevu)
            self._calcul_prevu = None
        etape_visite = None                           # visite guidée en cours : reprise à la même étape
        if self.visite is not None and self.visite.active:
            etape_visite = self.visite.etape
            self.visite.arreter()
        self.visite = None
        for widget in self.winfo_children():
            if not isinstance(widget, tk.Menu):
                widget.destroy()
        self.entrees = {}
        self._a_jour = [False] * len(self.ONGLETS)
        self.theme = Theme(self, zoom)
        self._styles()
        self._construire()
        self._ajuster_taille_minimale()
        self.choisir_type(self.type_courant, calculer=False)
        self.choisir_onglet(onglet)
        if self.resultat is not None or (self._saisie_complete() and self._saisie_calculee is not None):
            self.calculer()                           # résultats (ou erreur) redessinés à la nouvelle taille
        else:
            self._vider_resultats()
        if etape_visite is not None:
            self.after(250, lambda: self.lancer_visite(etape_visite))

    # -------------------------------------------------------------- construction
    def _construire(self) -> None:
        """Deux colonnes : la saisie à gauche, les résultats à droite."""
        px = self.theme.px
        self.columnconfigure(2, weight=1)
        self.rowconfigure(0, weight=1)

        # Panneau de saisie (gauche) : contenu défilant sur les petits écrans, et pied fixe
        # où le bouton « Calculer le filtre » et l'état du calcul restent toujours visibles.
        gauche = tk.Frame(self, bg=UI["plan"], width=px(340))
        gauche.grid(row=0, column=0, sticky="nsew")
        gauche.grid_propagate(False)
        gauche.pack_propagate(False)
        self._construire_pied(gauche)                  # placé en premier : jamais rogné
        self.colonne = CadreDefilant(gauche, UI["plan"])
        self.colonne.pack(side="top", fill="both", expand=True)
        tk.Frame(self, bg=UI["trait"], width=1).grid(row=0, column=1, sticky="ns")
        self._construire_saisie(self.colonne.interieur)

        # Résultats (droite)
        droite = tk.Frame(self, bg=UI["surface"])
        droite.grid(row=0, column=2, sticky="nsew")
        self._construire_resultats(droite)

    def _section(self, parent, titre: str, haut: int = 18) -> tk.Label:
        """Titre d'une section du panneau de saisie."""
        px = self.theme.px
        etiquette = tk.Label(parent, text=titre, font=self.theme.polices["section"], fg=UI["encre"],
                             bg=UI["plan"], anchor="w")
        etiquette.pack(fill="x", padx=px(22), pady=(px(haut), px(8)))
        return etiquette

    def _construire_pied(self, parent: tk.Frame) -> None:
        """Pied du panneau de saisie, toujours visible : bouton « Calculer le filtre » et état du calcul."""
        px = self.theme.px
        pied = self.pied = tk.Frame(parent, bg=UI["plan"])
        pied.pack(side="bottom", fill="x")
        tk.Frame(pied, bg=UI["trait"], height=1).pack(fill="x")
        interieur = tk.Frame(pied, bg=UI["plan"])
        interieur.pack(fill="x", padx=px(22), pady=(px(12), px(10)))
        self.bouton_calculer = BoutonPlat(interieur, self.theme, "Calculer le filtre", self.calculer)
        self.bouton_calculer.pack(fill="x")
        Infobulle(self.bouton_calculer, self.theme,
                  "Lance la synthèse. Touche Entrée : même effet depuis un champ du gabarit.")
        self.etat = EtatCalcul(interieur, self.theme)        # en cours, terminé, saisie modifiée…
        self.etat.pack(fill="x", pady=(px(7), 0))

    def _construire_saisie(self, cote: tk.Frame) -> None:
        """Panneau de gauche : type de filtre, gabarit, composants, puis les options repliables."""
        px, P = self.theme.px, self.theme.polices
        self.var_auto = tk.BooleanVar(value=self.calcul_auto)
        self.champs: Dict[str, ChampUnite] = {}

        # Titre de l'application
        tk.Label(cote, text="Filtres de Butterworth", font=P["marque"], fg=UI["encre"], bg=UI["plan"],
                 anchor="w").pack(fill="x", padx=px(22), pady=(px(18), 0))

        # Type de filtre : quatre tuiles
        self._titre_types = self._section(cote, "Type de filtre", haut=14)
        grille = self.cadre_types = tk.Frame(cote, bg=UI["plan"])
        grille.pack(fill="x", padx=px(22))
        grille.columnconfigure((0, 1), weight=1, uniform="tuile")
        self.tuiles: Dict[str, TuileType] = {}
        for i, code in enumerate(("PB", "PH", "PM", "CB")):
            tuile = TuileType(grille, self.theme, code, self.choisir_type)
            Infobulle(tuile, self.theme, BULLES_TYPES[code])
            tuile.grid(row=i // 2, column=i % 2, sticky="ew",
                       padx=(0 if i % 2 == 0 else px(4), px(4) if i % 2 == 0 else 0),
                       pady=(0, px(7)))
            self.tuiles[code] = tuile

        # Gabarit : croquis redessiné pendant la saisie, puis les champs sur deux colonnes
        self._titre_gabarit = self._section(cote, "Gabarit", haut=10)
        self.croquis = CroquisGabarit(cote, self.theme)
        self.croquis.pack(fill="x", padx=px(22), pady=(0, px(4)))
        Infobulle(self.croquis, self.theme,
                  "Gabarit à l'échelle (fréquences en échelle logarithmique) : zones interdites en rose. "
                  "Le paramètre en cours de saisie est en bleu. Il se met à jour pendant la frappe.")
        self.alerte_croquis = texte_souple(tk.Label(cote, text="", font=P["petit"], fg=UI["erreur"], bg=UI["plan"],
                                                    anchor="w", justify="left", wraplength=px(292)))
        self._champ_actif: Optional[str] = None
        self._dernieres_valeurs: Dict[tuple, float] = {}     # dernière valeur lisible de chaque champ
        self.cadre_gabarit = tk.Frame(cote, bg=UI["plan"])
        self.cadre_gabarit.pack(fill="x", padx=px(22), pady=(px(8), 0))
        self.aide = texte_souple(tk.Label(cote, text=AIDE_DEFAUT, font=P["petit"], fg=UI["discret"],
                                          bg=UI["plan"], anchor="nw", justify="left", wraplength=px(292),
                                          height=2))
        self.aide.pack(fill="x", padx=px(22))

        # Messages sous le gabarit : erreur de saisie (rouge) ou remarque (orangé)
        self.message = texte_souple(tk.Label(cote, text="", font=P["petit"], anchor="nw", justify="left",
                                             wraplength=px(272), padx=px(11), pady=px(9)), marge=px(26))

        # Composants : valeur de référence et séries ; options repliables
        self.titre_reference = self._section(cote, "Composants", haut=8)
        self.cadre_reference = tk.Frame(cote, bg=UI["plan"])
        self.cadre_reference.pack(fill="x", padx=px(22))
        self.options = SectionRepliable(cote, self.theme, "Options",
                                        bool(self.preferences.get("options_ouvertes", False)),
                                        self._options_depliees)
        self.options.pack(fill="x", padx=px(22), pady=(px(12), px(18)))
        Infobulle(self.options.tete, self.theme,
                  "Options de calcul et de câblage : associations de deux valeurs, pont diviseur et ordre des "
                  "cellules du passe-bande, calcul automatique. Le nombre d'options actives s'affiche à droite.")
        self.cadre_options = self.options.contenu

    def _construire_resultats(self, droite: tk.Frame) -> None:
        """Panneau de droite : bandeau des résultats clés puis les onglets."""
        px = self.theme.px

        # Bandeau des résultats clés
        bandeau = self._cadre_bandeau = tk.Frame(droite, bg=UI["surface"])
        bandeau.pack(fill="x", padx=px(28), pady=(px(20), px(14)))
        self.f_ordre = Fait(bandeau, self.theme, "Ordre minimal", accent=True)
        self.f_k = Fait(bandeau, self.theme, "Sélectivité k")
        self.f_eps = Fait(bandeau, self.theme, "Ondulation ε")
        self.f_ref = Fait(bandeau, self.theme, "Référence")
        self.f_montage = Fait(bandeau, self.theme, "Montage")
        faits = [self.f_ordre, self.f_k, self.f_eps, self.f_ref, self.f_montage]
        for fait, cle in zip(faits, ("ordre", "k", "eps", "ref", "montage")):
            Infobulle(fait, self.theme, lambda c=cle: self._bulle_fait(c))
        self._bandeau = []          # (séparateur, fait) dans l'ordre d'affichage
        for i, fait in enumerate(faits):
            separateur = tk.Frame(bandeau, bg=UI["trait"], width=1) if i else None
            self._bandeau.append((separateur, fait))
        self._placer_bandeau(len(faits))
        bandeau.bind("<Configure>", lambda e: self._adapter_bandeau(e.width))

        # Onglets
        self.onglets = BarreOnglets(droite, self.theme, self.ONGLETS, self.choisir_onglet, BULLES_ONGLETS)
        Infobulle(self.onglets.statut, self.theme, self._bulle_statut)
        # Gabarit non respecté avec les valeurs normalisées : un clic mène à « Corriger les valeurs »
        self.onglets.statut.bind("<Button-1>", lambda _e: self._statut_clic(), add="+")
        self.onglets.pack(fill="x", padx=px(28), pady=(0, px(4)))

        pile = tk.Frame(droite, bg=UI["surface"])
        pile.pack(fill="both", expand=True, padx=px(28), pady=(px(12), px(16)))
        pile.rowconfigure(0, weight=1)
        pile.columnconfigure(0, weight=1)
        # Accueil (aucun filtre calculé) puis onglets, empilés : le premier plan est choisi
        # par choisir_onglet()
        self.accueil = Accueil(pile, self.theme, visite=self.lancer_visite, cours=self.ouvrir_guide)
        self.accueil.grid(row=0, column=0, sticky="nsew")
        self.panneaux = [PanneauBode(pile, self.theme, normalise=True, app=self),
                         PanneauBode(pile, self.theme, normalise=False, app=self),
                         PanneauEtapes(pile, self.theme, self),
                         PanneauComposants(pile, self.theme, self),
                         PanneauCablage(pile, self.theme, self)]
        for p in self.panneaux:
            p.grid(row=0, column=0, sticky="nsew")
        self.choisir_onglet(0)

    def _placer_bandeau(self, nombre: int) -> None:
        """Affiche les `nombre` premiers résultats du bandeau."""
        px = self.theme.px
        for separateur, fait in self._bandeau:
            fait.pack_forget()
            if separateur:
                separateur.pack_forget()
        for i, (separateur, fait) in enumerate(self._bandeau[:nombre]):
            if separateur:
                separateur.pack(side="left", fill="y", pady=px(4))
            fait.pack(side="left", anchor="n", padx=(0 if i == 0 else px(22), px(22)))
        self._nombre_faits = nombre

    def _adapter_bandeau(self, largeur: int) -> None:
        """Fenêtre étroite : on masque les derniers résultats (ils restent dans les onglets)."""
        px = self.theme.px
        necessaire, nombre = 0, 0
        for i, (_sep, fait) in enumerate(self._bandeau):
            necessaire += fait.winfo_reqwidth() + px(44) + 1
            if necessaire > largeur and i > 0:
                break
            nombre = i + 1
        if nombre != self._nombre_faits:
            self._placer_bandeau(nombre)

    # ------------------------------------------------------------------ saisie
    def _champ(self, parent, nom: str, ligne: int, colonne: int) -> None:
        """Un champ de saisie de la grille : nom au-dessus, valeur et unité dans le même cadre."""
        px = self.theme.px
        champ = ChampUnite(parent, self.theme, nom, UNITES.get(nom, "Hz"))
        champ.grid(row=ligne, column=colonne, sticky="ew", pady=(0, px(8)),
                   padx=(0, px(5)) if colonne == 0 else (px(5), 0))
        Infobulle(champ.nom_champ, self.theme, lambda n=nom: self._bulle_champ(n))
        entree = champ.entree
        entree.insert(0, self.valeurs[self.type_courant].get(nom, ""))
        entree.bind("<Return>", lambda _e: self.calculer(), add="+")
        entree.bind("<KP_Enter>", lambda _e: self.calculer(), add="+")
        entree.bind("<FocusIn>", lambda _e, n=nom: self._entrer_champ(n), add="+")
        entree.bind("<FocusOut>", lambda _e: self._entrer_champ(None), add="+")
        entree.bind("<KeyRelease>", self._verifier_saisie, add="+")
        self.entrees[nom] = entree
        self.champs[nom] = champ

    def _grille(self, parent) -> tk.Frame:
        """Grille de deux colonnes égales (champs, listes)."""
        grille = tk.Frame(parent, bg=UI["plan"])
        grille.pack(fill="x")
        grille.columnconfigure((0, 1), weight=1, uniform="champ")
        return grille

    def _marquer_champs(self, en_erreur: Optional[str] = None) -> None:
        """Remet les champs à l'état normal ; `en_erreur` : nom du champ à signaler."""
        for nom, champ in self.champs.items():
            if champ.winfo_exists():
                champ.marquer(nom == en_erreur)

    def _option(self, titre: str, detail: str, variable: tk.BooleanVar, commande: Callable[[], None],
                bulle) -> ttk.Checkbutton:
        """Une option : case à cocher et, dessous, une ligne d'explication discrète."""
        px, P = self.theme.px, self.theme.polices
        bloc = tk.Frame(self.cadre_options, bg=UI["plan"])
        bloc.pack(fill="x", pady=(0, px(9)))

        def basculer() -> None:
            commande()
            self._maj_resume_options()
        case = ttk.Checkbutton(bloc, text=titre, variable=variable, style="Choix.TCheckbutton", command=basculer)
        case.pack(anchor="w")
        texte_souple(tk.Label(bloc, text=detail, font=P["petit"], fg=UI["discret"], bg=UI["plan"], anchor="w",
                              justify="left")).pack(fill="x", padx=(px(20), 0))
        Infobulle(case, self.theme, bulle)
        return case

    def _options_depliees(self, ouvert: bool) -> None:
        """Options dépliées ou repliées : choix gardé pour les prochains lancements."""
        self.preferences["options_ouvertes"] = ouvert
        enregistrer_preferences(self.preferences)
        self.after_idle(self._ajuster_colonne)

    def _ajuster_colonne(self) -> None:
        """Après dépliage des options, la colonne défile pour les montrer."""
        if self.options.ouvert and self.cadre_options.winfo_children():
            self.colonne.montrer(self.cadre_options.winfo_children()[-1])

    def _maj_resume_options(self) -> None:
        """Nombre d'options actives, à droite du titre « Options » (cases cochées et utiles)."""
        if getattr(self, "options", None) is None or not self.options.winfo_exists():
            return
        cases = [getattr(self, nom, None) for nom in ("case_associations", "case_pont", "case_ph", "case_auto")]
        actives = 0
        for case in cases:
            if case is not None and case.winfo_exists() and case.instate(["selected", "!disabled"]):
                actives += 1
        self.options.resumer("aucune active" if actives == 0 else f"{actives} active" + ("s" if actives > 1 else ""))

    def _entrer_champ(self, nom: Optional[str]) -> None:
        """Champ qui reçoit (ou perd) la saisie : aide sous le gabarit et croquis mis à jour."""
        self.aide.configure(text=AIDE.get(nom, AIDE_DEFAUT) if nom else AIDE_DEFAUT)
        self._champ_actif = nom
        self._maj_croquis()

    def _maj_croquis(self) -> None:
        """Redessine le croquis du gabarit avec les valeurs saisies (la dernière valeur lisible
        de chaque champ en cours de frappe) et signale aussitôt une incohérence (fa < fp…)."""
        if not hasattr(self, "croquis") or not self.croquis.winfo_exists():
            return
        t = self.type_courant
        lues: Dict[str, Optional[float]] = {}
        for nom, entree in self.entrees.items():
            texte = entree.get()
            if not texte.strip():                     # champ vide : forme type du croquis
                lues[nom] = None
                self._dernieres_valeurs.pop((t, nom), None)
                continue
            try:
                lues[nom] = mt.lire_valeur(texte, nom)
                self._dernieres_valeurs[(t, nom)] = lues[nom]
            except mt.ErreurGabarit:
                lues[nom] = None
        connues = {}
        for nom in list(mt.FREQUENCES[t]) + ["Gp", "Ga"]:
            valeur = lues.get(nom)
            if valeur is None:                        # frappe en cours (« 2, ») : dernière valeur lisible
                valeur = self._dernieres_valeurs.get((t, nom))
            if valeur is not None:
                connues[nom] = valeur
        self.croquis.montrer(t, croquis_complet(t, connues), self._champ_actif)
        # Contrôle de cohérence dès que tout est lisible (sinon on attend la fin de la frappe)
        alerte = ""
        if lues and all(valeur is not None for valeur in lues.values()):
            try:
                mt.verifier_gabarit(mt.Gabarit(t, **lues))
            except mt.ErreurGabarit as erreur:
                alerte = "✕  " + str(erreur)
        self.alerte_croquis.configure(text=alerte)
        if alerte and not self.alerte_croquis.winfo_ismapped():
            self.alerte_croquis.pack(fill="x", padx=self.theme.px(22), pady=(0, self.theme.px(2)),
                                     after=self.croquis)
        elif not alerte and self.alerte_croquis.winfo_ismapped():
            self.alerte_croquis.pack_forget()

    def _reconstruire_champs(self) -> None:
        """Affiche les champs, les composants et les options propres au type de filtre choisi."""
        for cadre in (self.cadre_gabarit, self.cadre_reference, self.cadre_options):
            for w in cadre.winfo_children():
                w.destroy()
        self.entrees.clear()
        self.champs = {}
        for nom in ("case_pont", "case_ph", "case_associations", "choix_R", "choix_C"):
            setattr(self, nom, None)
        px, P = self.theme.px, self.theme.polices
        t = self.type_courant

        # Gabarit : fréquences dans l'ordre croissant, puis Gp et Ga, sur deux colonnes
        grille = self._grille(self.cadre_gabarit)
        for i, nom in enumerate(list(mt.FREQUENCES[t]) + ["Gp", "Ga"]):
            self._champ(grille, nom, i // 2, i % 2)

        # Composants : valeur(s) de référence, puis séries des résistances et des condensateurs
        if t == "CB":
            texte_souple(tk.Label(self.cadre_reference, text="Le coupe-bande n'est pas réalisable en "
                                                             "Sallen & Key : aucun composant à calculer.",
                                  font=P["petit"], fg=UI["discret"], bg=UI["plan"], anchor="w",
                                  justify="left", wraplength=px(292))).pack(fill="x")
        else:
            grille = self._grille(self.cadre_reference)
            references = [nom for nom, types in (("R0", ("PB", "PM")), ("C0", ("PH", "PM"))) if t in types]
            for i, nom in enumerate(references):
                self._champ(grille, nom, 0, i)
            listes = []
            for i, (titre, code, commande) in enumerate((("Résistances", self.serie_R, self.choisir_serie_R),
                                                         ("Condensateurs", self.serie_C, self.choisir_serie_C))):
                cellule = tk.Frame(grille, bg=UI["plan"])
                cellule.grid(row=1, column=i, sticky="ew", padx=(0, px(5)) if i == 0 else (px(5), 0))
                tk.Label(cellule, text=titre, font=P["petit"], fg=UI["encre2"], bg=UI["plan"],
                         anchor="w").pack(fill="x", pady=(0, px(2)))
                liste = ListeChoix(cellule, self.theme, OPTIONS_SERIES, code, commande)
                liste.pack(fill="x")
                Infobulle(liste, self.theme, BULLE_SERIES)
                listes.append(liste)
            self.choix_R, self.choix_C = listes

        # Options (repliables) : seulement celles qui ont un sens pour ce type de filtre
        if t != "CB":
            self.var_associations = tk.BooleanVar(value=self.associations)
            self.case_associations = self._option(
                "Associer deux valeurs si besoin", "Valeur à moins de 1 % avec deux composants",
                self.var_associations, self.basculer_associations,
                "Si aucune valeur de la série n'approche la valeur calculée à 1 % près, elle est réalisée avec "
                "deux composants : deux résistances en série ou deux condensateurs en parallèle (notés « a + b »). "
                "Sans effet avec des valeurs calculées.")
            self._maj_case_associations()
        if t == "PM":
            self.var_pont = tk.BooleanVar(value=self.pont)
            self.case_pont = self._option("Pont diviseur d'entrée", "Ramène le gain du passe-bande à 0 dB",
                                          self.var_pont, self.basculer_pont, self._bulle_pont)
            self._maj_case_pont()
            self.var_ph = tk.BooleanVar(value=self.ph_dabord)
            self.case_ph = self._option(
                "Commencer par la cellule passe-haut", "Chaque paire : 1 bis, puis 1", self.var_ph,
                self.basculer_ph_dabord,
                "Ordre de câblage de chaque paire : cellule passe-haut (i bis) puis passe-bas (i). La fonction "
                "de transfert ne change pas ; seuls l'ordre des étages et les niveaux internes changent.")
        self.case_auto = self._option(
            "Calcul automatique", "Recalcule pendant la frappe", self.var_auto, self.basculer_calcul_auto,
            "Le filtre est recalculé une demi-seconde après la dernière frappe, sans cliquer sur « Calculer le "
            "filtre ». Une saisie incomplète ou incorrecte est ignorée jusqu'au clic (ou à la touche Entrée), "
            "qui affiche l'erreur.")
        self._maj_resume_options()

    def _memoriser_saisies(self) -> None:
        """Garde les valeurs saisies : chaque type de filtre conserve les siennes."""
        for nom, entree in self.entrees.items():
            self.valeurs[self.type_courant][nom] = entree.get()

    def choisir_type(self, code: str, calculer: bool = True) -> None:
        """Changement de type de filtre (clic sur une tuile) : ses valeurs reviennent, et son
        filtre est calculé si son gabarit est complet (sinon, l'accueil s'affiche)."""
        if self.entrees:
            self._memoriser_saisies()
        self.type_courant = code
        for c, tuile in self.tuiles.items():
            tuile.selectionner(c == code)
        self._reconstruire_champs()
        self._champ_actif = None
        self.aide.configure(text=AIDE_DEFAUT)          # le champ qui avait la saisie n'existe plus
        self._maj_croquis()
        self._afficher_message(None)
        if calculer:
            if self._saisie_complete():
                self.calculer()
            else:
                self._vider_resultats()

    # ------------------------------------------------------------------ infobulles
    def _bulle_champ(self, nom: str) -> str:
        """Explication d'un paramètre du gabarit, selon le type de filtre."""
        return BULLES_CHAMPS.get((self.type_courant, nom), BULLES_CHAMPS.get(nom, ""))

    def _bulle_fait(self, cle: str) -> str:
        """Explication d'un résultat du bandeau, selon le type de filtre."""
        t = self.type_courant
        bande = t in ("PM", "CB")
        if cle == "ordre":
            return ("Plus petit entier n qui respecte le gabarit ; en dessous, la valeur exacte du "
                    "calcul."
                    + (" Le filtre réel est d'ordre 2n : la transposition donne deux pôles pour chaque pôle "
                       "du prototype." if bande else "")
                    + " Détail : onglet Étapes du calcul.")
        if cle == "k":
            formule = {"PB": "k = fp/fa", "PH": "k = fa/fp", "PM": "k = (fp+ − fp−)/(fa+ − fa−)",
                       "CB": "k = (fa+ − fa−)/(fp+ − fp−)"}[t]
            formule = formule.replace(" ", "\u00a0")          # formule jamais coupée en fin de ligne
            return (f"Coefficient de sélectivité : {formule}, compris entre 0 et 1. Plus k est proche de 1, "
                    "plus la transition est raide et plus l'ordre est élevé. Le gabarit réduit va de Ω = 1 "
                    "à Ω = 1/k.")
        if cle == "eps":
            return ("ε² = 10^(−Gp/10) − 1. Avec Gp = −3 dB, ε ≈ 1 : la coupure à −3 dB du prototype tombe "
                    "en Ω = 1. Sinon, elle passe en Ωc = ε^(−1/n).")
        if cle == "ref":
            if t == "PB":
                return ("Condensateur de référence : R0·C0·ωp = 1, avec ωp = 2π·fp. Les condensateurs des "
                        "cellules passe-bas valent m·C0 et q·C0.")
            if t == "PH":
                return ("Résistance de référence : R0·C0·ωp = 1, avec ωp = 2π·fp. Les résistances des "
                        "cellules passe-haut valent R0/m et R0/q.")
            return ("Fréquence centrale f0 = √(fp+·fp−) et largeur de bande relative B = (fp+ − fp−)/f0, "
                    "utilisées par la transposition de fréquence.")
        if t == "CB":
            return "Le coupe-bande n'est pas réalisable avec des cellules de Sallen & Key : il n'y a pas de montage."
        return ("Nombre d'étages du montage : une cellule de Sallen & Key à gain unité par facteur du second "
                "degré, une cellule RC ou CR pour un facteur du premier ordre, une cellule de Rauch pour le "
                "centre d'un passe-bande d'ordre impair.")

    def _correction_possible(self) -> bool:
        """Vrai si le gabarit n'est pas respecté avec les valeurs normalisées (montage réalisable)."""
        res, choix = self.resultat, self.choix_series()
        return (res is not None and choix is not None and bool(res.montages)
                and not all(p.ok for p in res.points_controle_serie(choix)))

    def _statut_clic(self) -> None:
        """Clic sur l'indicateur « Gabarit non respecté » : onglet Composants, où se trouve
        « Corriger les valeurs »."""
        if self._correction_possible():
            self.choisir_onglet(3)

    def _bulle_statut(self) -> str:
        """Ce que contrôle l'indicateur « Gabarit respecté »."""
        res = self.resultat
        if res is None:
            return ""
        texte = ("Le gain est contrôlé à chaque fréquence limite du gabarit : au moins Gp dans la bande "
                 "passante, au plus Ga dans la bande atténuée.")
        choix = self.choix_series()
        if choix is not None and res.montages:
            texte += (f" Le contrôle porte sur le montage aux valeurs normalisées ({choix.court()}), "
                      "courbe orange du Bode réel.")
            if not all(p.ok for p in res.points_controle_serie(choix)):
                texte += (" Cliquez ici pour ouvrir l'onglet Composants : « Corriger les valeurs » cherche "
                          "d'autres valeurs normalisées qui le respectent, sans changer R0 ni C0.")
        return texte + " Détail : fin de l'onglet Étapes du calcul."

    def _bulle_pont(self) -> str:
        """Effet du pont diviseur, avec le gain du montage affiché."""
        res = self.resultat
        if res is not None and res.gabarit.type == "PM" and res.attenuateur():
            gain = mt.fmt_nombre(20 * math.log10(res.gain_montage()), 3)
            return (f"Les cellules à gain unité amplifient la bande passante : le montage a un gain de {gain} dB "
                    "à f0. Le pont diviseur remplace la résistance d'entrée de la première cellule passe-bas par "
                    "deux résistances (l'une côté entrée, l'autre vers la masse) et ramène ce gain à 0 dB, sans "
                    "changer la forme de la réponse.")
        if res is not None and res.gabarit.type == "PM":
            return "Inutile ici : ce montage n'amplifie pas la bande passante (gain de 0 dB au plus à f0)."
        return ("Les cellules à gain unité du passe-bande amplifient la bande passante ; le pont diviseur "
                "d'entrée ramène le gain du montage à 0 dB.")

    def choix_series(self) -> Optional[mt.ChoixSeries]:
        """Séries choisies pour réaliser les composants (None : valeurs calculées), avec le pont
        diviseur s'il est dans le montage et les valeurs ajustées par la correction du gabarit
        (si elles correspondent aux séries, aux options et au calcul affichés)."""
        if not (self.serie_R or self.serie_C):
            return None
        pont = self.pont_actif()
        ajustements: Tuple[mt.Ajustement, ...] = ()
        if (self.ajustements and self.resultat is not None
                and self.config_ajustements == (self.serie_R, self.serie_C, self.associations, pont,
                                                mt.signature_calcul(self.resultat))
                and mt.ajustements_valides(self.resultat, self.ajustements)):
            ajustements = self.ajustements
        return mt.ChoixSeries(self.serie_R or None, self.serie_C or None, self.associations, pont, ajustements)

    # ------------------------------------------------------ correction du gabarit
    def corriger_valeurs(self) -> None:
        """« Corriger les valeurs » (onglet Composants) : cherche des valeurs normalisées qui
        respectent le gabarit, sans changer R0 ni C0 (autre valeur de la série, autre
        association, puis associations ou série plus fine si besoin), et les applique tout de
        suite ; « Annuler la correction » revient aux valeurs d'avant."""
        res, choix = self.resultat, self.choix_series()
        if res is None or choix is None or not res.montages:
            return
        bouton = self.panneaux[3].bouton_corriger
        bouton.occuper("Recherche…")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            correction = mt.corriger_gabarit(res, choix)
        finally:
            self.configure(cursor="")
            bouton.liberer()
        self.correction = correction
        if correction.trouvee:
            self._avant_correction = {"serie_R": self.serie_R, "serie_C": self.serie_C,
                                      "associations": self.associations, "ajustements": self.ajustements,
                                      "config": self.config_ajustements}
            c = correction.choix
            self.serie_R, self.serie_C = c.resistances or "", c.condensateurs or ""
            self.associations = c.associations
            self.ajustements = c.ajustements
            self.config_ajustements = (self.serie_R, self.serie_C, self.associations, c.pont,
                                       mt.signature_calcul(res))
        self._maj_choix(garder_correction=True)

    def annuler_correction(self) -> None:
        """Revient aux séries, à l'option « associations » et aux valeurs d'avant la correction
        (après une reprise de séance : aux valeurs normalisées les plus proches)."""
        avant = self._avant_correction
        if avant is not None:
            self.serie_R, self.serie_C = avant["serie_R"], avant["serie_C"]
            self.associations = avant["associations"]
            self.ajustements, self.config_ajustements = avant["ajustements"], avant["config"]
        else:
            self.ajustements, self.config_ajustements = (), None
        self.correction = None
        self._avant_correction = None
        self._maj_choix(garder_correction=True)

    def correction_affichee(self) -> Optional[mt.Correction]:
        """Dernière recherche de correction, si elle décrit encore le montage affiché :
        correction appliquée (ses valeurs sont celles du montage) ou recherche sans résultat
        (pour ces mêmes valeurs). None sinon."""
        c = self.correction
        if c is None or self.resultat is None:
            return None
        choix = self.choix_series()
        if c.trouvee:
            return c if c.choix == choix else None
        return c if c.depart == choix else None

    def choisir_serie_R(self, code: str) -> None:
        """Série des résistances : "" (calculées), "E6", "E12" ou "E24"."""
        self.serie_R = code
        self._maj_choix()

    def choisir_serie_C(self, code: str) -> None:
        """Série des condensateurs : "" (calculés), "E6", "E12" ou "E24"."""
        self.serie_C = code
        self._maj_choix()

    def basculer_associations(self) -> None:
        """Case « Associer deux valeurs » cochée ou décochée."""
        self.associations = bool(self.var_associations.get())
        self._maj_choix()

    def basculer_pont(self) -> None:
        """Case « Pont diviseur d'entrée » cochée ou décochée : étapes, composants et câblage (leurs
        repères changent) à redessiner."""
        self.pont = bool(self.var_pont.get())
        self.correction = None
        self._avant_correction = None
        if self.resultat is not None:
            for i in (1, 2, 3, 4):                        # Bode réel, étapes, composants, câblage
                self._a_jour[i] = False
            self._actualiser_onglet(self.onglets.actif)
            self._maj_statut()           # pont normalisé : il compte dans le contrôle du gabarit

    def basculer_aop(self) -> None:
        """Option « µA741 réel » (case du Bode réel ou menu Affichage) : la courbe est ajoutée
        ou retirée du Bode réel, qui est affiché ; le choix est gardé pour les prochains lancements."""
        self.aop_reel = bool(self.var_aop.get())
        self.preferences["aop_reel"] = self.aop_reel
        enregistrer_preferences(self.preferences)
        self._a_jour[1] = False
        self.choisir_onglet(1)

    def basculer_dispersion(self) -> None:
        """Option « Dispersion » du Bode réel (case ou menu) : zone des montages tirés au hasard."""
        self.dispersion = bool(self.var_dispersion.get())
        self.preferences["dispersion"] = self.dispersion
        enregistrer_preferences(self.preferences)
        self._a_jour[1] = False
        self.choisir_onglet(1)

    def basculer_ph_dabord(self) -> None:
        """Ordre des cellules du passe-bande : le résultat affiché est recalculé dans le nouvel ordre."""
        self.ph_dabord = bool(self.var_ph.get())
        self.correction = None             # repères renumérotés : le détail de la correction ne vaut plus
        res = self.resultat
        if res is not None and res.gabarit.type == "PM":
            self.resultat = mt.synthese(res.gabarit, self.ph_dabord)
            self._afficher_resultat(self.resultat)

    def _maj_case_pont(self) -> None:
        """La case n'a d'effet que si le montage amplifie (gain > 0 dB à f0) : sinon elle est grisée."""
        case = getattr(self, "case_pont", None)
        if case is None or not case.winfo_exists():
            return
        res = self.resultat
        utile = res is None or res.gabarit.type != "PM" or res.attenuateur() is not None
        case.state(["!disabled"] if utile else ["disabled"])
        self._maj_resume_options()

    def pont_actif(self) -> bool:
        """Vrai si le pont diviseur doit figurer dans le montage réel affiché."""
        res = self.resultat
        return self.pont and res is not None and res.attenuateur() is not None

    def _maj_case_associations(self) -> None:
        """La case n'a d'effet que si une série est choisie : sinon elle est grisée."""
        case = getattr(self, "case_associations", None)
        if case is not None and case.winfo_exists():
            case.state(["!disabled"] if (self.serie_R or self.serie_C) else ["disabled"])
            self._maj_resume_options()

    def _maj_choix(self, garder_correction: bool = False) -> None:
        """Nouveau choix de séries : met à jour les contrôles, les onglets concernés et l'indicateur.
        Un choix fait à la main remplace la correction : elle ne peut plus être annulée."""
        if not garder_correction:
            self.correction = None
            self._avant_correction = None
        for segments, code in ((getattr(self, "choix_R", None), self.serie_R),
                               (getattr(self, "choix_C", None), self.serie_C)):
            if segments is not None and segments.winfo_exists():
                segments.selectionner(code)
        if getattr(self, "var_associations", None) is not None:
            self.var_associations.set(self.associations)
        self._maj_case_associations()
        if self.resultat is not None:
            for i in (1, 2, 3, 4):                        # Bode réel, étapes, composants et câblage
                self._a_jour[i] = False
            self._actualiser_onglet(self.onglets.actif)
            self._maj_statut()

    def _maj_statut(self) -> None:
        """L'indicateur de gabarit décrit le montage affiché : valeurs calculées ou normalisées."""
        res, choix = self.resultat, self.choix_series()
        if res is None:
            self.onglets.afficher_statut(None)
        elif choix is not None and res.montages:
            points = res.points_controle_serie(choix)
            self.onglets.afficher_statut(all(p.ok for p in points), f"({choix.court()})")
        else:
            self.onglets.afficher_statut(res.gabarit_respecte())
        self.onglets.statut.configure(cursor="hand2" if self._correction_possible() else "")

    def _onglet_voisin(self, sens: int) -> str:
        """Ctrl+Tab / Ctrl+Maj+Tab : onglet suivant ou précédent."""
        self.choisir_onglet((self.onglets.actif + sens) % len(self.ONGLETS))
        return "break"

    def choisir_onglet(self, i: int) -> None:
        """Affiche l'onglet i (0 : Bode normalisé … 3 : composants, 4 : câblage) ; l'accueil
        reste au premier plan tant qu'aucun filtre n'est calculé."""
        self.onglets.activer(i)
        self.panneaux[i].tkraise()
        if self._accueil_actif:
            self.accueil.tkraise()
        self._actualiser_onglet(i)

    def _actualiser_onglet(self, i: int) -> None:
        """Redessine un onglet seulement quand on l'affiche : le calcul reste instantané."""
        if self.resultat is not None and not self._a_jour[i]:
            self.panneaux[i].afficher(self.resultat)
            self._a_jour[i] = True

    # ------------------------------------------------------------------ calcul
    # Durée minimale de l'état « Calcul en cours… » (ms) : le calcul est presque
    # instantané, mais l'utilisateur doit voir que son clic a été pris en compte.
    DELAI_CALCUL = 150

    def calculer(self) -> None:
        """Bouton « Calculer le filtre » (ou Entrée) : affiche « Calcul en cours… » puis calcule.

        Le calcul est lancé juste après, une fois le bouton redessiné ; un clic
        pendant ce temps est ignoré (le calcul programmé lira la saisie la plus récente).
        """
        if self._calcul_prevu is not None:
            return
        self.bouton_calculer.occuper("Calcul en cours…")
        self.etat.en_cours()
        self.configure(cursor="watch")
        self._calcul_prevu = self.after(self.DELAI_CALCUL, self._calculer_maintenant)

    def _calculer_maintenant(self) -> None:
        """Lit le gabarit, lance la synthèse (moteur.py) puis affiche les résultats."""
        self._calcul_prevu = None
        try:
            reussi = self._synthese_et_affichage()
            self.update_idletasks()              # diagrammes dessinés avant d'annoncer la fin
        finally:
            self.configure(cursor="")
            self.bouton_calculer.liberer()
        if reussi:
            self.etat.termine(f"n = {self.resultat.n}")
            self._garder_session()
        else:
            self.etat.impossible()
            self.colonne.montrer(self.message)        # le message d'erreur est rendu visible

    def _synthese_et_affichage(self) -> bool:
        """Calcul proprement dit. Renvoie False si le gabarit est incorrect."""
        self._memoriser_saisies()
        self._saisie_calculee = self._saisie_actuelle()
        self._marquer_champs(None)
        try:
            g = mt.gabarit_depuis_textes(self.type_courant, self.valeurs[self.type_courant])
            res = mt.synthese(g, self.ph_dabord)
        except mt.ErreurGabarit as erreur:
            self._afficher_message(str(erreur), erreur=True)
            if erreur.champ in self.entrees:
                self._marquer_champs(erreur.champ)
                self.entrees[erreur.champ].focus_set()
            self.onglets.afficher_statut(None)
            if self.resultat is not None and self.resultat.gabarit.type != self.type_courant:
                self.resultat = None                  # résultats d'un autre type de filtre : retirés
                self._maj_exports()
            if self.resultat is None:
                self._vider_bandeau()
                self._montrer_accueil(True)
            else:
                for fait in (self.f_ordre, self.f_k, self.f_eps, self.f_ref, self.f_montage):
                    fait.perime()
            return False
        if self.resultat is None or self.resultat.gabarit != res.gabarit:
            self.correction = None              # autre calcul : la correction n'est plus annulable
            self._avant_correction = None
        self.resultat = res
        self._afficher_resultat(res)
        return True

    def _saisie_actuelle(self) -> tuple:
        """Type de filtre et textes saisis, pour savoir si la saisie a changé depuis le calcul."""
        return self.type_courant, {nom: entree.get() for nom, entree in self.entrees.items()}

    def _verifier_saisie(self, _event=None) -> None:
        """Après chaque frappe : croquis du gabarit redessiné ; prévient si les résultats ne
        correspondent plus à la saisie (et, en calcul automatique, programme le recalcul)."""
        self._maj_croquis()
        if self._calcul_prevu is not None:
            return
        if self._saisie_calculee is None:             # rien de calculé pour ce filtre
            if self.calcul_auto:
                self._programmer_calcul_auto()
            return
        if self._saisie_actuelle() != self._saisie_calculee:
            self.etat.modifie()
            if self.calcul_auto:
                self._programmer_calcul_auto()
        else:
            self.etat.retablir()

    # Pause de frappe avant le calcul automatique (ms)
    DELAI_AUTO = 500                    # ms : « une demi-seconde après la dernière frappe »

    def basculer_calcul_auto(self) -> None:
        """Case « Calcul automatique » : option gardée pour les prochains lancements."""
        self.calcul_auto = bool(self.var_auto.get())
        self.preferences["calcul_auto"] = self.calcul_auto
        enregistrer_preferences(self.preferences)
        if self.calcul_auto and self.entrees and self._saisie_actuelle() != self._saisie_calculee:
            self._programmer_calcul_auto()

    def _programmer_calcul_auto(self) -> None:
        if self._auto_prevu is not None:
            self.after_cancel(self._auto_prevu)
        self._auto_prevu = self.after(self.DELAI_AUTO, self._calcul_auto)

    def _calcul_auto(self) -> None:
        """Recalcul discret : seulement si la saisie est complète et correcte (sinon, rien ne
        change jusqu'au clic sur « Calculer le filtre », qui montre l'erreur)."""
        self._auto_prevu = None
        if (not self.calcul_auto or self._calcul_prevu is not None or not self.entrees
                or self._saisie_actuelle() == self._saisie_calculee):
            return
        textes = {nom: entree.get() for nom, entree in self.entrees.items()}
        if not self._saisie_complete():               # champs encore vides : la saisie continue
            return
        try:
            mt.synthese(mt.gabarit_depuis_textes(self.type_courant, textes), self.ph_dabord)
        except mt.ErreurGabarit:
            self.etat.a_completer()
            return
        if self._synthese_et_affichage():
            self.etat.termine(f"n = {self.resultat.n}")
            self._garder_session()

    def _afficher_resultat(self, res: mt.Resultat) -> None:
        """Met à jour le bandeau, l'indicateur « gabarit respecté » et l'onglet visible."""
        g, nm = res.gabarit, res.norm
        bande = g.type in ("PM", "CB")

        self.f_ordre.maj(str(res.n), f"n ≥ {mt.fmt_nombre(res.n_exact)}"
                         + (f", ordre réel {2 * res.n}" if bande else ""))
        self.f_k.maj(mt.fmt_nombre(nm.k), f"1/k = {mt.fmt_nombre(1 / nm.k)}")
        if res.eps_convention:
            self.f_eps.maj("1", "Gp = −3 dB")
        else:
            self.f_eps.maj(mt.fmt_nombre(res.eps), f"Ωc = {mt.fmt_nombre(res.omega_c)}")
        if g.type == "PB":
            self.f_ref.maj(mt.fmt_si(res.ref_pb[1], "F"), "R0·C0·ωp = 1", titre="Condensateur C0")
        elif g.type == "PH":
            self.f_ref.maj(mt.fmt_si(res.ref_ph[0], "Ω"), "R0·C0·ωp = 1", titre="Résistance R0")
        else:
            self.f_ref.maj(mt.fmt_si(nm.f_ref, "Hz"), f"B = {mt.fmt_nombre(nm.B)}",
                           titre="Fréquence centrale f0")
        nb = len(res.montages)
        self.f_montage.maj(f"{nb} cellule{'s' if nb > 1 else ''}" if nb else "—",
                           res.description_montage())

        self._maj_statut()
        self._maj_case_pont()
        self._maj_exports()
        cours = getattr(self, "_guide", None)
        if cours is not None and cours.winfo_exists():
            cours.actualiser()
        self._placer_bandeau(len(self._bandeau))
        self.after_idle(lambda: self._adapter_bandeau(self._cadre_bandeau.winfo_width()))
        self._a_jour = [False] * len(self.panneaux)
        self._actualiser_onglet(self.onglets.actif)
        self._montrer_accueil(False)

        if res.avertissements:
            self._afficher_message("\n".join(res.avertissements))
        else:
            self._afficher_message(None)

    # ------------------------------------------------------- aucun résultat
    def _saisie_complete(self) -> bool:
        """Vrai si tous les champs du filtre choisi sont remplis. Le calcul est alors lancé de
        lui-même (au lancement, au changement de type…) ; sinon on attend la saisie, sans
        signaler d'erreur pour des champs encore vides."""
        textes = ({nom: entree.get() for nom, entree in self.entrees.items()} if self.entrees
                  else self.valeurs[self.type_courant])
        return all(textes.get(nom, "").strip() for nom in champs_du_type(self.type_courant))

    def _montrer_accueil(self, visible: bool) -> None:
        """Accueil (aucun filtre calculé) au premier plan, ou onglet choisi."""
        self._accueil_actif = visible
        if visible:
            self.accueil.tkraise()
        else:
            self.panneaux[self.onglets.actif].tkraise()

    def _vider_bandeau(self) -> None:
        """Bandeau sans résultat : tirets, et titre de la référence selon le type de filtre."""
        titre_ref = {"PB": "Condensateur C0", "PH": "Résistance R0"}.get(self.type_courant,
                                                                          "Fréquence centrale f0")
        for fait in (self.f_ordre, self.f_k, self.f_eps, self.f_montage):
            fait.vider()
        self.f_ref.vider(titre_ref)
        self._placer_bandeau(len(self._bandeau))       # largeurs changées : bandeau réadapté
        self.after_idle(lambda: self._adapter_bandeau(self._cadre_bandeau.winfo_width()))

    def _vider_resultats(self) -> None:
        """Aucun résultat pour le filtre choisi (filtre neuf, gabarit incomplet) : bandeau en
        attente, accueil à la place des onglets, exports grisés."""
        self.resultat = None
        self._saisie_calculee = None
        self._a_jour = [False] * len(self.panneaux)
        self._vider_bandeau()
        self.onglets.afficher_statut(None)
        self.etat.vider()
        self._maj_exports()
        self._maj_case_pont()
        self._montrer_accueil(True)

    def _maj_exports(self) -> None:
        """Exports du menu Fichier (compte rendu, rapport, images) : seulement avec un résultat."""
        menu = getattr(self, "menu_fichier", None)
        if menu is not None:
            for index in self._exports:
                menu.entryconfigure(index, state="normal" if self.resultat is not None else "disabled")

    def _afficher_message(self, texte: Optional[str], erreur: bool = False) -> None:
        """Erreur (rouge) ou remarque sur le gabarit (orangé) sous le bouton Calculer."""
        px = self.theme.px
        if not texte:
            self.message.pack_forget()
            return
        self.message.configure(text=("✕  " if erreur else "⚠  ") + texte,
                               fg=UI["erreur"] if erreur else UI["alerte"],
                               bg=UI["erreur_doux"] if erreur else UI["alerte_doux"])
        self.message.pack(fill="x", padx=px(22), pady=(px(6), px(2)), after=self.aide)

    # ------------------------------------------------------------- export
    def _resultat_requis(self, action: str) -> bool:
        """Vrai si un filtre est calculé ; sinon, la ligne d'état dit brièvement quoi faire."""
        if self.resultat is not None:
            return True
        self.etat.annoncer(f"{action} : calculez d'abord le filtre.", succes=False)
        return False

    def _enregistrer_bode(self, i: int) -> None:
        """Enregistre l'image d'un onglet : Bode (0, 1) ou schéma de câblage (4)."""
        if not self._resultat_requis("Image"):
            return
        self._actualiser_onglet(i)
        self.panneaux[i].enregistrer()

    def texte_rapport(self) -> str:
        """Rapport texte complet : les étapes du calcul rédigées comme dans l'onglet (formule,
        application numérique, résultat), puis le montage réel et sa nomenclature."""
        res, choix, pont = self.resultat, self.choix_series(), self.pont_actif()
        titre = f"Synthèse d'un filtre de Butterworth ({mt.NOMS_TYPES[res.gabarit.type].lower()})"
        montage = mt.lignes_montage_reel(res, choix, pont)
        return (titre + "\n" + "=" * len(titre) + "\n\n" + gr.texte_etapes(gr.etapes_du_calcul(res, choix, pont))
                + ("\n\n" + "\n".join(montage) if montage else "") + "\n")

    def enregistrer_rapport(self) -> None:
        """Enregistre le rapport texte complet (étapes 1 à 6 de la synthèse, montage réel)."""
        if not self._resultat_requis("Rapport"):
            return
        chemin = self.demander_enregistrement("Enregistrer le rapport texte", f"{self.nom_base()}_rapport.txt",
                                              ".txt", [("Texte", "*.txt")])
        if chemin:
            with open(chemin, "w", encoding="utf-8") as fichier:
                fichier.write(self.texte_rapport())
            self.etat.annoncer(f"Rapport enregistré : {os.path.basename(chemin)}")

    def exporter_netlist(self, simulateur: str) -> None:
        """Fichier > Exporter la netlist LTspice / PSpice : le montage réel affiché (mêmes repères et
        valeurs, pont diviseur, suiveurs), prêt à simuler. Pour PSpice, prévient si le montage
        dépasse les 64 nœuds de la version étudiante."""
        import netlist                          # chargé à la demande : seulement pour ce menu
        nom = netlist.SIMULATEURS[simulateur]
        if not self._resultat_requis("Netlist"):
            return
        if not self.resultat.montages:
            self.etat.annoncer("Netlist : le coupe-bande n'est pas réalisable en Sallen & Key.", succes=False)
            return
        chemin = self.demander_enregistrement(f"Exporter la netlist {nom}", f"{self.nom_base()}_{simulateur}.cir",
                                              ".cir", [("Netlist SPICE", "*.cir"), ("Tous les fichiers", "*.*")])
        if not chemin:
            return
        texte, noeuds = netlist.netlist(self.resultat, self.choix_series(), self.pont_actif(), simulateur,
                                        fichier=os.path.basename(self.fichier) if self.fichier else "",
                                        version=VERSION)
        try:
            with open(chemin, "w", encoding="ascii", errors="replace") as fichier:
                fichier.write(texte)
        except OSError as erreur:
            messagebox.showerror(f"Netlist {nom}", f"Le fichier n'a pas pu être enregistré :\n{erreur}",
                                 parent=self)
            return
        if simulateur == "pspice" and noeuds > netlist.LIMITE_NOEUDS_PSPICE:
            self._demander(f"Netlist {nom}", "Netlist enregistrée, mais trop grande pour la version étudiante",
                           netlist.resume(self.resultat, noeuds, simulateur), [("ok", "Compris")])
        self.etat.annoncer(f"Netlist {nom} enregistrée : {os.path.basename(chemin)} ({noeuds} nœuds)")

    def enregistrer_compte_rendu(self) -> None:
        """Fichier > Compte rendu PDF : gabarit et résultats, diagrammes de Bode, étapes du calcul,
        schémas des cellules et schéma de câblage, en pages A4 ; le PDF s'ouvre ensuite."""
        if not self._resultat_requis("Compte rendu"):
            return
        chemin = self.demander_enregistrement("Enregistrer le compte rendu", f"{self.nom_base()}_compte_rendu.pdf",
                                              ".pdf", [("Document PDF", "*.pdf")])
        if not chemin:
            return
        import compte_rendu                     # chargé à la demande : seulement pour ce menu
        self.etat.occupe("Création du compte rendu PDF…")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            compte_rendu.creer_compte_rendu(
                chemin, self.resultat, self.choix_series(), pont=self.pont_actif(), aop=self.aop_reel,
                dispersion=self.dispersion, fichier=os.path.basename(self.fichier) if self.fichier else "",
                version=VERSION)
        except OSError as erreur:
            self.etat.retablir()
            messagebox.showerror("Compte rendu PDF", f"Le fichier n'a pas pu être enregistré (est-il ouvert "
                                                     f"dans un autre programme ?) :\n{erreur}", parent=self)
            return
        finally:
            self.configure(cursor="")
        self.etat.annoncer(f"Compte rendu enregistré : {os.path.basename(chemin)}")
        ouvrir_document(chemin)

    # ------------------------------------------------------------------ aide
    def _fenetre_aide(self, cle: str, titre: str, remplir: Callable[[tk.Text], None],
                      taille: Tuple[int, int] = (720, 640)) -> None:
        """Fenêtre d'aide (une seule par sujet) : texte défilant et bouton Fermer."""
        fenetres = self.__dict__.setdefault("_fenetres_aide", {})
        ancienne = fenetres.get(cle)
        if ancienne is not None and ancienne.winfo_exists():
            ancienne.deiconify()
            ancienne.lift()
            ancienne.focus_set()
            return
        px, P = self.theme.px, self.theme.polices
        fenetre = tk.Toplevel(self, bg=UI["surface"])
        fenetre.title(titre)
        fenetre.transient(self)
        fenetres[cle] = fenetre
        largeur = min(px(taille[0]), self.winfo_screenwidth() - px(40))
        hauteur = min(px(taille[1]), self.winfo_screenheight() - px(80))
        fenetre.geometry(f"{largeur}x{hauteur}+{self.winfo_rootx() + px(60)}+{self.winfo_rooty() + px(40)}")
        pied = tk.Frame(fenetre, bg=UI["surface"])
        pied.pack(side="bottom", fill="x", padx=px(24), pady=(px(6), px(16)))
        BoutonPlat(pied, self.theme, "Fermer", fenetre.destroy).pack(side="right", ipadx=px(18))
        cadre = tk.Frame(fenetre, bg=UI["surface"])
        cadre.pack(fill="both", expand=True, padx=(px(24), px(10)), pady=(px(18), 0))
        texte = tk.Text(cadre, bg=UI["surface"], fg=UI["encre"], relief="flat", bd=0, highlightthickness=0,
                        wrap="word", cursor="arrow", width=1, height=1, font=P["texte"], padx=0, pady=0)
        defil = ttk.Scrollbar(cadre, orient="vertical", command=texte.yview)
        texte.configure(yscrollcommand=barre_automatique(defil, side="right", fill="y", before=texte))
        texte.pack(side="left", fill="both", expand=True)
        texte.tag_configure("titre", font=P["marque"], foreground=UI["encre"], spacing3=px(6))
        texte.tag_configure("section", font=P["titre_bloc"], foreground=UI["accent"], spacing1=px(18),
                            spacing3=px(6))
        texte.tag_configure("texte", font=P["texte"], foreground=UI["encre2"], spacing1=px(2), spacing3=px(4))
        texte.tag_configure("puce", font=P["texte"], foreground=UI["encre"], lmargin1=px(4), lmargin2=px(22),
                            spacing1=px(3), spacing3=px(5))
        texte.tag_configure("petit", font=P["petit"], foreground=UI["discret"], spacing1=px(2), spacing3=px(2))
        texte.tag_configure("touche", font=P["champ"], foreground=UI["encre"], lmargin1=px(4), lmargin2=px(200),
                            tabs=(px(200),), spacing1=px(4), spacing3=px(4))
        texte.tag_configure("action", font=P["texte"], foreground=UI["encre2"])     # après « touche » : prioritaire
        remplir(texte)
        texte.configure(state="disabled")
        fenetre.bind("<Escape>", lambda _e: fenetre.destroy())
        fenetre.focus_set()

    def ouvrir_guide(self, chapitre: Optional[int] = None) -> None:
        """Aide > Comprendre Sallen & Key (F2) : une seule fenêtre, ramenée au premier plan ;
        `chapitre` (0 à 9) l'ouvre directement au bon endroit."""
        fenetre = getattr(self, "_guide", None)
        if fenetre is not None and fenetre.winfo_exists():
            fenetre.deiconify()
            fenetre.lift()
            fenetre.focus_set()
            if chapitre is not None:
                fenetre.afficher(chapitre)
            return
        self._guide = FenetreGuide(self, chapitre or 0)

    def mode_emploi(self) -> None:
        """Aide > Mode d'emploi : parties « Utilisation » et « Conventions de calcul » du LISEZMOI."""
        def remplir(t: tk.Text) -> None:
            t.insert("end", "Mode d'emploi\n", "titre")
            t.insert("end", insecable(f"Filtres de Butterworth {VERSION} · synthèse et cellules de Sallen & Key à "
                                      "gain unité. Laissez la souris un instant sur un élément de la fenêtre "
                                      "pour afficher son explication.") + "\n", "texte")
            sections = lire_lisezmoi(("4.", "5."))
            if not sections:
                t.insert("end", "\nLe fichier LISEZMOI.txt est introuvable : il accompagne normalement le "
                                "programme.\n", "texte")
            for titre, paragraphes in sections:
                t.insert("end", titre + "\n", "section")
                for paragraphe in paragraphes:
                    if paragraphe.startswith("- "):
                        t.insert("end", "•  " + insecable(paragraphe[2:]) + "\n", "puce")
                    else:
                        t.insert("end", insecable(paragraphe) + "\n", "texte")
        self._fenetre_aide("emploi", "Mode d'emploi – Filtres de Butterworth", remplir, (760, 680))

    RACCOURCIS = [
        ("Entrée", "calculer le filtre (depuis un champ du gabarit)"),
        ("Ctrl+N", "nouveau filtre (gabarit vide)"),
        ("Ctrl+O", "ouvrir un filtre (.filtre)"),
        ("Ctrl+S", "enregistrer le filtre"),
        ("Ctrl+Maj+S", "enregistrer le filtre sous un autre nom"),
        ("Ctrl+P", "compte rendu PDF"),
        ("Ctrl+1 à Ctrl+5", "afficher un onglet"),
        ("Ctrl+Tab", "onglet suivant (Ctrl+Maj+Tab : précédent)"),
        ("Ctrl++  /  Ctrl+−", "agrandir / réduire le texte"),
        ("Ctrl+0", "taille de texte normale"),
        ("Entrée (champ f =)", "lire le gain et la phase en ce point du diagramme de Bode"),
        ("Échap (champ f =)", "effacer le repère"),
        ("F1", "mode d'emploi"),
        ("F2", "comprendre Sallen & Key : petit cours en dix chapitres"),
        ("Ctrl+Q", "quitter, après confirmation (la saisie est gardée pour la prochaine fois)"),
    ]

    def raccourcis(self) -> None:
        """Aide > Raccourcis clavier."""
        def remplir(t: tk.Text) -> None:
            t.insert("end", "Raccourcis clavier\n", "titre")
            for touches, action in self.RACCOURCIS:
                t.insert("end", touches + "\t", "touche")
                t.insert("end", action + "\n", ("touche", "action"))
            t.insert("end", "\nSous macOS, Ctrl correspond à la touche Contrôle (et non Commande).\n", "petit")
        self._fenetre_aide("raccourcis", "Raccourcis clavier", remplir, (620, 560))

    def nouveautes(self) -> None:
        """Aide > Nouveautés : partie 6 du LISEZMOI, ce qui a changé dans cette version. La fenêtre
        s'ouvre aussi d'elle-même, une fois, au premier lancement qui suit une mise à jour."""
        def remplir(t: tk.Text) -> None:
            t.tag_configure("nom", font=self.theme.polices["champ"], foreground=UI["encre"])
            sections = lire_lisezmoi(("6.",))
            t.insert("end", (sections[0][0] if sections else f"Nouveautés de la version {VERSION}") + "\n",
                     "titre")
            if not sections:
                t.insert("end", "Le fichier LISEZMOI.txt est introuvable : il accompagne normalement le "
                                "programme.\n", "texte")
            for _titre, paragraphes in sections:
                for paragraphe in paragraphes:
                    if not paragraphe.startswith("- "):
                        t.insert("end", insecable(paragraphe) + "\n", "texte")
                        continue
                    nom, deux_points, suite = paragraphe[2:].partition(" : ")
                    t.insert("end", "•  ", "puce")
                    if deux_points and len(nom) <= 60:              # « Nom : description »
                        t.insert("end", insecable(nom), ("puce", "nom"))
                        t.insert("end", insecable(" : " + suite) + "\n", "puce")
                    else:
                        t.insert("end", insecable(paragraphe[2:]) + "\n", "puce")
            t.insert("end", "\nLe mode d'emploi (F1) détaille chaque fonction ; la visite guidée (menu Aide) "
                            "présente la fenêtre.\n", "petit")
        self._fenetre_aide("nouveautes", f"Nouveautés – Filtres de Butterworth {VERSION}", remplir, (720, 640))

    def a_propos(self) -> None:
        """Aide > À propos : version du programme et des bibliothèques, fichiers utiles."""
        def remplir(t: tk.Text) -> None:
            t.insert("end", "Filtres de Butterworth\n", "titre")
            t.insert("end", f"Version {VERSION}\n", "section")
            t.insert("end", "Synthèse de filtres de Butterworth (passe-bas, passe-haut, passe-bande, coupe-bande) "
                            "et calcul des cellules de Sallen & Key à gain unité.\n", "texte")
            t.insert("end", f"Logiciel libre, sous licence MIT. Code source : {DEPOT}\n", "texte")
            t.insert("end", "Bibliothèques\n", "section")
            t.insert("end", f"Python {sys.version.split()[0]} · Tk {self.tk.call('info', 'patchlevel')} · "
                            f"numpy {np.__version__} · matplotlib {matplotlib.__version__}\n", "texte")
            t.insert("end", "Fichiers utiles\n", "section")
            t.insert("end", "Préférences et dernière saisie :\n", "petit")
            t.insert("end", fichier_preferences() + "\n", "texte")
            t.insert("end", "Journal des erreurs (programme installé) :\n", "petit")
            t.insert("end", os.path.join(tempfile.gettempdir(), "FiltresButterworth.log") + "\n", "texte")
        self._fenetre_aide("a_propos", "À propos", remplir, (620, 460))

    # ------------------------------------------------------------ visite guidée
    def zone_visite(self, zone: str) -> List[tk.Widget]:
        """Widgets éclairés par une étape de la visite guidée (aucun pour un menu)."""
        zones = {"types": [self._titre_types, self.cadre_types],
                 "gabarit": [self._titre_gabarit, self.croquis, self.cadre_gabarit, self.aide],
                 "composants": [self.titre_reference, self.cadre_reference, self.options],
                 "calcul": [self.pied],
                 "bandeau": [self._cadre_bandeau],
                 "onglets": [self.onglets]}
        return [w for w in zones.get(zone, []) if w.winfo_exists()]

    def lancer_visite(self, etape: int = 0) -> None:
        """Aide > Visite guidée (proposée d'elle-même au premier lancement)."""
        if self.visite is not None and self.visite.active:
            return
        self.visite = VisiteGuidee(self, etape)

    def fin_visite(self) -> None:
        """Après la visite : colonne de saisie en haut, curseur dans le premier champ du gabarit."""
        self.visite = None
        self.colonne.canvas.yview_moveto(0)
        if self.entrees:
            next(iter(self.entrees.values())).focus_set()

    def _visite_premier_lancement(self, essais: int = 0) -> None:
        """Premier lancement : la visite démarre une fois la fenêtre affichée, et une seule fois."""
        if not self.winfo_viewable() and essais < 20:
            self.after(300, lambda: self._visite_premier_lancement(essais + 1))
            return
        self.preferences["visite_vue"] = True
        self.preferences["version"] = VERSION         # tout est nouveau : rien à annoncer ensuite
        enregistrer_preferences(self.preferences)
        self.lancer_visite()

    def _nouveautes_mise_a_jour(self, essais: int = 0) -> None:
        """Premier lancement d'une nouvelle version : ses nouveautés, une fois la fenêtre affichée."""
        if not self.winfo_viewable() and essais < 20:
            self.after(300, lambda: self._nouveautes_mise_a_jour(essais + 1))
            return
        self.preferences["version"] = VERSION
        enregistrer_preferences(self.preferences)
        self.nouveautes()

    # ------------------------------------------------------- fichiers et dossiers
    def _dossier(self) -> str:
        """Dossier proposé par les boîtes d'enregistrement : le dernier utilisé, sinon Documents."""
        dossier = self.preferences.get("dossier")
        if isinstance(dossier, str) and os.path.isdir(dossier):
            return dossier
        documents = os.path.join(os.path.expanduser("~"), "Documents")
        return documents if os.path.isdir(documents) else os.path.expanduser("~")

    def _retenir_dossier(self, chemin: str) -> None:
        self.preferences["dossier"] = os.path.dirname(os.path.abspath(chemin))
        enregistrer_preferences(self.preferences)

    def demander_enregistrement(self, titre: str, nom: str, extension: str, types: List[tuple]) -> str:
        """Boîte « Enregistrer sous » ouverte dans le dernier dossier utilisé."""
        chemin = filedialog.asksaveasfilename(parent=self, title=titre, initialdir=self._dossier(),
                                              initialfile=nom, defaultextension=extension, filetypes=types)
        if chemin:
            self._retenir_dossier(chemin)
        return chemin or ""

    def nom_base(self) -> str:
        """Début des noms de fichiers proposés : nom du filtre ouvert, sinon type de filtre."""
        if self.fichier:
            return os.path.splitext(os.path.basename(self.fichier))[0]
        return {"PB": "passe_bas", "PH": "passe_haut", "PM": "passe_bande", "CB": "coupe_bande"}[self.type_courant]

    # ------------------------------------------------------ travail en cours
    TYPES_FICHIER = [("Filtre de Butterworth", "*.filtre"), ("Tous les fichiers", "*.*")]

    def _etat_travail(self) -> dict:
        """Saisie et options du moment (session gardée et fichiers .filtre)."""
        if self.entrees:
            self._memoriser_saisies()
        return {"type": self.type_courant, "valeurs": {t: dict(v) for t, v in self.valeurs.items()},
                "serie_R": self.serie_R, "serie_C": self.serie_C, "associations": self.associations,
                "pont": self.pont, "ph_dabord": self.ph_dabord,
                "ajustements": [[a.cellule, a.cle, a.calculee, list(a.elements)] for a in self.ajustements],
                "config_ajustements": list(self.config_ajustements) if self.config_ajustements else None}

    def _appliquer_etat(self, etat: dict) -> bool:
        """Reprend une saisie enregistrée (valeurs vérifiées une à une). Renvoie False si
        le contenu n'est pas reconnu."""
        if not isinstance(etat, dict) or etat.get("type") not in mt.NOMS_TYPES:
            return False
        valeurs = etat.get("valeurs")
        if isinstance(valeurs, dict):
            for t, champs in valeurs.items():
                if t in self.valeurs and isinstance(champs, dict):
                    connus = set(mt.FREQUENCES[t]) | {"Gp", "Ga", "R0", "C0"}
                    self.valeurs[t].update({c: v for c, v in champs.items() if c in connus and isinstance(v, str)})
        for cle in ("serie_R", "serie_C"):
            if etat.get(cle) in ("", "E6", "E12", "E24"):
                setattr(self, cle, etat[cle])
        for cle in ("associations", "pont", "ph_dabord"):
            if isinstance(etat.get(cle), bool):
                setattr(self, cle, etat[cle])
        self.ajustements, self.config_ajustements = lire_ajustements(etat.get("ajustements"),
                                                                     etat.get("config_ajustements"))
        self.correction = None
        self._avant_correction = None
        self.type_courant = etat["type"]
        return True

    def _garder_session(self) -> None:
        """La saisie est gardée : le programme reprend là où on l'a laissé au prochain lancement."""
        session = self._etat_travail()
        session["onglet"] = self.onglets.actif
        session["fichier"] = self.fichier or ""
        session["enregistre"] = self._enregistre if self.fichier else None
        session["format"] = self.FORMAT_SESSION
        self.preferences["session"] = session
        enregistrer_preferences(self.preferences)

    # ------------------------------------------------------- travail enregistré ?
    def _contenu_filtre(self) -> dict:
        """Ce que « Enregistrer le filtre » écrit : type, gabarit de ce type, séries et options."""
        etat = self._etat_travail()
        t = etat["type"]
        return {"type": t,
                "gabarit": {nom: etat["valeurs"][t].get(nom, "").strip() for nom in champs_du_type(t)},
                "series": {"resistances": etat["serie_R"], "condensateurs": etat["serie_C"],
                           "associations": etat["associations"], "ajustements": etat["ajustements"],
                           "config_ajustements": etat["config_ajustements"]},
                "options": {"pont": etat["pont"], "ph_dabord": etat["ph_dabord"]}}

    def travail_non_enregistre(self) -> bool:
        """Vrai si le filtre affiché diffère de son fichier .filtre, ou s'il n'a jamais été
        enregistré alors qu'un gabarit a été saisi."""
        contenu = self._contenu_filtre()
        if self.fichier and self._enregistre is not None:
            return contenu != self._enregistre
        return any(valeur and valeur != REFERENCES_DEPART.get(nom, "")
                   for nom, valeur in contenu["gabarit"].items())

    def _demander(self, titre: str, question: str, explication: str, boutons: List[Tuple[str, str]]) -> str:
        """Pose une question (fenêtre modale) et renvoie la clé du bouton choisi."""
        if self.visite is not None and self.visite.active:
            self.visite.terminer()
        if self.state() == "iconic":                   # fenêtre réduite : la question doit se voir
            self.deiconify()
        self._dialogue = Dialogue(self, self.theme, titre, question, explication, boutons)
        try:
            return self._dialogue.attendre()
        finally:
            self._dialogue = None

    def _confirmer_abandon(self, action: str) -> bool:
        """Avant de quitter, de commencer un nouveau filtre ou d'en ouvrir un autre : propose
        d'enregistrer un filtre qui ne l'est pas ; pour quitter, demande toujours confirmation.
        Renvoie True si l'action peut continuer."""
        if self._dialogue is not None:                 # une question est déjà posée
            return False
        if self.travail_non_enregistre():
            question = {"quitter": "Enregistrer le filtre avant de quitter ?",
                        "nouveau": "Enregistrer le filtre avant d'en commencer un nouveau ?",
                        "ouvrir": "Enregistrer le filtre avant d'en ouvrir un autre ?"}[action]
            if self.fichier and self._enregistre is not None:
                explication = f"« {os.path.basename(self.fichier)} » a été modifié depuis son dernier enregistrement."
            else:
                explication = "Ce filtre n'a pas encore été enregistré."
            explication += (" Sans enregistrement, seule la dernière saisie sera reprise au prochain lancement."
                            if action == "quitter" else " Sans enregistrement, la saisie actuelle sera perdue.")
            reponse = self._demander("Filtre non enregistré", question, explication,
                                     [("enregistrer", "Enregistrer"), ("abandonner", "Ne pas enregistrer"),
                                      ("annuler", "Annuler")])
            if reponse == "enregistrer":
                return self.enregistrer_filtre()        # boîte « Enregistrer sous » annulée : on reste
            return reponse == "abandonner"
        if action == "quitter":
            return self._demander("Quitter", "Quitter Filtres de Butterworth ?",
                                  "Votre saisie sera reprise au prochain lancement.",
                                  [("quitter", "Quitter"), ("annuler", "Annuler")]) == "quitter"
        return True

    # Format 2 : filtre neuf au gabarit vide. Les séances plus anciennes partaient de gabarits
    # préremplis : ces valeurs, laissées telles quelles, ne sont pas reprises.
    FORMAT_SESSION = 2

    def _sans_exemples(self, session: dict) -> dict:
        """Séance d'une version précédente : les types de filtre dont les champs sont encore
        exactement les gabarits préremplis repartent d'un gabarit vide."""
        if session.get("format") == self.FORMAT_SESSION or not isinstance(session.get("valeurs"), dict):
            return session
        valeurs = {t: champs for t, champs in session["valeurs"].items()
                   if not (isinstance(champs, dict) and t in mt.EXEMPLES
                           and all(champs.get(nom) == texte for nom, texte in mt.EXEMPLES[t].items()))}
        return dict(session, valeurs=valeurs)

    def _maj_titre(self) -> None:
        titre = "Synthèse de filtres de Butterworth – Sallen & Key"
        self.title(f"{os.path.basename(self.fichier)} – {titre}" if self.fichier else titre)

    def _reprendre(self, onglet: int = 0) -> None:
        """Affiche la saisie reprise (type, champs, séries, options) et relance le calcul si
        le gabarit est complet."""
        self._a_jour = [False] * len(self.ONGLETS)
        self.choisir_type(self.type_courant, calculer=False)
        self._maj_choix()
        self.choisir_onglet(onglet)
        self._maj_titre()
        if self._saisie_complete():
            self.calculer()
        else:
            self._vider_resultats()

    def nouveau(self, demander: bool = True) -> None:
        """Fichier > Nouveau filtre : gabarit vide pour le type de filtre choisi et les autres
        (R0 et C0 proposés), options par défaut, aucun résultat. Un filtre non enregistré peut
        d'abord être enregistré."""
        if demander and not self._confirmer_abandon("nouveau"):
            return
        self.valeurs = valeurs_de_depart()
        self.serie_R = self.serie_C = ""
        self.associations = self.pont = self.ph_dabord = False
        self.ajustements, self.config_ajustements = (), None
        self.fichier = None
        self._enregistre = None
        self.entrees = {}
        self._dernieres_valeurs.clear()
        for panneau in self.panneaux[:2]:
            panneau.oublier_repere()
        self._reprendre(0)

    def ouvrir_filtre(self, chemin: Optional[str] = None) -> None:
        """Fichier > Ouvrir : reprend un filtre enregistré (.filtre). Depuis le menu, un filtre
        non enregistré peut d'abord être enregistré."""
        if chemin is None:
            if not self._confirmer_abandon("ouvrir"):
                return
            chemin = filedialog.askopenfilename(parent=self, title="Ouvrir un filtre", initialdir=self._dossier(),
                                                filetypes=self.TYPES_FICHIER)
            if not chemin:
                return
        try:
            with open(chemin, encoding="utf-8") as fichier:
                donnees = json.load(fichier)
            etat = {"type": donnees.get("type"), "valeurs": {donnees.get("type"): donnees.get("gabarit", {})},
                    "serie_R": donnees.get("series", {}).get("resistances", ""),
                    "serie_C": donnees.get("series", {}).get("condensateurs", ""),
                    "associations": donnees.get("series", {}).get("associations", False),
                    "ajustements": donnees.get("series", {}).get("ajustements", []),
                    "config_ajustements": donnees.get("series", {}).get("config_ajustements"),
                    "pont": donnees.get("options", {}).get("pont", False),
                    "ph_dabord": donnees.get("options", {}).get("ph_dabord", False)}
        except (OSError, ValueError, AttributeError) as erreur:
            messagebox.showerror("Ouvrir un filtre", f"Ce fichier ne peut pas être lu :\n{erreur}", parent=self)
            return
        if self.entrees:
            self._memoriser_saisies()
        self.entrees = {}
        if not self._appliquer_etat(etat):
            messagebox.showerror("Ouvrir un filtre", "Ce fichier ne décrit pas un filtre de ce programme.",
                                 parent=self)
            return
        self.fichier = os.path.abspath(chemin)
        self._enregistre = self._contenu_filtre()
        self._retenir_dossier(chemin)
        self._reprendre(self.onglets.actif)

    def enregistrer_filtre(self, sous: bool = False) -> bool:
        """Fichier > Enregistrer le filtre : gabarit, séries et options dans un fichier .filtre.
        Renvoie True si le filtre est enregistré (False : boîte annulée ou erreur d'écriture)."""
        chemin = self.fichier
        if chemin is None or sous:
            chemin = self.demander_enregistrement("Enregistrer le filtre", f"{self.nom_base()}.filtre", ".filtre",
                                                  self.TYPES_FICHIER)
            if not chemin:
                return False
        contenu = self._contenu_filtre()
        donnees = dict({"programme": "Filtres de Butterworth", "version": VERSION}, **contenu)
        try:
            with open(chemin, "w", encoding="utf-8") as fichier:
                json.dump(donnees, fichier, ensure_ascii=False, indent=2)
        except OSError as erreur:
            messagebox.showerror("Enregistrer le filtre", f"Le fichier n'a pas pu être enregistré :\n{erreur}",
                                 parent=self)
            return False
        self.fichier = os.path.abspath(chemin)
        self._enregistre = contenu
        self._maj_titre()
        self._garder_session()
        self.etat.annoncer(f"Filtre enregistré : {os.path.basename(chemin)}")
        return True

    def quitter(self, demander: bool = True) -> None:
        """Fichier > Quitter, Ctrl+Q ou croix de la fenêtre : confirmation, avec proposition
        d'enregistrer un filtre qui ne l'est pas. La saisie est gardée pour le prochain lancement."""
        if demander and not self._confirmer_abandon("quitter"):
            return
        try:
            self._garder_session()
        except Exception:
            traceback.print_exc()
        self.destroy()

    def destroy(self) -> None:
        """Ferme la fenêtre. Les actions programmées (redessins différés, messages brefs…) sont
        annulées d'abord : sinon elles se déclencheraient sans fenêtre, avec un message d'erreur
        de Tcl dans la console."""
        try:
            for ident in self.tk.splitlist(self.tk.call("after", "info")):
                self.tk.call("after", "cancel", ident)
        except tk.TclError:
            pass
        super().destroy()


def lancer(fichier: Optional[str] = None, pret: Optional[Callable[[], None]] = None) -> None:
    """Ouvre la fenêtre du programme (et le filtre donné, par exemple après un double-clic) ;
    au premier lancement d'une nouvelle version, ses nouveautés s'affichent une fois.

    pret : appelé une fois la fenêtre affichée (programme installé : fermeture de l'écran de
    démarrage, qui reste visible pendant le chargement et le premier calcul)."""
    app = Application(fichier, annoncer_nouveautes=True)
    if pret is not None:
        etat = {"fait": False}

        def fermer(_e=None) -> None:
            if not etat["fait"]:
                etat["fait"] = True
                app.after(80, _sans_erreur(pret))         # la fenêtre a eu le temps de se dessiner

        app.bind("<Map>", lambda e: fermer() if e.widget is app else None, add="+")
        app.after(15000, fermer)                         # au pire, l'écran ne reste pas affiché
    app.mainloop()


def _sans_erreur(action: Callable[[], None]) -> Callable[[], None]:
    """Action qui ne doit jamais interrompre le programme (fermeture de l'écran de démarrage)."""
    def appel() -> None:
        try:
            action()
        except Exception:
            traceback.print_exc()
    return appel


if __name__ == "__main__":
    lancer(sys.argv[1] if len(sys.argv) > 1 else None)
