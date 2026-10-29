# -*- coding: utf-8 -*-
"""
panneaux.py
===========
Zone des résultats de la fenêtre principale : bandeau des résultats clés, barre
d'onglets, et le contenu de chaque onglet (Bode normalisé et réel, étapes du calcul,
composants, câblage), avec l'accueil affiché tant qu'aucun filtre n'est calculé.
"""

from __future__ import annotations

import base64
import io
import itertools
import math
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import graphes as gr
import guide
import moteur as mt
from commun import (
    barre_automatique, BoutonPlat, CadreDefilant, entete_panneau, image_tk, Infobulle, insecable,
    Lien, rectangle_arrondi, texte_souple, Theme, UI, ZoneImage)

if TYPE_CHECKING:                     # annotations seulement : interface.py importe ce module
    from interface import Application


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

        self._construire_entete()
        defilant = CadreDefilant(self, UI["surface"])
        defilant.pack(fill="both", expand=True)
        zone = self.zone = defilant.interieur
        self._construire_statut(zone)

        # Remarques sur le montage (gain du passe-bande, bande très large, valeurs peu réalistes…)
        self.note = tk.Label(zone, text="", font=P["petit"], fg=UI["encre2"], bg=UI["surface"], anchor="w",
                             justify="left")
        self.note.bind("<Configure>", lambda e: self.note.configure(wraplength=max(200, e.width - px(6))))

        self._construire_corps(zone)
        self._construire_detail()

        # Message pour le coupe-bande
        self.vide = tk.Label(zone, text="", font=P["texte"], fg=UI["encre2"], bg=UI["surface"],
                             justify="center", wraplength=px(600))

    def _construire_entete(self) -> None:
        """Titre de l'onglet, lien « Copier le tableau » et « ? » : comment les composants sont repérés."""
        theme, px, P = self.theme, self.theme.px, self.theme.polices
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

    def _construire_statut(self, zone: tk.Frame) -> None:
        """Message sur les valeurs normalisées et explication « Que faire ? » (cachés au départ)."""
        theme, app = self.theme, self.app
        px, P = theme.px, theme.polices
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

    def _construire_corps(self, zone: tk.Frame) -> None:
        """Corps de l'onglet : liste des cellules (cartes) et cadre du détail de la cellule choisie."""
        px, P = self.theme.px, self.theme.polices
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

    def _construire_detail(self) -> None:
        """Détail de la cellule choisie : titre, lien vers le cours, schéma, tableau des composants et
        légende du schéma."""
        theme, px, P = self.theme, self.theme.px, self.theme.polices
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
