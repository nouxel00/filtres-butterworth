# -*- coding: utf-8 -*-
"""
aide.py
=======
Aide du programme : fenêtres d'aide (mode d'emploi et nouveautés tirés du LISEZMOI,
raccourcis clavier, à propos), visite guidée de la fenêtre, et fenêtre du petit cours
« Comprendre Sallen & Key » (textes et figures : guide.py).
"""

from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import graphes as gr
import guide
from commun import (
    barre_automatique, BoutonPlat, chemin_ressource, DEPOT, enregistrer_preferences,
    fichier_preferences, insecable, Lien, UI, VERSION)

if TYPE_CHECKING:                     # annotations seulement : interface.py importe ce module
    from interface import Application


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
        px = self.theme.px
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

        self._construire_sommaire()

        # Chapitre et navigation
        droite = tk.Frame(self, bg=UI["surface"])
        droite.pack(side="left", fill="both", expand=True)
        self._construire_navigation(droite)
        self._construire_page(droite)
        for touche, pas in (("<Left>", -1), ("<Prior>", -1), ("<Right>", 1), ("<Next>", 1)):
            self.bind(touche, lambda _e, pas=pas: self.afficher(self.actuel + pas))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.afficher(chapitre)
        self.focus_set()

    def _construire_sommaire(self) -> None:
        """Sommaire à gauche : titre, présentation du cours et un lien par chapitre."""
        px, P = self.theme.px, self.theme.polices
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

    def _construire_navigation(self, droite: tk.Frame) -> None:
        """Bas de page : « Précédent », position, « Copier le chapitre » et « Suivant » (« Fermer »
        au dernier chapitre)."""
        px, P = self.theme.px, self.theme.polices
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

    def _construire_page(self, droite: tk.Frame) -> None:
        """Page du chapitre : zone de texte et barre de défilement (affichée seulement si besoin)."""
        px, P = self.theme.px, self.theme.polices
        cadre = tk.Frame(droite, bg=UI["surface"])
        cadre.pack(fill="both", expand=True, padx=(px(32), px(8)), pady=(px(20), 0))
        t = self.texte = tk.Text(cadre, bg=UI["surface"], fg=UI["encre"], relief="flat", bd=0,
                                 highlightthickness=0, wrap="word", cursor="arrow", width=1, height=1,
                                 font=P["texte"], padx=0, pady=0)
        defil = ttk.Scrollbar(cadre, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=barre_automatique(defil, side="right", fill="y", before=t))
        t.pack(side="left", fill="both", expand=True, padx=(0, px(16)))
        self._styles_page(t)
        t.bind("<Configure>", self._redimensionne, add="+")

    def _styles_page(self, t: tk.Text) -> None:
        """Styles du chapitre : numéro, titre, intertitres, puces, formules, figures et encadrés
        « À retenir » et « Dans votre filtre »."""
        px, P = self.theme.px, self.theme.polices
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


class AideMixin:
    """Menu Aide de la fenêtre principale : fenêtres d'aide (mode d'emploi, raccourcis,
    nouveautés, à propos), petit cours « Comprendre Sallen & Key » et visite guidée.
    Classe de base de Application (interface.py)."""

    def _menu_aide(self, barre: tk.Menu) -> None:
        """Menu Aide : visite guidée, mode d'emploi (F1), petit cours (F2), raccourcis, nouveautés,
        à propos ; tout fonctionne sans Internet."""
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
