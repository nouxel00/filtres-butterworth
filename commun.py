# -*- coding: utf-8 -*-
"""
commun.py
=========
Éléments communs de la fenêtre : couleurs et polices (Theme), numéro de version,
ressources livrées avec le programme, préférences de l'utilisateur, et les petits
composants graphiques réutilisés partout (boutons plats, liens, infobulles, sections
repliables, zones défilantes, dialogues).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from matplotlib.figure import Figure

import moteur as mt


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
VERSION = "2.1"


DEPOT = "https://github.com/nouxel00/filtres-butterworth"   # code source (licence MIT)


# Tailles du texte proposées dans le menu Affichage (facteur appliqué à toute la fenêtre).
TAILLES_TEXTE = [("Texte normal", 1.0), ("Texte grand", 1.15), ("Texte très grand", 1.3)]


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


def rectangle_arrondi(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, rayon: float,
                      **options) -> int:
    """Rectangle aux coins arrondis sur un Canvas (polygone lissé)."""
    r = min(rayon, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=12, **options)


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
