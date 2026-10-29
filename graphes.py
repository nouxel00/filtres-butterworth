# -*- coding: utf-8 -*-
"""
graphes.py
==========
Tout ce qui est dessiné avec matplotlib :

    - les diagrammes de Bode (gain et phase) avec le gabarit,
    - le curseur de lecture qui suit la souris,
    - le schéma électrique d'une cellule avec les valeurs de ses composants,
    - le schéma de câblage du montage réel (µA741), avec nomenclature et notes,
    - le rendu des fonctions de transfert en images (formules mathématiques).

Les fonctions reçoivent une Figure matplotlib déjà créée : elles marchent aussi
bien dans l'interface Tkinter que dans un script qui enregistre des PNG.
"""

from __future__ import annotations

import io
import math
import warnings
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np
import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, Polygon, Rectangle
from matplotlib.text import Annotation, Text
from matplotlib.transforms import Bbox, IdentityTransform
from matplotlib.ticker import (EngFormatter, FuncFormatter, Locator, LogLocator,
                               NullFormatter)

import moteur as mt


# =============================================================================
# Couleurs (communes avec l'interface)
# =============================================================================

COULEURS = {
    "fond": "#FFFFFF",
    "encre": "#1B2A3A",        # texte principal, traits du schéma
    "encre2": "#4A5A6A",       # texte secondaire
    "discret": "#5B6676",      # graduations, légendes
    "grille": "#E6EAF0",       # quadrillage principal
    "grille_fine": "#F2F4F7",  # quadrillage secondaire
    "axe": "#C5CED8",          # axes
    "courbe": "#2A78D6",       # réponse du filtre
    "serie": "#EB6834",        # montage aux valeurs normalisées (E6, E12)
    "aop": "#7A4FD0",          # montage avec de vrais µA741 (option du Bode réel)
    "interdit": "#D03B3B",     # zones interdites du gabarit
    "accent": "#1F5FBF",
}


def configurer_matplotlib(police: Optional[str] = None) -> None:
    """Réglages globaux : police de l'interface, couleurs discrètes, formules type LaTeX."""
    # Fenêtre en cours de construction (graphique encore minuscule) : avertissement sans objet
    warnings.filterwarnings("ignore", message="constrained_layout not applied")
    from matplotlib import font_manager
    disponibles = {f.name for f in font_manager.fontManager.ttflist}
    polices = [p for p in (police, "Segoe UI", "Helvetica Neue", "Arial") if p and p in disponibles]
    reglages = {
        # Familles nommées une à une : un caractère absent de la police de l'interface (✓, ✕, Ω…)
        # est pris dans la suivante (DejaVu Sans, livrée avec matplotlib), à l'écran et dans les PDF.
        "font.family": polices + ["DejaVu Sans"],
        "font.sans-serif": polices + ["DejaVu Sans"],
        "font.size": 10,
        "axes.edgecolor": COULEURS["axe"],
        "axes.labelcolor": COULEURS["encre2"],
        "axes.linewidth": 0.8,
        "xtick.color": COULEURS["axe"],
        "ytick.color": COULEURS["axe"],
        "xtick.labelcolor": COULEURS["discret"],
        "ytick.labelcolor": COULEURS["discret"],
        "axes.unicode_minus": True,
        "mathtext.fontset": "cm",
    }
    for cle, valeur in reglages.items():
        try:                                 # certaines clés n'existent pas
            matplotlib.rcParams[cle] = valeur  # dans les anciennes versions
        except (KeyError, ValueError):
            pass


def _activer_mise_en_page(fig: Figure) -> None:
    """Mise en page automatique des marges (selon la version de matplotlib)."""
    try:
        fig.set_layout_engine("constrained")
        fig.get_layout_engine().set(h_pad=4 / 72, w_pad=6 / 72, hspace=0.02)
    except AttributeError:
        fig.set_constrained_layout(True)


# =============================================================================
# Diagrammes de Bode
# =============================================================================

@dataclass
class Courbe:
    """Données tracées, conservées pour le curseur de lecture."""
    x: np.ndarray
    gain: np.ndarray
    phase: np.ndarray
    formater_x: Callable[[float], str]
    gain2: Optional[np.ndarray] = None    # montage aux valeurs normalisées (si demandé)
    libelle2: str = ""
    gain3: Optional[np.ndarray] = None    # montage avec de vrais µA741 (si demandé)
    libelle3: str = ""
    dispersion: Optional[mt.Dispersion] = None   # montages tirés dans les tolérances (si demandé)


def creer_figure_bode(dpi: float = 100) -> Tuple[Figure, object, object]:
    """Figure à deux étages : gain (2/3 de la hauteur) et phase (1/3)."""
    fig = Figure(dpi=dpi, facecolor=COULEURS["fond"])
    grille = fig.add_gridspec(2, 1, height_ratios=[2.1, 1])
    ax_g = fig.add_subplot(grille[0])
    ax_p = fig.add_subplot(grille[1], sharex=ax_g)
    _activer_mise_en_page(fig)
    return fig, ax_g, ax_p


class GraduationsEspacees(Locator):
    """Graduations multiples d'un pas rond (10 dB, 90°…), choisi à chaque tracé selon la
    hauteur réelle de l'axe : sur un petit écran ou avec un grand texte, le pas s'élargit
    (20 dB, 180°…) au lieu de laisser les étiquettes se chevaucher."""

    def __init__(self, pas: Tuple[float, ...], maximum: int):
        self.pas, self.maximum = pas, maximum      # pas possibles (croissants), graduations au plus

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def _place(self) -> int:
        """Nombre d'étiquettes qui tiennent sur la hauteur de l'axe (une tous les 1,7 corps de texte)."""
        try:
            ax = self.axis.axes
            hauteur = ax.get_window_extent().height * 72 / ax.get_figure().dpi      # en points
            corps = FontProperties(size=matplotlib.rcParams["ytick.labelsize"]).get_size_in_points()
            return int(hauteur / (1.7 * corps)) + 1
        except Exception:                          # axe pas encore placé
            return self.maximum

    def tick_values(self, vmin, vmax):
        vmin, vmax = sorted((float(vmin), float(vmax)))
        place = max(2, min(self._place(), self.maximum))

        def graduations(pas: float) -> np.ndarray:
            debut = pas * math.ceil(vmin / pas - 1e-9)
            return np.arange(debut, vmax + pas * 1e-9, pas)

        for pas in self.pas:                       # le pas le plus fin qui laisse la place
            valeurs = graduations(pas)
            if len(valeurs) <= place:
                return valeurs
        return graduations(self.pas[-1])


class EtiquettePoint(Annotation):
    """Valeur lue en un point de contrôle, placée à chaque tracé selon la taille réelle du
    graphique : au premier emplacement qui reste sous le haut du cadre (au-dessus, il y a les
    noms des fréquences) sans toucher les étiquettes déjà placées. Si aucun ne convient et
    qu'une étiquette voisine affiche déjà la même valeur, celle-ci n'est pas répétée."""

    def __init__(self, texte: str, xy, emplacements: List[tuple], voisines: list, **options):
        self.emplacements = emplacements                 # [(dx, dy en points, ha, va), …] par préférence
        self.voisines = voisines                         # étiquettes du graphique, dans l'ordre
        self.cachee = False
        dx, dy, ha, va = emplacements[0]
        super().__init__(texte, xy, xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, **options)

    def _placer(self, dx: float, dy: float, ha: str, va: str) -> None:
        self.xyann = (dx, dy)
        self.set_horizontalalignment(ha)
        self.set_verticalalignment(va)

    def placer(self, renderer) -> None:
        """Choisit l'emplacement pour la taille actuelle du graphique."""
        self.cachee = False
        self._placer(*self.emplacements[0])
        if self.axes is None:
            return
        try:
            avant = self.voisines[:self.voisines.index(self)] if self in self.voisines else []
            occupees = []
            for voisine in avant:
                voisine.placer(renderer)
                if not voisine.cachee:
                    occupees.append((voisine, Annotation.get_window_extent(voisine, renderer)))
            haut = self.axes.bbox.y1 + 1
            for emplacement in self.emplacements:
                self._placer(*emplacement)
                boite = Annotation.get_window_extent(self, renderer)
                if boite.y1 <= haut and not any(boite.overlaps(b) for _v, b in occupees):
                    return
            # Aucun emplacement libre : repli, ou rien si la même valeur est déjà écrite à côté
            self._placer(*self.emplacements[-1])
            boite = Annotation.get_window_extent(self, renderer)
            self.cachee = any(v.get_text() == self.get_text() and boite.overlaps(b) for v, b in occupees)
        except Exception:
            pass

    def get_window_extent(self, renderer=None):
        if renderer is not None:              # mise en page : avec l'emplacement retenu
            self.placer(renderer)
            if self.cachee:
                return Bbox.null()
        return super().get_window_extent(renderer)

    def draw(self, renderer):
        self.placer(renderer)
        if not self.cachee:
            super().draw(renderer)


class RepereHaut(Annotation):
    """Nom d'une fréquence du gabarit écrit au-dessus du cadre ; il monte d'un cran s'il
    toucherait le nom précédent (fréquences proches, graphique étroit)."""

    def __init__(self, nom: str, f: float, transformation, precedent: Optional["RepereHaut"], **options):
        super().__init__(nom, (f, 1), xycoords=transformation, xytext=(0, 3), textcoords="offset points",
                         ha="center", va="bottom", annotation_clip=False, clip_on=False, **options)
        self.precedent, self.niveau = precedent, 0

    def placer(self, renderer) -> None:
        self.niveau, self.xyann = 0, (0, 3)
        p = self.precedent
        if p is None:
            return
        try:
            p.placer(renderer)
            if p.niveau == 0:
                a = Annotation.get_window_extent(self, renderer)
                b = Annotation.get_window_extent(p, renderer)
                marge = renderer.points_to_pixels(4)
                if a.x0 < b.x1 + marge and b.x0 < a.x1 + marge:
                    self.niveau, self.xyann = 1, (0, 16)
        except Exception:
            pass

    def get_window_extent(self, renderer=None):
        if renderer is not None:
            self.placer(renderer)
        return super().get_window_extent(renderer)

    def draw(self, renderer):
        self.placer(renderer)
        super().draw(renderer)


class TexteZone(Text):
    """Mention « zone interdite » dans une zone du gabarit, placée à chaque tracé : au centre
    de la zone, ou un peu à côté si une valeur lue (ou la légende) occupe le centre ; elle
    n'est pas écrite si elle ne tient pas dans la zone (taille réelle, en pixels)."""

    POSITIONS = [(0.5, 0.5), (0.35, 0.5), (0.65, 0.5), (0.5, 0.65), (0.5, 0.35),
                 (0.25, 0.5), (0.75, 0.5), (0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)]

    def __init__(self, zone: tuple, etiquettes: List[EtiquettePoint], **options):
        xa, xb, ya, yb = zone
        super().__init__(math.sqrt(xa * xb), (ya + yb) / 2, "zone interdite", ha="center", va="center",
                         **options)
        self.zone, self.etiquettes = zone, etiquettes

    def _placer(self, renderer) -> bool:
        """Cherche une position libre ; renvoie False s'il n'y en a pas."""
        ax = self.axes
        marge = renderer.points_to_pixels(5)
        xa, xb, ya, yb = self.zone
        (x1, y1), (x2, y2) = ax.transData.transform([(xa, ya), (xb, yb)])
        x1, x2, y1, y2 = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
        obstacles = []
        for etiquette in self.etiquettes:
            etiquette.placer(renderer)
            if not etiquette.cachee:
                obstacles.append(Annotation.get_window_extent(etiquette, renderer))
        if ax.get_legend() is not None:
            obstacles.append(ax.get_legend().get_window_extent(renderer))
        inverse = ax.transData.inverted()
        for fx, fy in self.POSITIONS:
            self.set_position(inverse.transform((x1 + fx * (x2 - x1), y1 + fy * (y2 - y1))))
            b = self.get_window_extent(renderer)
            b = Bbox.from_extents(b.x0 - marge, b.y0 - marge, b.x1 + marge, b.y1 + marge)
            if (b.x0 >= x1 and b.x1 <= x2 and b.y0 >= y1 and b.y1 <= y2
                    and not any(b.overlaps(o) for o in obstacles)):
                return True
        return False

    def draw(self, renderer):
        try:
            if self.axes is not None and not self._placer(renderer):
                return
        except Exception:
            pass
        super().draw(renderer)


def _formateur_reduit(x, _pos=None) -> str:
    """Graduations de l'axe des pulsations réduites : 0,1 ; 1 ; 10."""
    return f"{x:g}".replace(".", ",")


@dataclass
class _Plage:
    """Axe des fréquences d'un diagramme de Bode, réponse exacte du filtre et gabarit."""
    x_min: float
    x_max: float
    x: np.ndarray
    H: np.ndarray
    phase: np.ndarray
    passante: List[Tuple[float, float]]       # zones où G doit rester ≥ Gp
    attenuee: List[Tuple[float, float]]       # zones où G doit rester ≤ Ga
    reperes: List[Tuple[str, float]]          # fréquences du gabarit, écrites au-dessus du graphique
    points: list                              # points de contrôle (gain aux limites du gabarit)
    formater_x: Callable[[float], str]


@dataclass
class _Ajouts:
    """Courbes ajoutées au Bode réel : montage aux valeurs normalisées, dispersion des
    composants, montage avec de vrais µA741."""
    serie: bool
    gain2: Optional[np.ndarray] = None
    phase2: Optional[np.ndarray] = None
    x_disp: Optional[np.ndarray] = None
    disp: Optional[mt.Dispersion] = None
    gain3: Optional[np.ndarray] = None
    phase3: Optional[np.ndarray] = None


def tracer_bode(ax_g, ax_p, res: mt.Resultat, normalise: bool,
                choix: Optional[mt.ChoixSeries] = None, aop: bool = False,
                dispersion: bool = False) -> Courbe:
    """Trace |H| (dB) et la phase (°) avec les zones interdites du gabarit.

    normalise=True  : prototype passe-bas H(jΩ) et gabarit réduit (Ω = 1 et 1/k)
    normalise=False : filtre réel H(jω) et gabarit initial (en Hz)
    choix (séries E)  : ajoute la réponse du montage aux valeurs normalisées (filtre réel)
    aop               : ajoute la réponse du montage avec de vrais µA741 (filtre réel)
    dispersion        : ajoute la zone balayée par des montages tirés dans les tolérances
    """
    ax_g.clear()
    ax_p.clear()
    g = res.gabarit

    # ----- 1. Plage de fréquences et réponses -----------------------------------
    p = _plage_bode(res, normalise)
    gain = 20 * np.log10(np.maximum(np.abs(p.H), 1e-300))
    a = _courbes_ajoutees(res, p, normalise, choix, aop, dispersion)

    # ----- 2. Échelles -------------------------------------------------------
    y_max = 5.0
    y_min = 10 * math.floor((g.Ga - 25) / 10)
    _echelles_bode(ax_g, ax_p, p.x_min, p.x_max, y_min, y_max, normalise)

    # ----- 3. Gabarit : zones interdites ------------------------------------
    etiquettes = _zones_interdites(ax_g, p, g.Gp, g.Ga, y_min, y_max)

    # ----- 4. Courbes, légende, échelle de la phase ---------------------------
    _courbes_bode(ax_g, ax_p, p.x, gain, p.phase, a, choix)
    if a.gain2 is not None or a.gain3 is not None or a.disp is not None:
        _legende_bode(ax_g, g.type)
    _echelle_phase(ax_p, p.phase, a.phase2, a.phase3)

    # ----- 5. Points de contrôle (gain obtenu aux limites du gabarit) -------
    _points_controle(ax_g, p.points, etiquettes)
    if a.gain3 is not None:
        _points_aop(ax_g, res, p.points, choix if a.serie else None)

    # ----- 6. Repères des fréquences du gabarit, au-dessus du graphique -----
    _reperes_haut(ax_g, p.reperes, p.x_min, p.x_max)

    return Courbe(p.x, gain, p.phase, p.formater_x, a.gain2, "Normalisées" if a.gain2 is not None else "",
                  a.gain3, "µA741" if a.gain3 is not None else "", a.disp)


def _plage_bode(res: mt.Resultat, normalise: bool) -> _Plage:
    """Plage de fréquences, réponse exacte, zones du gabarit, repères et points de contrôle."""
    g = res.gabarit
    k = res.norm.k
    if normalise:
        x_min, x_max = 0.1, 4 / k
        x = np.logspace(math.log10(x_min), math.log10(x_max), 2000)
        return _Plage(x_min, x_max, x, res.H_normalisee(x), res.phase_normalisee(x),
                      passante=[(x_min, 1.0)], attenuee=[(1 / k, x_max)],
                      reperes=[("1", 1.0), (f"1/k = {mt.fmt_compact(1 / k, 3)}", 1 / k)],
                      points=res.points_controle_normalises(),
                      formater_x=lambda v: f"Ω = {mt.fmt_nombre(v, 4)}")
    if g.type == "PB":
        x_min, x_max = g.fp / 10, 4 * g.fa
        passante, attenuee = [(x_min, g.fp)], [(g.fa, x_max)]
    elif g.type == "PH":
        x_min, x_max = g.fa / 4, 10 * g.fp
        passante, attenuee = [(g.fp, x_max)], [(x_min, g.fa)]
    elif g.type == "PM":
        x_min, x_max = g.fa_moins / 3, 3 * g.fa_plus
        passante = [(g.fp_moins, g.fp_plus)]
        attenuee = [(x_min, g.fa_moins), (g.fa_plus, x_max)]
    else:
        x_min, x_max = g.fp_moins / 3, 3 * g.fp_plus
        passante = [(x_min, g.fp_moins), (g.fp_plus, x_max)]
        attenuee = [(g.fa_moins, g.fa_plus)]
    x = np.logspace(math.log10(x_min), math.log10(x_max), 2500)
    return _Plage(x_min, x_max, x, res.H(x), res.phase(x), passante, attenuee,
                  reperes=[(mt.LIBELLES[nom], getattr(g, nom)) for nom in mt.FREQUENCES[g.type]],
                  points=res.points_controle(),
                  formater_x=lambda v: mt.fmt_si(v, "Hz", 4))


def _courbes_ajoutees(res: mt.Resultat, p: _Plage, normalise: bool, choix: Optional[mt.ChoixSeries],
                      aop: bool, dispersion: bool) -> _Ajouts:
    """Réponses ajoutées au Bode réel (aucune au Bode normalisé)."""
    # Montage construit avec les valeurs normalisées : même calcul, à partir des composants
    a = _Ajouts(serie=choix is not None and choix.actif and not normalise and bool(res.montages))
    if a.serie:
        H2 = res.H_serie(p.x, choix)
        a.gain2 = 20 * np.log10(np.maximum(np.abs(H2), 1e-300))
        a.phase2 = np.degrees(np.unwrap(np.angle(H2)))
        a.phase2 += 360 * round((p.phase[0] - a.phase2[0]) / 360)     # même origine que la phase exacte
    # Montages tirés au hasard dans les tolérances des composants (enveloppe du gain, sur une
    # grille plus lâche : le dessin reste identique et le calcul quatre fois plus rapide)
    a.x_disp = np.concatenate([p.x[::4], p.x[-1:]])
    a.disp = mt.dispersion(res, a.x_disp, choix if a.serie else None) if dispersion and not normalise else None
    # Montage avec de vrais µA741 (gain et produit gain-bande finis), avec les mêmes valeurs
    # de composants que la courbe orange si une série est choisie
    if aop and not normalise and res.montages:
        H3 = res.H_aop(p.x, choix if a.serie else None)
        a.gain3 = 20 * np.log10(np.maximum(np.abs(H3), 1e-300))
        a.phase3 = np.degrees(np.unwrap(np.angle(H3)))
        a.phase3 += 360 * round((p.phase[0] - a.phase3[0]) / 360)
    return a


def _echelles_bode(ax_g, ax_p, x_min: float, x_max: float, y_min: float, y_max: float, normalise: bool) -> None:
    """Axes logarithmiques, grilles, graduations et titres des axes."""
    for ax in (ax_g, ax_p):
        ax.set_xscale("log")
        ax.set_xlim(x_min, x_max)
        ax.set_facecolor(COULEURS["fond"])
        for cote in ("top", "right"):
            ax.spines[cote].set_visible(False)
        ax.grid(True, which="major", color=COULEURS["grille"], linewidth=0.8)
        ax.grid(True, which="minor", axis="x", color=COULEURS["grille_fine"], linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(which="both", length=0, pad=5)
        # Plage courte : graduations 1-2-5 pour que l'axe reste lisible
        decades = math.log10(x_max / x_min)
        ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0) if decades <= 3 else (1.0,)))
        ax.xaxis.set_minor_locator(LogLocator(base=10, subs=np.arange(2, 10)))
        ax.xaxis.set_minor_formatter(NullFormatter())
    ax_g.set_ylim(y_min, y_max)
    ax_g.yaxis.set_major_locator(GraduationsEspacees((10, 20, 50, 100), maximum=13))
    ax_g.tick_params(axis="x", labelbottom=False)
    ax_g.set_ylabel("Gain (dB)")

    if normalise:
        ax_p.xaxis.set_major_formatter(FuncFormatter(_formateur_reduit))
        ax_p.set_xlabel("Pulsation réduite  Ω")
    else:
        ax_p.xaxis.set_major_formatter(EngFormatter(unit="Hz"))
        ax_p.set_xlabel("Fréquence")


def _zones_interdites(ax_g, p: _Plage, Gp: float, Ga: float, y_min: float, y_max: float) -> List[EtiquettePoint]:
    """Zones interdites du gabarit, leurs bords intérieurs et la mention « zone interdite ».
    Renvoie la liste des étiquettes de valeurs, que les mentions évitent (remplie à l'étape 5)."""
    etiquettes: List[EtiquettePoint] = []
    rectangles = [(a, b, y_min, Gp) for a, b in p.passante] + [(a, b, Ga, y_max) for a, b in p.attenuee]
    for (xa, xb, ya, yb) in rectangles:
        ax_g.add_patch(Rectangle((xa, ya), xb - xa, yb - ya, facecolor=COULEURS["interdit"],
                                 alpha=0.075, edgecolor="none", zorder=0.5))
        # On ne trace que les bords intérieurs (ceux qui ne sont pas sur le cadre).
        bords = [((xa, xb), (ya, ya)), ((xa, xb), (yb, yb)), ((xa, xa), (ya, yb)), ((xb, xb), (ya, yb))]
        for xs, ys in bords:
            sur_cadre = (xs[0] == xs[1] and xs[0] in (p.x_min, p.x_max)) or \
                        (ys[0] == ys[1] and ys[0] in (y_min, y_max))
            if not sur_cadre:
                ax_g.plot(xs, ys, color=COULEURS["interdit"], linewidth=1.1, alpha=0.75,
                          solid_capstyle="butt", zorder=1)
        # Mention « zone interdite » (écrite au tracé, s'il y a la place)
        ax_g.add_artist(TexteZone((xa, xb, ya, yb), etiquettes, fontsize=9, color=COULEURS["interdit"],
                                  alpha=0.75, zorder=1))
    return etiquettes


def _courbes_bode(ax_g, ax_p, x: np.ndarray, gain: np.ndarray, phase: np.ndarray, a: _Ajouts,
                  choix: Optional[mt.ChoixSeries]) -> None:
    """Gain et phase : valeurs calculées, puis les courbes ajoutées (valeurs normalisées,
    dispersion, µA741 réel). La légende du tracé précédent est retirée."""
    ax_g.plot(x, gain, color=COULEURS["courbe"], linewidth=2, solid_capstyle="round", zorder=3,
              label="Valeurs calculées")
    ax_p.plot(x, phase, color=COULEURS["courbe"], linewidth=2, solid_capstyle="round", zorder=3)
    fig = ax_g.get_figure()
    for ancienne in list(getattr(fig, "legends", [])):     # légende du tracé précédent
        ancienne.remove()
    if a.gain2 is not None:
        ax_g.plot(x, a.gain2, color=COULEURS["serie"], linewidth=2, solid_capstyle="round", zorder=4,
                  label=f"Valeurs normalisées ({choix.court()})")
        ax_p.plot(x, a.phase2, color=COULEURS["serie"], linewidth=2, solid_capstyle="round", zorder=4)
    if a.disp is not None:
        couleur = COULEURS["serie"] if a.gain2 is not None else COULEURS["courbe"]
        ax_g.fill_between(a.x_disp, a.disp.gain_min, a.disp.gain_max, color=couleur, alpha=0.2, linewidth=0,
                          zorder=2.5, label=f"Dispersion (R ±{mt.fmt_compact(100 * a.disp.tol_R)} %, "
                                            f"C ±{mt.fmt_compact(100 * a.disp.tol_C)} %)")
    if a.gain3 is not None:
        libelle3 = "µA741 réel" + (f" ({choix.court()})" if a.serie else "")
        pointilles = dict(color=COULEURS["aop"], linewidth=2, linestyle=(0, (4, 2.4)), dash_capstyle="round",
                          zorder=4.5)
        ax_g.plot(x, a.gain3, label=libelle3, **pointilles)
        ax_p.plot(x, a.phase3, **pointilles)


def _legende_bode(ax_g, type_filtre: str) -> None:
    """Légende sur une ligne au-dessus du graphique : elle ne cache ni les courbes ni les valeurs."""
    fig = ax_g.get_figure()
    poignees, libelles = ax_g.get_legend_handles_labels()
    try:
        # Une seule ligne si elle tient dans la largeur du graphique, sinon deux colonnes, sinon une
        for ncol in sorted({len(libelles), 2, 1}, reverse=True):
            legende = fig.legend(poignees, libelles, loc="outside upper right", ncol=ncol, fontsize=9.5,
                                 frameon=False, handlelength=2.2, columnspacing=1.8)
            try:
                trop_large = legende.get_window_extent(fig.canvas.get_renderer()).width > 0.97 * fig.bbox.width
            except Exception:                # figure sans canevas : pas de mesure possible
                trop_large = False
            if not trop_large or ncol == 1:
                break
            legende.remove()
    except (ValueError, TypeError):          # matplotlib < 3.7 : dans le graphique
        place = {"PB": "lower left", "PH": "lower right"}.get(type_filtre, "lower center")
        legende = ax_g.legend(loc=place, fontsize=9.5, frameon=True, handlelength=1.6, borderpad=0.6)
        legende.get_frame().set(facecolor=COULEURS["fond"], edgecolor=COULEURS["axe"], linewidth=0.6,
                                alpha=0.95)
        legende.set_zorder(7)
    for texte in legende.get_texts():
        texte.set_color(COULEURS["encre"])


def _echelle_phase(ax_p, *phases: Optional[np.ndarray]) -> None:
    """Phase : graduations multiples de 90° (180°, 360°… si l'axe est petit)."""
    toutes = np.concatenate([p for p in phases if p is not None])
    p_min, p_max = float(np.min(toutes)), float(np.max(toutes))
    pas = 90 if p_max - p_min <= 720 else (180 if p_max - p_min <= 1440 else 360)
    ax_p.set_ylim(pas * math.floor((p_min - 10) / pas), pas * math.ceil((p_max + 10) / pas))
    ax_p.yaxis.set_major_locator(GraduationsEspacees((90, 180, 360, 720, 1440), maximum=11))
    ax_p.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}°".replace("-", "−")))
    ax_p.set_ylabel("Phase")


def _cote_texte(dx: float) -> str:
    """Alignement d'une étiquette placée du côté `dx` de son point."""
    return "left" if dx > 0 else "right"


def _points_controle(ax_g, points: list, etiquettes: List[EtiquettePoint]) -> None:
    """Gain obtenu aux limites du gabarit : un point et sa valeur, placée là où elle ne
    gêne pas (les mentions « zone interdite » évitent ensuite ces étiquettes)."""
    for p in points:
        ax_g.plot([p.f], [p.G], "o", markersize=7, markerfacecolor=COULEURS["courbe"],
                  markeredgecolor=COULEURS["fond"], markeredgewidth=1.6, zorder=5)
        # En dessous, du côté de la bande passante : place libre, dans le cadre
        dessous = (p.cote * 7, -7, _cote_texte(p.cote), "top")
        # Bande passante : au-dessus, décalée du côté où la courbe chute (s'il y a la place)
        emplacements = [(-p.cote * 12, 4, _cote_texte(-p.cote), "bottom"), dessous] if p.passante else [dessous]
        etiquette = EtiquettePoint(f"{mt.fmt_nombre(p.G, 3)} dB", (p.f, p.G), emplacements, etiquettes,
                                   fontsize=9.5, color=COULEURS["encre"], zorder=6, clip_on=False,
                                   bbox=dict(boxstyle="round,pad=0.2", facecolor=COULEURS["fond"],
                                             edgecolor="none", alpha=0.85))
        etiquette.set_transform(IdentityTransform())       # comme Axes.annotate
        ax_g.add_artist(etiquette)
        etiquettes.append(etiquette)


def _points_aop(ax_g, res: mt.Resultat, points: list, choix: Optional[mt.ChoixSeries]) -> None:
    """Avec de vrais µA741 : point violet aux limites du gabarit où le gain s'écarte du calcul."""
    for p_ideal, p_aop in zip(points, res.points_controle_aop(choix)):
        if abs(p_aop.G - p_ideal.G) > 0.05:
            ax_g.plot([p_aop.f], [p_aop.G], "o", markersize=6, markerfacecolor=COULEURS["aop"],
                      markeredgecolor=COULEURS["fond"], markeredgewidth=1.4, zorder=5.5)


def fmt_db(g: float) -> str:
    """Gain lu sur un diagramme : deux décimales (−25,72 dB ; 0,00 dB plutôt que −0,000009 dB)."""
    return "0,00" if abs(g) < 0.005 else mt.fmt_decimales(g, 2)


def fmt_deg(phi: float) -> str:
    """Phase lue sur un diagramme : une décimale."""
    return "0,0" if abs(phi) < 0.05 else mt.fmt_decimales(phi, 1)


def valeurs_en(res: mt.Resultat, courbe: Courbe, x: float, normalise: bool,
               choix: Optional[mt.ChoixSeries] = None) -> Tuple[float, float, Optional[float], Optional[float]]:
    """Valeurs exactes en un point (fréquence en Hz, ou pulsation réduite Ω) : gain (dB) et
    phase (°) du filtre, puis gain des courbes ajoutées au tracé (valeurs normalisées, µA741).

    La phase est calculée sur une grille qui part du même point que la courbe tracée :
    elle est donc continue avec elle (−450° plutôt que −90° pour un ordre 5)."""
    def gain(h) -> float:
        return float(20 * np.log10(max(abs(h), 1e-300)))
    reponse = res.H_normalisee if normalise else res.H
    phase = res.phase_normalisee if normalise else res.phase
    G = gain(reponse(np.array([x]))[0])
    depart = float(courbe.x[0])
    if x >= depart:
        ph = float(phase(np.logspace(math.log10(depart), math.log10(x), 1500))[-1])
    else:
        ph = float(phase(np.logspace(math.log10(x), math.log10(depart), 1500))[0])
    serie = choix is not None and choix.actif
    G2 = gain(res.H_serie(np.array([x]), choix)[0]) if courbe.gain2 is not None else None
    G3 = gain(res.H_aop(np.array([x]), choix if serie else None)[0]) if courbe.gain3 is not None else None
    return G, ph, G2, G3


def _reperes_haut(ax, reperes, x_min, x_max) -> None:
    """Noms des fréquences du gabarit au-dessus du graphique, décalés s'ils se chevauchent."""
    from matplotlib.transforms import blended_transform_factory
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    precedent = None
    for nom, f in sorted(reperes, key=lambda r: r[1]):
        if not x_min <= f <= x_max:
            continue
        repere = RepereHaut(nom, f, trans, precedent, fontsize=9.5, color=COULEURS["encre2"])
        repere.set_transform(IdentityTransform())
        ax.add_artist(repere)
        precedent = repere


class Curseur:
    """Ligne verticale qui suit la souris et affiche la fréquence, le gain et la phase.

    Le dessin utilise le « blitting » : seule la ligne est redessinée, ce qui
    garde l'interface fluide.
    """

    def __init__(self, canvas, ax_g, ax_p, afficher: Optional[Callable[[Optional[str]], None]] = None):
        """`afficher(texte)` reçoit la lecture (None quand la souris quitte le graphique).
        Sans cette fonction, la lecture s'affiche dans un cadre en bas du graphique."""
        self.canvas = canvas
        self.ax_g, self.ax_p = ax_g, ax_p
        self.afficher = afficher
        self.courbe: Optional[Courbe] = None
        self.fond = None
        self.artistes: List = []
        canvas.mpl_connect("draw_event", self._apres_dessin)
        canvas.mpl_connect("motion_notify_event", self._mouvement)
        canvas.mpl_connect("figure_leave_event", lambda _e: self._cacher())

    def attacher(self, courbe: Courbe) -> None:
        """À appeler après chaque tracé (ax.clear() efface les anciens éléments)."""
        self.courbe = courbe
        style = dict(color=COULEURS["encre"], linewidth=0.8, alpha=0.45, animated=True, visible=False)
        point = dict(marker="o", markersize=6, markerfacecolor=COULEURS["courbe"],
                     markeredgecolor=COULEURS["fond"], markeredgewidth=1.4, linestyle="none",
                     animated=True, visible=False)
        self.ligne_g = self.ax_g.axvline(courbe.x[0], **style)
        self.ligne_p = self.ax_p.axvline(courbe.x[0], **style)
        self.point_g, = self.ax_g.plot([courbe.x[0]], [courbe.gain[0]], **point)
        self.point_p, = self.ax_p.plot([courbe.x[0]], [courbe.phase[0]], **point)
        self.artistes = [self.ligne_g, self.ligne_p, self.point_g, self.point_p]
        self.texte = None
        if self.afficher is None:
            self.texte = self.ax_g.text(0.012, 0.035, "", transform=self.ax_g.transAxes, ha="left",
                                        va="bottom", fontsize=10, color=COULEURS["encre"], animated=True,
                                        visible=False,
                                        bbox=dict(boxstyle="round,pad=0.35", facecolor=COULEURS["fond"],
                                                  edgecolor=COULEURS["axe"], linewidth=0.6, alpha=0.95))
            self.artistes.append(self.texte)

    def _apres_dessin(self, _event) -> None:
        """Mémorise l'image du graphique sans le curseur (fond pour le blitting)."""
        self.fond = self.canvas.copy_from_bbox(self.canvas.figure.bbox)

    def _mouvement(self, event) -> None:
        """Place le curseur sur le point de la courbe le plus proche de la souris."""
        if (self.courbe is None or self.fond is None or event.xdata is None
                or event.inaxes not in (self.ax_g, self.ax_p)):
            self._cacher()
            return
        c = self.courbe
        i = int(np.clip(np.searchsorted(c.x, event.xdata), 0, len(c.x) - 1))
        x, gdb, ph = c.x[i], c.gain[i], c.phase[i]
        self.ligne_g.set_xdata([x, x])
        self.ligne_p.set_xdata([x, x])
        self.point_g.set_data([x], [gdb])
        self.point_p.set_data([x], [ph])
        texte = f"{c.formater_x(x)}     G = {fmt_db(gdb)} dB     φ = {fmt_deg(ph)}°"
        if c.gain2 is not None:
            texte += f"     {c.libelle2} : G = {fmt_db(c.gain2[i])} dB"
        if c.gain3 is not None:
            texte += f"     {c.libelle3} : G = {fmt_db(c.gain3[i])} dB"
        if self.afficher is not None:
            self.afficher(texte)
        else:
            self.texte.set_text(texte)
        self._dessiner(True)

    def _cacher(self) -> None:
        """Efface le curseur quand la souris quitte le graphique."""
        if self.artistes and self.artistes[0].get_visible() and self.fond is not None:
            self._dessiner(False)
            if self.afficher is not None:
                self.afficher(None)

    def _dessiner(self, visible: bool) -> None:
        """Redessine seulement le curseur par-dessus le fond mémorisé."""
        self.canvas.restore_region(self.fond)
        for a in self.artistes:
            a.set_visible(visible)
            if visible:
                a.axes.draw_artist(a)
        self.canvas.blit(self.canvas.figure.bbox)


# =============================================================================
# Schémas électriques des cellules
# =============================================================================

class _Dessin:
    """Petits outils de dessin de schéma (symboles normalisés IEC)."""

    def __init__(self, ax):
        self.ax = ax
        self.encre = COULEURS["encre"]
        self.lw = 1.4

    def fil(self, *points) -> None:
        """Fil de liaison passant par les points donnés."""
        xs, ys = zip(*points)
        self.ax.plot(xs, ys, color=self.encre, linewidth=self.lw, solid_capstyle="round",
                     solid_joinstyle="round", zorder=2)

    def noeud(self, x, y) -> None:
        """Point de connexion entre plusieurs fils."""
        self.ax.add_patch(Circle((x, y), 0.065, color=self.encre, zorder=4))

    def borne(self, x, y) -> None:
        """Borne d'entrée ou de sortie (petit cercle)."""
        self.ax.add_patch(Circle((x, y), 0.1, facecolor=COULEURS["fond"], edgecolor=self.encre,
                                 linewidth=self.lw, zorder=4))

    def resistance(self, a, b, longueur=0.95, largeur=0.3) -> None:
        """Résistance (rectangle, norme IEC) entre deux points alignés."""
        (x1, y1), (x2, y2) = a, b
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if y1 == y2:                                      # horizontale
            self.fil(a, (cx - longueur / 2, cy))
            self.fil((cx + longueur / 2, cy), b)
            coin, l, h = (cx - longueur / 2, cy - largeur / 2), longueur, largeur
        else:                                             # verticale
            self.fil(a, (cx, cy + longueur / 2 * np.sign(y1 - y2)))
            self.fil((cx, cy - longueur / 2 * np.sign(y1 - y2)), b)
            coin, l, h = (cx - largeur / 2, cy - longueur / 2), largeur, longueur
        self.ax.add_patch(Rectangle(coin, l, h, facecolor=COULEURS["fond"], edgecolor=self.encre,
                                    linewidth=self.lw, zorder=3))

    def condensateur(self, a, b, ecart=0.17, plaque=0.56) -> None:
        """Condensateur (deux plaques) entre deux points alignés."""
        (x1, y1), (x2, y2) = a, b
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        epais = dict(color=self.encre, linewidth=2.4, solid_capstyle="butt", zorder=3)
        if y1 == y2:
            self.fil(a, (cx - ecart / 2, cy))
            self.fil((cx + ecart / 2, cy), b)
            for dx in (-ecart / 2, ecart / 2):
                self.ax.plot([cx + dx, cx + dx], [cy - plaque / 2, cy + plaque / 2], **epais)
        else:
            s = np.sign(y1 - y2)
            self.fil(a, (cx, cy + s * ecart / 2))
            self.fil((cx, cy - s * ecart / 2), b)
            for dy in (-ecart / 2, ecart / 2):
                self.ax.plot([cx - plaque / 2, cx + plaque / 2], [cy + dy, cy + dy], **epais)

    def suiveur(self, x, y, largeur=1.25, hauteur=1.3) -> Tuple[float, float]:
        """Amplificateur de gain 1 (triangle marqué « 1 »). Renvoie la sortie."""
        self.ax.add_patch(Polygon([(x, y - hauteur / 2), (x, y + hauteur / 2), (x + largeur, y)],
                                  closed=True, facecolor=COULEURS["fond"], edgecolor=self.encre,
                                  linewidth=self.lw, zorder=3))
        self.ax.text(x + largeur * 0.36, y, "1", ha="center", va="center", fontsize=11,
                     color=self.encre, zorder=4)
        return x + largeur, y

    def aop(self, x, y_moins, y_plus, largeur=1.7) -> Tuple[float, float]:
        """Amplificateur opérationnel (entrées − et +). Renvoie la sortie."""
        y_c = (y_moins + y_plus) / 2
        demi = abs(y_moins - y_plus) / 2 + 0.45
        self.ax.add_patch(Polygon([(x, y_c - demi), (x, y_c + demi), (x + largeur, y_c)], closed=True,
                                  facecolor=COULEURS["fond"], edgecolor=self.encre, linewidth=self.lw,
                                  zorder=3))
        for yy, signe in ((y_moins, "−"), (y_plus, "+")):
            self.ax.text(x + 0.2, yy, signe, ha="center", va="center", fontsize=11, color=self.encre, zorder=4)
        self.ax.text(x + largeur * 0.45, y_c, "∞", ha="center", va="center", fontsize=10,
                     color=COULEURS["encre2"], zorder=4)
        return x + largeur, y_c

    def tension(self, x, y_bas, y_haut, nom, gauche=False) -> None:
        """Flèche de tension (V1, V2) entre la masse et la borne."""
        self.ax.annotate("", (x, y_haut - 0.22), (x, y_bas + 0.22),
                         arrowprops=dict(arrowstyle="-|>", color=COULEURS["encre2"], linewidth=1,
                                         shrinkA=0, shrinkB=0, mutation_scale=9))
        self.ax.text(x + (-0.18 if gauche else 0.18), (y_bas + y_haut) / 2, nom, ha="right" if gauche else "left",
                     va="center", fontsize=11.5, color=COULEURS["encre2"])

    def etiquette(self, x, y, nom, valeur, place="haut") -> None:
        """Nom du composant (discret) et sa valeur (en gras)."""
        txt_nom = dict(fontsize=9.5, color=COULEURS["discret"], zorder=5)
        txt_val = dict(fontsize=10.5, color=self.encre, fontweight="bold", zorder=5)
        if place == "haut":
            self.ax.annotate(valeur, (x, y), xytext=(0, 3), textcoords="offset points",
                             ha="center", va="bottom", **txt_val)
            self.ax.annotate(nom, (x, y), xytext=(0, 17.5), textcoords="offset points",
                             ha="center", va="bottom", **txt_nom)
        else:                                               # à droite ou à gauche
            dx, ha = (7, "left") if place == "droite" else (-7, "right")
            self.ax.annotate(nom, (x, y), xytext=(dx, 1), textcoords="offset points",
                             ha=ha, va="bottom", **txt_nom)
            self.ax.annotate(valeur, (x, y), xytext=(dx, -1), textcoords="offset points",
                             ha=ha, va="top", **txt_val)


def _textes(cle: str, etage: mt.Etage) -> Tuple[str, str]:
    """Textes de l'étiquette d'un composant : (repère, valeur), repère du montage réel.

    Avec des valeurs normalisées, la valeur calculée est rappelée entre parenthèses
    à côté du repère quand elle diffère : « C1 (220,8 nF) » au-dessus de « 220 nF »,
    ou d'une association « C1 + C2 » au-dessus de « 4,7 nF + 680 pF ».
    """
    unite = "Ω" if cle[0] == "R" else "F"
    nom, valeur = etage.designation(cle), etage.valeur(cle)
    exacte = etage.calcules[cle]
    if etage.series.get(cle[0]) and abs(etage.composants[cle].valeur / exacte - 1) > 1e-9:
        nom += f"  ({mt.fmt_si(exacte, unite, 4)})"
    return nom, valeur


def dessiner_cellule(fig: Figure, etage: mt.Etage) -> None:
    """Schéma d'une cellule du montage réel, avec ses repères (R1, R2, C1…) et ses valeurs.

    Avec des valeurs normalisées, la valeur calculée est rappelée entre parenthèses. La
    cellule qui porte le pont diviseur d'entrée du passe-bande le montre aussi.
    """
    fig.clear()
    ax = fig.add_axes([0.01, 0.02, 0.98, 0.96])
    ax.set_axis_off()
    d = _Dessin(ax)
    s = etage.montage.structure
    if s in ("SK_PB", "SK_PH"):
        _schema_sallen_key(d, ax, etage, s)
    elif s in ("RC", "CR"):
        _schema_premier_ordre(d, ax, etage, s)
    else:   # cellule passe-bande de Rauch (centre d'un passe-bande d'ordre impair)
        _schema_rauch(d, ax, etage)
    ax.set_aspect("equal", anchor="C")


def _schema_sallen_key(d: "_Dessin", ax, etage: mt.Etage, s: str) -> None:
    """Cellule de Sallen & Key, passe-bas ou passe-haut (avec, s'il y a lieu, le pont diviseur)."""
    # Disposition commune : entrée, série, masse et contre-réaction. Avec le pont diviseur,
    # la cellule s'allonge pour loger la résistance vers la masse et son étiquette, et
    # l'élément série aussi, pour que l'étiquette de l'élément vers la masse (à sa gauche,
    # souvent longue : « C3 + C4  (697,3 pF) ») ne touche pas la résistance du pont.
    ys, ym, yc = 2.4, 0.6, 4.25
    dx, ecart = (1.6, 0.9) if etage.pont else (0.0, 0.0)
    xe, xa = 0.6, 3.3 + dx
    dx += ecart
    xb, xamp, xsortie, xs = 6.0 + dx, 6.55 + dx, 8.75 + dx, 10.6 + dx
    if s == "SK_PB":
        noms = ("R1", "R2", "C1", "C2")
        types = (d.resistance, d.resistance, d.condensateur, d.condensateur)
    else:
        noms = ("C1", "C2", "R1", "R2")
        types = (d.condensateur, d.condensateur, d.resistance, d.resistance)
    d.borne(xe, ys)
    d.borne(xe, ym)
    types[0]((xe, ys), (xa, ys))                       # entrée (Y1)
    types[1]((xa, ys), (xb, ys))                       # série (Y3)
    d.fil((xb, ys), (xamp, ys))
    sortie = d.suiveur(xamp, ys)
    d.fil(sortie, (xs, ys))
    types[2]((xb, ys), (xb, ym))                       # vers la masse (Y4)
    d.fil((xa, ys), (xa, yc))
    types[3]((xa, yc), (xsortie, yc))                  # contre-réaction (Y2)
    d.fil((xsortie, yc), (xsortie, ys))
    d.fil((xe, ym), (xs, ym))
    for p in ((xa, ys), (xb, ys), (xsortie, ys), (xb, ym)):
        d.noeud(*p)
    if etage.pont:                                     # pont diviseur : résistance vers la masse
        d.resistance((xa, ys), (xa, ym))
        d.noeud(xa, ym)
        d.etiquette(xa - 0.36, (ys + ym) / 2, *_textes("Rb", etage), place="gauche")
    d.borne(xs, ys)
    d.borne(xs, ym)
    d.etiquette((xe + xa) / 2, ys + 0.2, *_textes(noms[0], etage))
    d.etiquette((xa + xb) / 2, ys + 0.2, *_textes(noms[1], etage))
    d.etiquette(xb - 0.36, (ys + ym) / 2, *_textes(noms[2], etage), place="gauche")
    d.etiquette((xa + xsortie) / 2, yc + 0.3, *_textes(noms[3], etage))
    d.tension(xe + 0.32, ym, ys, "$V_1$")
    d.tension(xs - 0.32, ym, ys, "$V_2$", gauche=True)
    ax.set_xlim(0.1, 11.1 + dx)
    ax.set_ylim(0.15, 5.35)


def _schema_premier_ordre(d: "_Dessin", ax, etage: mt.Etage, s: str) -> None:
    """Cellule du premier ordre, RC (passe-bas) ou CR (passe-haut)."""
    ys, ym = 2.4, 0.6
    xe, xn, xs = 0.6, 4.3, 7.0
    serie, masse = (("R1", "C1") if s == "RC" else ("C1", "R1"))
    type_serie = d.resistance if s == "RC" else d.condensateur
    type_masse = d.condensateur if s == "RC" else d.resistance
    d.borne(xe, ys)
    d.borne(xe, ym)
    type_serie((xe, ys), (xn, ys))
    d.fil((xn, ys), (xs, ys))
    type_masse((xn, ys), (xn, ym))
    d.fil((xe, ym), (xs, ym))
    d.noeud(xn, ys)
    d.noeud(xn, ym)
    d.borne(xs, ys)
    d.borne(xs, ym)
    d.etiquette((xe + xn) / 2, ys + 0.2, *_textes(serie, etage))
    # Étiquette de l'élément vers la masse à sa gauche, comme dans les cellules de
    # Sallen & Key : à droite, une association la ferait buter sur V2
    d.etiquette(xn - 0.36, (ys + ym) / 2, *_textes(masse, etage), place="gauche")
    d.tension(xe + 0.32, ym, ys, "$V_1$")
    d.tension(xs - 0.32, ym, ys, "$V_2$", gauche=True)
    ax.set_xlim(-1.6, 9.2)
    ax.set_ylim(0.15, 3.6)


def _schema_rauch(d: "_Dessin", ax, etage: mt.Etage) -> None:
    """Cellule passe-bande de Rauch (centre d'un passe-bande d'ordre impair)."""
    # Branches assez longues pour les étiquettes des associations (« R5 + R6  (104,7 kΩ) »)
    ys, ym, y3, y4 = 2.8, 0.6, 4.05, 5.45
    xe, xx, xn, xaop, xsortie, xs = 0.6, 4.4, 8.4, 9.05, 12.4, 14.05
    y_plus = ys - 0.8
    d.borne(xe, ys)
    d.borne(xe, ym)
    d.resistance((xe, ys), (xx, ys))                   # R1 = q·R0 (entrée)
    d.resistance((xx, ys), (xx, ym))                   # R2 = m·R0/(1 − m²)
    d.condensateur((xx, ys), (xn, ys))                 # C2 vers l'entrée −
    d.fil((xn, ys), (xaop, ys))
    sortie = d.aop(xaop, ys, y_plus)
    d.fil((xaop, y_plus), (xaop - 0.3, y_plus), (xaop - 0.3, ym))
    d.fil(sortie, (xs, sortie[1]))
    d.fil((xn, ys), (xn, y3))
    d.resistance((xn, y3), (xsortie, y3))              # R3 = q·R0 (contre-réaction)
    d.fil((xsortie, y3), (xsortie, sortie[1]))
    d.fil((xx, ys), (xx, y4))
    d.condensateur((xx, y4), (xn, y4))                 # C1 vers la sortie (au-dessus de C2,
    d.fil((xn, y4), (xsortie, y4), (xsortie, y3))      # loin de l'étiquette de R3)
    d.fil((xe, ym), (xs, ym))
    for p in ((xx, ys), (xn, ys), (xsortie, sortie[1]), (xsortie, y3), (xx, ym), (xaop - 0.3, ym)):
        d.noeud(*p)
    d.borne(xs, sortie[1])
    d.borne(xs, ym)
    d.etiquette((xe + xx) / 2, ys + 0.2, *_textes("R1", etage))
    d.etiquette(xx + 0.2, (ys + ym) / 2, *_textes("R2", etage), place="droite")
    d.etiquette((xx + xn) / 2, ys + 0.3, *_textes("C2", etage))
    d.etiquette((xn + xsortie) / 2, y3 + 0.2, *_textes("R3", etage))
    d.etiquette((xx + xn) / 2, y4 + 0.3, *_textes("C1", etage))
    d.tension(xe + 0.32, ym, ys, "$V_1$")
    d.tension(xs - 0.32, ym, sortie[1], "$V_2$", gauche=True)
    ax.set_xlim(0.1, 14.55)
    ax.set_ylim(0.15, 6.75)


# =============================================================================
# Schéma de câblage du montage réel (µA741, alimentation ±15 V)
# =============================================================================
#
# Le schéma est dessiné en « unités » ; une unité vaut `echelle` pouce (0,29 à
# 0,38) : les textes gardent la même taille quelle que soit la longueur du
# montage. Les étages sont répartis en lignes de longueurs voisines ; un renvoi
# lettré (A, B…) relie la fin d'une ligne au début de la suivante.

ECHELLE_MIN, ECHELLE_MAX = 0.29, 0.38      # pouces par unité de dessin
BRANCHE = 3.6            # longueur d'une branche horizontale portant un composant
DEBUT_LIGNE = 2.4        # borne d'entrée (ou renvoi) au début d'une ligne
FIN_LIGNE = 2.4          # borne de sortie (ou renvoi) à la fin d'une ligne
INTERVALLE = 0.4         # fil entre deux étages
ECART_PARALLELE = 0.42   # demi-écart entre deux condensateurs en parallèle
LARGEUR_MIN = 22.0       # largeur minimale du schéma (brochage et nomenclature côte à côte)

UNITES = {"R": "Ω", "C": "F"}


def largeur_etage(e: mt.Etage) -> float:
    """Largeur d'un étage dans le schéma (unités)."""
    s = e.montage.structure
    if s in ("SK_PB", "SK_PH"):
        return 2 * BRANCHE + 1.3 + 2.0 + 1.2
    if s == "RAUCH":
        return 2 * BRANCHE + 0.9 + 2.0 + 1.2
    return BRANCHE + (1.3 + 2.0 + 1.2 if e.suiveur else 1.0)


def _haut_etage(e: mt.Etage) -> float:
    """Hauteur occupée au-dessus de la ligne de signal (étiquettes comprises)."""
    s = e.montage.structure
    if s in ("SK_PB", "SK_PH"):
        return 5.4
    if s == "RAUCH":
        return 5.0
    return 2.9 if e.suiveur else 1.5


def _largeur_ligne(ligne: List[mt.Etage]) -> float:
    return DEBUT_LIGNE + FIN_LIGNE + sum(largeur_etage(e) for e in ligne) + INTERVALLE * (len(ligne) - 1)


def repartir_lignes(etages: List[mt.Etage], largeur_max: float) -> List[List[mt.Etage]]:
    """Répartit les étages en lignes d'au plus `largeur_max` unités (au moins un étage par
    ligne), avec le moins de lignes possible, puis des lignes de longueurs voisines."""
    if not etages:
        return []
    # 1. Nombre minimal de lignes (remplissage glouton)
    nombre, largeur = 1, DEBUT_LIGNE + FIN_LIGNE - INTERVALLE
    for e in etages:
        w = largeur_etage(e) + INTERVALLE
        if largeur + w > largeur_max and largeur > DEBUT_LIGNE + FIN_LIGNE:
            nombre, largeur = nombre + 1, DEBUT_LIGNE + FIN_LIGNE - INTERVALLE
        largeur += w
    # 2. Découpage en `nombre` lignes qui minimise la plus longue (programmation dynamique)
    n = len(etages)
    inf = float("inf")
    meilleur = [[inf] * (n + 1) for _ in range(nombre + 1)]
    coupe = [[0] * (n + 1) for _ in range(nombre + 1)]
    meilleur[0][0] = 0.0
    for k in range(1, nombre + 1):
        for j in range(1, n + 1):
            for i in range(k - 1, j):
                valeur = max(meilleur[k - 1][i], _largeur_ligne(etages[i:j]))
                if valeur < meilleur[k][j]:
                    meilleur[k][j], coupe[k][j] = valeur, i
    lignes, j = [], n
    for k in range(nombre, 0, -1):
        i = coupe[k][j]
        lignes.insert(0, etages[i:j])
        j = i
    return lignes


class _DessinReel(_Dessin):
    """Symboles du schéma de câblage : associations de composants, µA741 et ses broches,
    masse, renvois d'une ligne à l'autre."""

    def __init__(self, ax, normalise_R: bool, normalise_C: bool):
        super().__init__(ax)
        self.lw = 1.3
        self.normalise = {"R": normalise_R, "C": normalise_C}

    # ---------------------------------------------------------------- composants
    def composant(self, etage: mt.Etage, cle: str, a, b, place: str) -> None:
        """Composant `cle` de l'étage entre a et b, avec son étiquette (repère du montage réel).

        Une association de deux valeurs est dessinée telle qu'on la câble :
        deux résistances l'une après l'autre (en série), ou deux condensateurs
        côte à côte (en parallèle) ; son étiquette porte les deux repères
        (« R3 + R4 »). place : "haut", "gauche" ou "droite".
        """
        r, nom = etage.composants[cle], etage.designation(cle)
        genre = cle[0]
        (x1, y1), (x2, y2) = a, b
        double = len(r.elements) > 1
        decal = 0.0
        if not double:
            (self.resistance if genre == "R" else self.condensateur)(a, b)
        elif genre == "R":                                   # deux résistances en série
            milieu = ((x1 + x2) / 2, (y1 + y2) / 2)
            self.resistance(a, milieu, longueur=0.72)
            self.resistance(milieu, b, longueur=0.72)
        else:                                                # deux condensateurs en parallèle
            e = decal = ECART_PARALLELE
            if y1 == y2:                                     # branche horizontale
                cx, y = (x1 + x2) / 2, y1
                g, d = cx - 0.55, cx + 0.55
                self.fil(a, (g, y))
                self.fil((d, y), b)
                for xx in (g, d):
                    self.fil((xx, y - e), (xx, y + e))
                    self.noeud(xx, y)
                for yy in (y - e, y + e):
                    self.condensateur((g, yy), (d, yy), plaque=0.42)
            else:                                            # branche verticale
                x, cy = x1, (y1 + y2) / 2
                h, bas = cy + 0.55, cy - 0.55
                self.fil(a, (x, h))
                self.fil((x, bas), b)
                for yy in (h, bas):
                    self.fil((x - e, yy), (x + e, yy))
                    self.noeud(x, yy)
                for xx in (x - e, x + e):
                    self.condensateur((xx, h), (xx, bas), plaque=0.42)
        if place == "haut":
            self.etiquette_reelle((x1 + x2) / 2, max(y1, y2) + 0.2 + decal, nom, r, place)
        else:
            dx = (-1 if place == "gauche" else 1) * (0.3 + decal)
            self.etiquette_reelle(x1 + dx, (y1 + y2) / 2, nom, r, place)

    def etiquette_reelle(self, x, y, nom: str, r: mt.Realisation, place: str) -> None:
        """Nom (discret) et valeur(s) à câbler (en gras). Une association est écrite
        « a + b » au-dessus d'une branche horizontale, sur deux lignes à côté d'une
        branche verticale."""
        unite = UNITES[nom[0]]
        if self.normalise[nom[0]]:
            morceaux = [mt.fmt_si(v, unite, compact=True) for v in r.elements]
            valeur = (" + " if place == "haut" else "\n+ ").join(morceaux)
        else:
            valeur = mt.fmt_si(r.valeur, unite, 4)
        txt_nom = dict(fontsize=8.5, color=COULEURS["discret"], zorder=5)
        txt_val = dict(fontsize=9.5, color=self.encre, fontweight="bold", zorder=5, linespacing=1.15)
        if place == "haut":
            self.ax.annotate(valeur, (x, y), xytext=(0, 1), textcoords="offset points",
                             ha="center", va="bottom", **txt_val)
            self.ax.annotate(nom, (x, y), xytext=(0, 15), textcoords="offset points",
                             ha="center", va="bottom", **txt_nom)
        else:
            dx, ha = (-1, "right") if place == "gauche" else (1, "left")
            self.ax.annotate(nom, (x, y), xytext=(dx, 1), textcoords="offset points",
                             ha=ha, va="bottom", **txt_nom)
            self.ax.annotate(valeur, (x, y), xytext=(dx, -1), textcoords="offset points",
                             ha=ha, va="top", **txt_val)

    # ------------------------------------------------------------- µA741
    def aop_741(self, x, y_moins, y_plus, nom: str, largeur: float = 2.0) -> Tuple[float, float]:
        """µA741 : triangle, entrées − (broche 2) et + (broche 3), sortie (broche 6),
        alimentation +15 V (broche 7) et −15 V (broche 4). Renvoie la sortie."""
        y_c = (y_moins + y_plus) / 2
        demi = abs(y_moins - y_plus) / 2 + 0.7
        bas, haut = y_c - demi, y_c + demi
        sommet = (x + largeur, y_c)
        self.ax.add_patch(Polygon([(x, bas), (x, haut), sommet], closed=True, facecolor=COULEURS["fond"],
                                  edgecolor=self.encre, linewidth=self.lw, zorder=3))
        broche = dict(fontsize=8, color=COULEURS["accent"], zorder=5)
        for yy, signe, numero in ((y_moins, "−", "2"), (y_plus, "+", "3")):
            self.ax.text(x + 0.2, yy, signe, ha="center", va="center", fontsize=10.5, color=self.encre, zorder=4)
            self.ax.text(x - 0.08, yy + 0.06, numero, ha="right", va="bottom", **broche)
        self.ax.text(x + 0.8, y_c, nom, ha="center", va="center", fontsize=8.5,
                     color=COULEURS["encre2"], zorder=4)
        self.ax.text(sommet[0] + 0.08, sommet[1] + 0.06, "6", ha="left", va="bottom", **broche)
        # Alimentation : broche 7 sur le côté haut, broche 4 sur le côté bas
        xa = x + 0.7
        y7 = haut - (0.7 / largeur) * (haut - y_c)
        y4 = bas + (0.7 / largeur) * (y_c - bas)
        self.fil((xa, y7), (xa, y7 + 0.4))
        self.fil((xa, y4), (xa, y4 - 0.4))
        self.ax.text(xa + 0.08, y7 + 0.08, "7", ha="left", va="bottom", **broche)
        self.ax.text(xa + 0.08, y4 - 0.08, "4", ha="left", va="top", **broche)
        alim = dict(fontsize=8, color=COULEURS["encre2"], ha="center", zorder=5)
        self.ax.text(xa, y7 + 0.46, "+15 V", va="bottom", **alim)
        self.ax.text(xa, y4 - 0.46, "−15 V", va="top", **alim)
        return sommet

    def suiveur_741(self, xu, ys, yb, nom: str) -> float:
        """µA741 en suiveur : entrée + sur la ligne de signal, sortie reliée à l'entrée −.
        Renvoie l'abscisse du nœud de sortie."""
        sommet = self.aop_741(xu, ys + 1.0, ys, nom)
        xo = sommet[0] + 0.6
        self.fil((xu, ys + 1.0), (xu - 0.45, ys + 1.0), (xu - 0.45, yb), (xo, yb), (xo, sommet[1]))
        self.fil(sommet, (xo, sommet[1]))
        self.noeud(xo, sommet[1])
        return xo

    # ------------------------------------------------------------ divers
    def masse(self, x, y) -> None:
        """Symbole de masse sous le point (x, y)."""
        self.fil((x, y), (x, y - 0.3))
        for i, demi in enumerate((0.3, 0.19, 0.08)):
            yy = y - 0.3 - 0.11 * i
            self.ax.plot([x - demi, x + demi], [yy, yy], color=self.encre, linewidth=self.lw, zorder=2)

    def renvoi(self, x, y, lettre: str) -> None:
        """Renvoi vers (ou depuis) une autre ligne : étiquette en forme de flèche."""
        h = 0.27
        self.ax.add_patch(Polygon([(x, y - h), (x + 0.8, y - h), (x + 1.05, y), (x + 0.8, y + h), (x, y + h)],
                                  closed=True, facecolor=COULEURS["fond"], edgecolor=self.encre,
                                  linewidth=self.lw, zorder=3))
        self.ax.text(x + 0.45, y, lettre, ha="center", va="center", fontsize=9, fontweight="bold",
                     color=self.encre, zorder=4)

    def separateur(self, x, y_bas, y_haut) -> None:
        """Limite entre deux étages (pointillés)."""
        self.ax.plot([x, x], [y_bas, y_haut], color=COULEURS["axe"], linewidth=0.9,
                     linestyle=(0, (4, 3)), zorder=1)


def _dessiner_etage(d: _DessinReel, e: mt.Etage, x0: float, ym: float) -> float:
    """Dessine un étage à partir de x0 (ligne de signal en ys = ym + 3). Renvoie la fin de l'étage."""
    ys = ym + 3.0
    s = e.montage.structure
    if s in ("SK_PB", "SK_PH"):
        yb, yc = ys + 2.5, ys + 3.7
        xa, xb = x0 + BRANCHE, x0 + 2 * BRANCHE
        xu = xb + 1.3
        if s == "SK_PB":
            d.composant(e, "R1", (x0, ys), (xa, ys), "haut")
            d.composant(e, "R2", (xa, ys), (xb, ys), "haut")
            d.composant(e, "C1", (xb, ys), (xb, ym), "gauche")
            if e.pont:                                       # pont diviseur : vers la masse, au nœud R1–R2
                d.composant(e, "Rb", (xa, ys), (xa, ym), "gauche")
                d.noeud(xa, ym)
            reaction = "C2"
        else:
            d.composant(e, "C1", (x0, ys), (xa, ys), "haut")
            d.composant(e, "C2", (xa, ys), (xb, ys), "haut")
            d.composant(e, "R1", (xb, ys), (xb, ym), "gauche")
            reaction = "R2"
        d.fil((xb, ys), (xu, ys))
        xo = d.suiveur_741(xu, ys, yb, e.aop)
        d.fil((xa, ys), (xa, yc))
        d.composant(e, reaction, (xa, yc), (xo, yc), "haut")     # contre-réaction
        d.fil((xo, yc), (xo, yb))
        for p in ((xa, ys), (xb, ys), (xo, yb), (xb, ym)):
            d.noeud(*p)
        fin = xo + 0.6
        d.fil((xo, ys + 0.5), (fin, ys + 0.5), (fin, ys))
        return fin
    if s == "RAUCH":
        y3, y4 = ys + 1.8, ys + 3.4
        xx, xn = x0 + BRANCHE, x0 + 2 * BRANCHE
        xu = xn + 0.9
        d.composant(e, "R1", (x0, ys), (xx, ys), "haut")
        d.composant(e, "R2", (xx, ys), (xx, ym), "gauche")
        d.composant(e, "C2", (xx, ys), (xn, ys), "haut")
        d.fil((xn, ys), (xu, ys))
        sommet = d.aop_741(xu, ys, ys - 1.0, e.aop)
        xo = sommet[0] + 0.6
        d.fil((xu, ys - 1.0), (xu - 0.4, ys - 1.0), (xu - 0.4, ym))       # entrée + à la masse
        d.fil(sommet, (xo, sommet[1]))
        d.fil((xn, ys), (xn, y3))
        d.composant(e, "R3", (xn, y3), (xo, y3), "haut")
        d.fil((xo, y3), (xo, sommet[1]))
        d.fil((xx, ys), (xx, y4))
        d.composant(e, "C1", (xx, y4), (xo, y4), "haut")
        d.fil((xo, y4), (xo, y3))
        for p in ((xx, ys), (xn, ys), (xo, y3), (xo, sommet[1]), (xx, ym), (xu - 0.4, ym)):
            d.noeud(*p)
        fin = xo + 0.6
        d.fil((xo, sommet[1]), (fin, sommet[1]), (fin, ys))
        return fin
    # Cellule RC ou CR (1er ordre), suivie d'un suiveur si elle n'est pas la dernière
    xn = x0 + BRANCHE
    serie, masse = ("R1", "C1") if s == "RC" else ("C1", "R1")
    d.composant(e, serie, (x0, ys), (xn, ys), "haut")
    d.composant(e, masse, (xn, ys), (xn, ym), "gauche")
    d.noeud(xn, ys)
    d.noeud(xn, ym)
    if e.suiveur:
        xu = xn + 1.3
        d.fil((xn, ys), (xu, ys))
        xo = d.suiveur_741(xu, ys, ys + 2.5, e.suiveur)
        fin = xo + 0.6
        d.fil((xo, ys + 0.5), (fin, ys + 0.5), (fin, ys))
        return fin
    fin = xn + 1.0
    d.fil((xn, ys), (fin, ys))
    return fin


def _legende_etage(e: mt.Etage) -> str:
    """Légende sous un étage : cellule, montage, fréquence propre et Q."""
    c = e.montage.cellule
    f = mt.fmt_si(c.wn / (2 * math.pi), "Hz", 3)
    montage = e.montage.libelle.replace("Cellule ", "")
    texte = f"Cellule {c.nom} · {montage}"
    texte += f" · fc = {f}" if c.ordre == 1 else f" · f = {f}, Q = {mt.fmt_nombre(c.Q, 3)}"
    if e.suiveur:
        texte += f" · suiveur {e.suiveur}"
    return texte


def _caracteres(largeur: float, taille: float, echelle: float) -> int:
    """Nombre de caractères d'une ligne de `largeur` unités (largeur moyenne d'un caractère)."""
    return max(20, int(largeur / (0.58 * taille / 72 / echelle)))


def _texte_coupe(texte: str, largeur: float, taille: float, echelle: float) -> List[str]:
    """Coupe un texte en lignes d'au plus `largeur` unités, sans séparer un nombre de son
    unité (espaces insécables, que textwrap ne coupe pas)."""
    import textwrap
    return textwrap.wrap(mt.insecable(texte), _caracteres(largeur, taille, echelle))


def schema_cablage(res: mt.Resultat, choix: Optional[mt.ChoixSeries] = None,
                   largeur_pouces: float = 10.0, pont: bool = False) -> Figure:
    """Schéma de câblage complet du montage réel, avec brochage, nomenclature et notes.

    largeur_pouces : largeur disponible. Les étages sont répartis en lignes pour
    tenir dans cette largeur (à l'échelle la plus serrée), puis l'échelle est
    ajustée entre ECHELLE_MIN et ECHELLE_MAX pour occuper la place.
    pont : passe-bande avec le pont diviseur d'entrée (gain ramené à 0 dB).
    """
    etages = mt.etages_reels(res, choix, pont)
    lignes = repartir_lignes(etages, largeur_pouces / ECHELLE_MIN)
    largeur = max([LARGEUR_MIN] + [_largeur_ligne(ligne) for ligne in lignes])
    echelle = max(0.26, min(ECHELLE_MAX, largeur_pouces / largeur))
    titre, sous_titre = _titres_cablage(res, choix, pont, etages, largeur, echelle)

    def pt(points: float) -> float:
        """Distance en unités du schéma correspondant à `points` points typographiques :
        les interlignes suivent la taille des textes, quelle que soit l'échelle du dessin."""
        return points / 72 / echelle

    hauteur_titre = pt(22) + pt(14) * len(sous_titre) + pt(10)

    # Hauteur de chaque ligne d'étages : au-dessus de la ligne de signal, puis 3 unités
    # jusqu'à la masse et la légende des cellules
    hauts = [max(_haut_etage(e) for e in ligne) for ligne in lignes]
    hauteur_lignes = sum(h + 3.0 + 1.6 for h in hauts)

    # Blocs du bas : brochage, nomenclature, notes
    blocs = _blocs_bas(mt.nomenclature(etages, choix), mt.notes_cablage(res, etages, choix), largeur, echelle)
    hauteur = hauteur_titre + hauteur_lignes + _hauteur_blocs(blocs, largeur, pt) + 0.4

    fig = Figure(figsize=(largeur * echelle, hauteur * echelle), facecolor=COULEURS["fond"])
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, largeur)
    ax.set_ylim(-hauteur, 0)
    d = _DessinReel(ax, bool(choix and choix.resistances), bool(choix and choix.condensateurs))

    ax.text(0.5, -pt(22), titre, ha="left", va="baseline", fontsize=12.5, fontweight="bold",
            color=COULEURS["encre"])
    for i, ligne in enumerate(sous_titre):
        ax.text(0.5, -pt(22) - pt(14) * (i + 1), ligne, ha="left", va="baseline", fontsize=9,
                color=COULEURS["encre2"])

    # Lignes d'étages
    y = -hauteur_titre
    for r, (ligne, haut) in enumerate(zip(lignes, hauts)):
        _ligne_cablage(d, ax, ligne, y - haut - 0.3, haut, r, len(lignes), largeur, echelle)
        y -= haut + 3.0 + 1.6

    _dessiner_blocs(ax, blocs, y - 0.1, largeur, pt)
    return fig


def _titres_cablage(res: mt.Resultat, choix: Optional[mt.ChoixSeries], pont: bool, etages: List[mt.Etage],
                    largeur: float, echelle: float) -> Tuple[str, List[str]]:
    """Titre du schéma de câblage, et son sous-titre coupé en lignes."""
    g = res.gabarit
    aops = mt.amplificateurs(etages)
    ordre = 2 * res.n if g.type in ("PM", "CB") else res.n
    titre = f"Schéma de câblage : filtre {mt.NOMS_TYPES[g.type].lower()} de Butterworth d'ordre {ordre}"
    valeurs = (f"valeurs normalisées ({choix.libelle()})" if choix is not None and choix.actif
               else "valeurs calculées, à arrondir aux valeurs disponibles")
    gain = ""
    if res.attenuateur():                                    # passe-bande à cellules de gain unité
        gain = (" · gain 0 dB à f0 (pont diviseur d'entrée)" if pont else
                f" · gain {mt.fmt_nombre(20 * math.log10(res.gain_montage()), 3)} dB à f0 (sans pont diviseur)")
    sous_titre = _texte_coupe(f"{len(etages)} cellule{'s' if len(etages) > 1 else ''}, {len(aops)} "
                              f"{mt.AOP_NOM} ({mt._plage(aops)}), alimentation {mt.ALIMENTATION}{gain} · "
                              f"{valeurs} · numéros de broches en bleu", largeur - 1.0, 9, echelle)
    return titre, sous_titre


LETTRES_RENVOIS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _ligne_cablage(d: "_DessinReel", ax, ligne: List[mt.Etage], ys: float, haut: float, r: int, nb_lignes: int,
                   largeur: float, echelle: float) -> None:
    """Une ligne du schéma de câblage (signal en `ys`) : début (entrée ou renvoi), étages avec
    leur légende, fin (sortie ou renvoi vers la ligne suivante)."""
    ym = ys - 3.0
    x_fin = largeur - 0.9
    # début de ligne : borne d'entrée, ou renvoi depuis la ligne précédente
    if r == 0:
        d.borne(0.9, ys)
        d.borne(0.9, ym)
        d.tension(1.22, ym, ys, "$V_e$")
        d.fil((0.9, ys), (DEBUT_LIGNE, ys))
        x_masse = 0.9
        d.masse(1.6, ym)
        d.noeud(1.6, ym)
    else:
        d.renvoi(0.35, ys, LETTRES_RENVOIS[(r - 1) % 26])
        d.fil((1.4, ys), (DEBUT_LIGNE, ys))
        x_masse = 1.0
        d.masse(x_masse, ym)
    x = DEBUT_LIGNE
    for i, e in enumerate(ligne):
        debut = x
        x = _dessiner_etage(d, e, x, ym)
        legende = _legende_etage(e)
        # légende centrée sous l'étage, ou alignée sur son début si elle est plus large
        if len(legende) <= _caracteres(x - debut, 8.5, echelle):
            ax.text((debut + x) / 2, ym - 0.45, legende, ha="center", va="top", fontsize=8.5,
                    color=COULEURS["encre2"])
        else:
            ax.text(debut, ym - 0.45, legende, ha="left", va="top", fontsize=8.5, color=COULEURS["encre2"])
        if i < len(ligne) - 1:
            d.fil((x, ys), (x + INTERVALLE, ys))
            d.separateur(x + INTERVALLE / 2, ym - 0.55, ys + haut - 0.3)
            x += INTERVALLE
    # fin de ligne : borne de sortie, ou renvoi vers la ligne suivante
    if r == nb_lignes - 1:
        d.fil((x, ys), (x_fin, ys))
        d.borne(x_fin, ys)
        d.borne(x_fin, ym)
        d.tension(x_fin - 0.32, ym, ys, "$V_s$", gauche=True)
        d.fil((x_masse, ym), (x_fin, ym))
    else:
        d.fil((x, ys), (largeur - 1.6, ys))
        d.renvoi(largeur - 1.6, ys, LETTRES_RENVOIS[r % 26])
        d.fil((x_masse, ym), (largeur - 1.0, ym))


# ---- blocs du bas : brochage du µA741, nomenclature, notes ----------------------

def _blocs_bas(nomenclature: List[mt.LigneNomenclature], notes: List[str], largeur: float,
               echelle: float) -> List[tuple]:
    """Prépare les trois blocs : (genre, largeur en unités, contenu)."""
    def pt(points: float) -> float:
        return points / 72 / echelle
    # Les notes se placent à droite de la nomenclature s'il y a la place ; sinon elles passent
    # dessous et prennent toute la largeur (moins de lignes à lire).
    cote_a_cote = pt(215) + pt(285) + pt(250) + 0.5 + 3 * 0.6 <= largeur - 0.3
    largeur_notes = pt(250) if cote_a_cote else max(9.0, largeur - 1.0)
    lignes_notes = []
    for note in notes:
        morceaux = _texte_coupe(note, largeur_notes - 0.4, 8.5, echelle)
        lignes_notes += [("– " if i == 0 else "   ") + m for i, m in enumerate(morceaux)]
    lignes_bom = []
    categorie = None
    for l in nomenclature:
        if l.categorie != categorie:
            categorie = l.categorie
            lignes_bom.append(("titre", categorie))
        reperes = _texte_coupe(l.reperes, pt(175), 8, echelle) or [""]
        lignes_bom.append(("ligne", l.valeur, f"× {l.quantite}", reperes[0]))
        lignes_bom += [("suite", suite) for suite in reperes[1:]]
    # Brochage : 215 points, la largeur de son titre en gras (il ne déborde pas sur la nomenclature)
    return [("brochage", pt(215), None), ("nomenclature", pt(285), lignes_bom),
            ("notes", largeur_notes, lignes_notes)]


def _placer_blocs(blocs: List[tuple], largeur: float) -> List[List[tuple]]:
    """Range les blocs en bandes horizontales de la largeur du schéma."""
    bandes, courante, x = [], [], 0.5
    for bloc in blocs:
        if courante and x + bloc[1] > largeur - 0.3:
            bandes.append(courante)
            courante, x = [], 0.5
        courante.append(bloc)
        x += bloc[1] + 0.6
    if courante:
        bandes.append(courante)
    return bandes


def _hauteur_bloc(bloc: tuple, pt: Callable[[float], float]) -> float:
    """Hauteur d'un bloc (unités) ; pt convertit des points en unités du schéma."""
    genre, _largeur, contenu = bloc
    if genre == "brochage":
        return pt(30) + 3.2 + pt(8)
    if genre == "nomenclature":
        titres = sum(1 for item in contenu if item[0] == "titre")
        return pt(18 + 16 + 14 + 6) + pt(12) * len(contenu) + pt(2) * titres
    return pt(18 + 15 + 6) + pt(11.5) * len(contenu)


def _hauteur_blocs(blocs: List[tuple], largeur: float, pt: Callable[[float], float]) -> float:
    return sum(max(_hauteur_bloc(b, pt) for b in bande) + pt(14) for bande in _placer_blocs(blocs, largeur))


def _dessiner_blocs(ax, blocs: List[tuple], y: float, largeur: float, pt: Callable[[float], float]) -> None:
    """Dessine les blocs du bas à partir de l'ordonnée y (vers le bas). Les interlignes et les
    colonnes de la nomenclature sont donnés en points, comme les textes."""
    titre = dict(fontsize=10.5, fontweight="bold", color=COULEURS["encre"], ha="left", va="baseline")
    discret = dict(fontsize=8, color=COULEURS["discret"], ha="left", va="baseline")
    ax.plot([0.5, largeur - 0.5], [y, y], color=COULEURS["grille"], linewidth=1)
    for bande in _placer_blocs(blocs, largeur):
        x = 0.5
        y_titre = y - pt(18)
        for genre, l, contenu in bande:
            if genre == "brochage":
                ax.text(x, y_titre, f"Brochage du {mt.AOP_NOM} (vu de dessus)", **titre)
                _brochage(ax, x + pt(90), y_titre - pt(12))
            elif genre == "nomenclature":
                ax.text(x, y_titre, "Nomenclature", **titre)
                valeur, quantite, reperes = x + pt(62), x + pt(68), x + pt(102)
                yy = y_titre - pt(16)
                ax.text(valeur, yy, "Valeur", **dict(discret, ha="right"))
                ax.text(quantite, yy, "Qté", **discret)
                ax.text(reperes, yy, "Repères", **discret)
                yy -= pt(14)
                for item in contenu:
                    if item[0] == "titre":
                        yy -= pt(2)
                        ax.text(x, yy, item[1], ha="left", va="baseline", fontsize=8.5,
                                color=COULEURS["discret"], fontstyle="italic")
                    elif item[0] == "ligne":
                        ax.text(valeur, yy, item[1], ha="right", va="baseline", fontsize=8.5,
                                fontweight="bold", color=COULEURS["encre"])
                        ax.text(quantite, yy, item[2], ha="left", va="baseline", fontsize=8.5,
                                color=COULEURS["encre"])
                        ax.text(reperes, yy, item[3], ha="left", va="baseline", fontsize=8,
                                color=COULEURS["encre2"])
                    else:
                        ax.text(reperes, yy, item[1], ha="left", va="baseline", fontsize=8,
                                color=COULEURS["encre2"])
                    yy -= pt(12)
            else:
                ax.text(x, y_titre, "Notes de câblage", **titre)
                yy = y_titre - pt(15)
                for ligne in contenu:
                    ax.text(x, yy, ligne, ha="left", va="baseline", fontsize=8.5, color=COULEURS["encre2"])
                    yy -= pt(11.5)
            x += l + 0.6
        y -= max(_hauteur_bloc(b, pt) for b in bande) + pt(14)


def _brochage(ax, cx: float, y_haut: float) -> None:
    """Boîtier DIP-8 du µA741 vu de dessus, centré en cx, sous l'ordonnée y_haut."""
    from matplotlib.patches import Arc, FancyBboxPatch
    l, h = 1.15, 3.0
    x0, y0 = cx - l / 2, y_haut - h
    ax.add_patch(FancyBboxPatch((x0, y0), l, h, boxstyle="round,pad=0.02", facecolor="#F3F5F8",
                                edgecolor=COULEURS["encre"], linewidth=1.1))
    ax.add_patch(Arc((cx, y_haut), 0.42, 0.42, theta1=180, theta2=360, color=COULEURS["encre"], linewidth=1.1))
    gauche = ["1  Offset", "2  Entrée −", "3  Entrée +", "4  −15 V"]
    droite = ["8  NC", "7  +15 V", "6  Sortie", "5  Offset"]
    for i in range(4):
        y = y_haut - 0.45 - i * 0.7
        ax.plot([x0 - 0.25, x0], [y, y], color=COULEURS["encre"], linewidth=2.4, solid_capstyle="butt")
        ax.plot([x0 + l, x0 + l + 0.25], [y, y], color=COULEURS["encre"], linewidth=2.4, solid_capstyle="butt")
        ax.text(x0 - 0.35, y, gauche[i], ha="right", va="center", fontsize=8.5, color=COULEURS["encre2"])
        ax.text(x0 + l + 0.35, y, droite[i], ha="left", va="center", fontsize=8.5, color=COULEURS["encre2"])


# =============================================================================
# Formules (fonctions de transfert) rendues en images PNG
# =============================================================================

_FORMULES: "OrderedDict[tuple, bytes]" = OrderedDict()    # formules déjà rendues (PNG)

# Résultat encadré des étapes du calcul : (bordure, fond du cadre)
CADRE_RESULTAT = (COULEURS["accent"], "#EAF1FB")


def formule_en_cache(tex: str, taille: float = 14, dpi: float = 100, couleur: str = COULEURS["encre"],
                     fond: str = COULEURS["fond"], cadre: Optional[Tuple[str, str]] = None) -> bool:
    """Vrai si la formule a déjà été rendue avec ces réglages (affichage immédiat)."""
    return (tex, taille, round(dpi, 3), couleur, fond, cadre) in _FORMULES


def formule_png(tex: str, taille: float = 14, dpi: float = 100, couleur: str = COULEURS["encre"],
                fond: str = COULEURS["fond"], cadre: Optional[Tuple[str, str]] = None) -> bytes:
    """Rend une expression mathématique (syntaxe LaTeX de matplotlib) en image PNG.

    cadre = (bordure, remplissage) : la formule est encadrée, comme un résultat sur une copie ;
    `tex` peut alors compter plusieurs lignes, séparées par « \\n », dans le même cadre.
    Les images sont gardées en mémoire : une formule déjà affichée revient instantanément.
    """
    cle = (tex, taille, round(dpi, 3), couleur, fond, cadre)
    if cle in _FORMULES:
        _FORMULES.move_to_end(cle)
        return _FORMULES[cle]
    if cadre is None:
        png = _rendre_formule(tex, taille, dpi, couleur, fond)
    else:
        png = _rendre_encadre(tex, taille, dpi, couleur, fond, cadre)
    _FORMULES[cle] = png
    while len(_FORMULES) > 600:
        _FORMULES.popitem(last=False)
    return png


def _rendre_encadre(tex: str, taille: float, dpi: float, couleur: str, fond: str,
                    cadre: Tuple[str, str]) -> bytes:
    """Une ou plusieurs lignes de formule dans un même cadre (bordure fine, fond teinté)."""
    from PIL import Image, ImageDraw
    bord, remplissage = cadre
    lignes = [Image.open(io.BytesIO(_rendre_formule(l, taille, dpi, couleur, remplissage))).convert("RGB")
              for l in tex.split("\n")]
    e = dpi / 96
    pad_x, pad_y, ecart = round(10 * e), round(6 * e), round(4 * e)
    trait, marge = max(1, round(1.3 * e)), max(1, round(2 * e))
    largeur = max(im.width for im in lignes) + 2 * (pad_x + trait)
    hauteur = sum(im.height for im in lignes) + ecart * (len(lignes) - 1) + 2 * (pad_y + trait)
    image = Image.new("RGB", (largeur + 2 * marge, hauteur + 2 * marge), fond)
    ImageDraw.Draw(image).rectangle([marge, marge, marge + largeur - 1, marge + hauteur - 1],
                                    fill=remplissage, outline=bord, width=trait)
    y = marge + trait + pad_y
    for im in lignes:
        image.paste(im, (marge + trait + pad_x, y))
        y += im.height + ecart
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    return tampon.getvalue()


_ANALYSEUR_MATH = None        # analyseur de formules de matplotlib (rendu direct en pixels)


def _rendre_formule(tex: str, taille: float, dpi: float, couleur: str, fond: str) -> bytes:
    """Rendu proprement dit en PNG : directement en pixels par l'analyseur de formules de
    matplotlib (cinq fois plus rapide qu'une figure) ou, à défaut, dans une petite figure."""
    try:
        return _rendre_formule_direct(tex, taille, dpi, couleur, fond)
    except Exception:                        # version de matplotlib sans ce rendu : figure complète
        pass

    def rendre(expression: str) -> bytes:
        """Rendu de l'expression dans une petite figure, enregistrée en PNG."""
        fig = Figure(figsize=(0.5, 0.5), dpi=dpi, facecolor=fond)
        FigureCanvasAgg(fig)
        fig.text(0, 0, f"${expression}$", fontsize=taille, color=couleur)
        tampon = io.BytesIO()
        fig.savefig(tampon, format="png", dpi=dpi, facecolor=fond,
                    bbox_inches="tight", pad_inches=0.03)
        return tampon.getvalue()
    try:
        return rendre(tex)
    except ValueError:                       # \dfrac ou \text absents des anciennes versions
        return rendre(tex_simplifie(tex))


def _rendre_formule_direct(tex: str, taille: float, dpi: float, couleur: str, fond: str) -> bytes:
    """Formule rendue en niveaux de couverture par l'analyseur « agg » de matplotlib, puis
    teintée (couleur du texte sur le fond) avec une marge de 0,03 pouce, comme une figure."""
    global _ANALYSEUR_MATH
    from matplotlib.colors import to_rgb
    from matplotlib.mathtext import MathTextParser
    from PIL import Image
    if _ANALYSEUR_MATH is None:
        _ANALYSEUR_MATH = MathTextParser("agg")
    police = FontProperties(size=taille)
    try:
        rendu = _ANALYSEUR_MATH.parse(f"${tex}$", dpi=dpi, prop=police)
    except ValueError:                       # \dfrac ou \text absents des anciennes versions
        rendu = _ANALYSEUR_MATH.parse(f"${tex_simplifie(tex)}$", dpi=dpi, prop=police)
    couverture = np.asarray(rendu.image, dtype=np.float32) / 255.0
    if couverture.ndim != 2 or couverture.size == 0:
        raise ValueError("rendu direct indisponible")
    marge = max(1, round(0.03 * dpi))
    h, l = couverture.shape
    a = np.zeros((h + 2 * marge, l + 2 * marge, 1), dtype=np.float32)
    a[marge:marge + h, marge:marge + l, 0] = couverture
    f, c = np.array(to_rgb(fond)) * 255, np.array(to_rgb(couleur)) * 255
    pixels = (f * (1 - a) + c * a).round().astype(np.uint8)
    tampon = io.BytesIO()
    Image.fromarray(pixels, "RGB").save(tampon, format="PNG")
    return tampon.getvalue()


def tex_simplifie(tex: str) -> str:
    r"""Expression sans les commandes récentes de matplotlib : \dfrac -> \frac, \text -> \mathrm."""
    import re
    return re.sub(r"\\text\{([^}]*)\}", lambda m: r"\mathrm{" + m.group(1).replace(" ", r"\ ") + "}",
                  tex.replace(r"\dfrac", r"\frac"))


# Libellé de l'application numérique, devant la formule
TEX_AN = r"\text{A.N. :}\quad "


def tex_prototype(res: mt.Resultat) -> List[str]:
    """Fonction de transfert normalisée en syntaxe mathématique (une ou plusieurs lignes)."""
    facteurs = [f"({f})" for f in mt.facteurs_prototype(res, "tex")]
    if len(facteurs) <= 3:
        return [r"H(p) = \dfrac{1}{" + r"\,".join(facteurs) + "}"]
    lignes = [r"H(p) = \dfrac{1}{B_{%d}(p)}" % res.n]
    for i in range(0, len(facteurs), 3):
        debut = r"B_{%d}(p) = " % res.n if i == 0 else r"\qquad\times\;"
        lignes.append(debut + r"\,".join(facteurs[i:i + 3]))
    return lignes


def tex_transposition(res: mt.Resultat) -> str:
    """Changement de variable de la transposition de fréquence et valeurs numériques."""
    t = res.gabarit.type
    w = mt.fmt_sci(res.w_ref, 4, "tex")
    if t in ("PB", "PH"):
        regle = r"\dfrac{p}{\omega_p}" if t == "PB" else r"\dfrac{\omega_p}{p}"
        return (r"p \;\rightarrow\; " + regle + r",\qquad \omega_p = 2\pi f_p = "
                + w + r"\ \mathrm{rad/s}")
    B = mt.fmt_nombre(res.norm.B, 4).replace(",", "{,}")
    if t == "PM":
        regle = r"\dfrac{1}{B}\left(\dfrac{p}{\omega_0} + \dfrac{\omega_0}{p}\right)"
    else:
        regle = r"\dfrac{B}{\dfrac{p}{\omega_0} + \dfrac{\omega_0}{p}}"
    return (r"p \;\rightarrow\; " + regle + r",\qquad B = " + B
            + r",\quad \omega_0 = 2\pi f_0 = " + w + r"\ \mathrm{rad/s}")


# Forme finale de H(p) : sur une seule ligne tant qu'elle ne dépasse pas cette largeur (en
# cadratins : 44 em, trois facteurs du second ordre environ), sinon numérateur et dénominateur
# écrits à part, deux facteurs par ligne.
LARGEUR_UNE_LIGNE_EM = 44.0


def largeur_formule_em(tex: str) -> float:
    """Largeur d'une formule, en cadratins (multiples de la taille du texte)."""
    try:
        from matplotlib.font_manager import FontProperties
        from matplotlib.mathtext import MathTextParser
        largeur = MathTextParser("path").parse(f"${tex}$", dpi=72, prop=FontProperties(size=10))[0]
        return float(largeur) / 10
    except Exception:                             # analyseur indisponible : estimation grossière
        return len(tex) * 0.3


def tex_fonction_finale(res: mt.Resultat) -> List[str]:
    """Fonction de transfert réelle sous sa forme finale : K·N(p) / produit des dénominateurs
    des cellules, en une ou plusieurs lignes."""
    numerateur, facteurs_num, facteurs_den = mt.fonction_reelle_finale(res, "tex")
    avec_K = abs(res.K - 1) > 1e-9
    k = r"K\," if avec_K else ""
    fin = (r",\qquad K = " + mt.fmt_sci(res.K, 4, "tex")) if avec_K else ""
    num = r"\,".join(f"({f})" for f in facteurs_num) if facteurs_num else numerateur
    den = [f"({f})" for f in facteurs_den]
    une_ligne = r"H(p) = " + k + r"\dfrac{" + num + "}{" + r"\,".join(den) + "}" + fin
    if largeur_formule_em(une_ligne) <= LARGEUR_UNE_LIGNE_EM:
        return [une_ligne]

    def produit(nom: str, facteurs: List[str]) -> List[str]:
        return [(nom + " = " if i == 0 else r"\qquad\times\;") + r"\,".join(facteurs[i:i + 2])
                for i in range(0, len(facteurs), 2)]

    if facteurs_num:
        lignes = [r"H(p) = " + k + r"\dfrac{N(p)}{D(p)}" + fin]
        lignes += produit("N(p)", [f"({f})" for f in facteurs_num])
    else:
        lignes = [r"H(p) = " + k + r"\dfrac{" + num + r"}{D(p)}" + fin]
    return lignes + produit("D(p)", den)


def tex_cellules_reelles(res: mt.Resultat) -> List[Tuple[str, mt.Cellule]]:
    """Fonction de transfert de chaque cellule réelle : Hᵢ(p) = Nᵢ(p)/Dᵢ(p)."""
    lignes = []
    for c in res.cellules:
        num, den = mt.fraction_cellule(c, "tex")
        lignes.append((r"H_{%s}(p) = \dfrac{%s}{%s}" % (mt.nom_indice(c.nom, "tex"), num, den), c))
    return lignes


# =============================================================================
# Étapes du calcul : contenu de l'onglet « Étapes du calcul » (et sa copie en texte)
# =============================================================================

@dataclass
class Bloc:
    """Un élément de l'onglet « Étapes du calcul ».

    genre : "donnees" (gabarit saisi), "etape" (titre, numéroté si numero > 0), "question"
    (sous-partie d'une étape : « a) Coefficient de sélectivité »), "texte" (explication),
    "formule" (rendue en image ; `texte` en est la version simple, pour la copie), "an"
    (application numérique, précédée de « A.N. : »), "resultat" (résultat encadré avec la
    formule qui y mène ; plusieurs lignes séparées par « \n »), "entete" et "ligne" (en-tête
    et ligne d'un tableau : colonnes séparées par des tabulations, alignées sur toutes les
    lignes du même `tableau` dans l'étape), "detail" (précision discrète), "controle"
    (vérification du gabarit, respectée ou non selon `ok`).
    """
    genre: str
    texte: str
    tex: str = ""
    numero: int = 0
    ok: Optional[bool] = None
    tableau: str = ""


def _tex(nombre: str) -> str:
    """Nombre écrit à la française -> syntaxe mathématique (virgule collée, signe moins)."""
    return nombre.replace(",", "{,}").replace("−", "-")


def _tex_si(x: float, unite: str, chiffres: int = 4, compact: bool = False) -> str:
    r"""6,631 nF -> 6{,}631\ \mathrm{nF} ; 10 kΩ -> 10\ \mathrm{k}\Omega."""
    nombre, _, u = mt.fmt_si(x, unite, chiffres, compact).partition(" ")
    if not u:
        return _tex(nombre)
    prefixe = u[:len(u) - len(unite)]
    p = r"\mu" if prefixe == "µ" else (r"\mathrm{%s}" % prefixe if prefixe else "")
    v = r"\Omega" if unite == "Ω" else r"\mathrm{%s}" % unite
    return _tex(nombre) + r"\ " + p + v


def _angle(k: int, n: int) -> Tuple[str, str, str]:
    """Angle (2k − 1)π/2n : fraction réduite (texte et syntaxe mathématique) et degrés."""
    a, b = 2 * k - 1, 2 * n
    d = math.gcd(a, b)
    a, b = a // d, b // d
    texte = ("π" if a == 1 else f"{a}π") + ("" if b == 1 else f"/{b}")
    tex = r"\dfrac{%s\pi}{%d}" % ("" if a == 1 else a, b) if b != 1 else ("%s\\pi" % ("" if a == 1 else a))
    degres = 180 * (2 * k - 1) / (2 * n)
    return texte, tex, mt.fmt_compact(degres, 5) + "°"


def _approche(x: float, chiffres: int = 4) -> bool:
    """Vrai si x écrit avec `chiffres` chiffres significatifs est arrondi (on écrit alors ≈)."""
    if x == 0 or not math.isfinite(x):
        return False
    decimales = chiffres - 1 - math.floor(math.log10(abs(x)))
    return abs(round(x, decimales) - x) > 1e-9 * abs(x)


def _approche_dec(x: float, decimales: int = 4) -> bool:
    """Vrai si x écrit avec `decimales` décimales est arrondi."""
    return abs(round(x, decimales) - x) > 1e-12 * max(1.0, abs(x))


def _nom_tex(nom: str) -> str:
    """Repère d'un composant en syntaxe mathématique : « R12 » -> R_{12}."""
    return f"{nom[0]}_{{{nom[1:]}}}" if len(nom) > 1 else nom


class _Redaction:
    """Rédaction des étapes du calcul : les blocs, dans l'ordre, et de quoi écrire chaque
    résultat comme sur une copie (formule littérale, application numérique, résultat encadré).
    Les nombres sont donnés en couples (texte simple, syntaxe mathématique)."""

    def __init__(self, res: mt.Resultat):
        self.res = res
        self.blocs: List[Bloc] = []
        # Fréquences dans les applications numériques : en hertz (comme on l'écrit à la main)
        # tant qu'elles restent lisibles, sinon avec un préfixe (kHz, MHz).
        g = res.gabarit
        self.en_hertz = max(getattr(g, nom) for nom in mt.FREQUENCES[g.type]) < 1e5

    # ----- blocs ------------------------------------------------------------------------
    def etape(self, numero: int, titre: str) -> None:
        self.blocs.append(Bloc("etape", titre, numero=numero))

    def question(self, titre: str) -> None:
        self.blocs.append(Bloc("question", titre))

    def texte(self, phrase: str) -> None:
        self.blocs.append(Bloc("texte", phrase))

    def formule(self, tex: str, simple: str) -> None:
        self.blocs.append(Bloc("formule", simple, tex))

    def encadre(self, tex: str, simple: str) -> None:
        """Résultat encadré ; plusieurs lignes séparées par « \\n » tiennent dans le même cadre."""
        self.blocs.append(Bloc("resultat", simple, tex))

    def detail(self, phrase: str) -> None:
        self.blocs.append(Bloc("detail", phrase))

    def an(self, simple: str, tex: str) -> None:
        """Application numérique écrite telle quelle (sans formule littérale ni cadre)."""
        self.blocs.append(Bloc("an", simple, tex))

    def calcul(self, symbole: Tuple[str, str], litterale: Tuple[str, str], numerique: Optional[Tuple[str, str]],
               valeur: Tuple[str, str], approche: bool = True, retenu: bool = True) -> None:
        """Un résultat rédigé comme sur une copie. Chaque argument est un couple (texte simple,
        syntaxe mathématique) : la formule littérale, l'application numérique, puis le résultat
        encadré avec sa formule. retenu=False : valeur intermédiaire, écrite au bout de l'A.N.
        sans cadre."""
        (s, s_tex), (l, l_tex), (v, v_tex) = symbole, litterale, valeur
        egal, egal_tex = ("≈", r"\approx") if approche else ("=", "=")
        self.formule(f"{s_tex} = {l_tex}", f"{s} = {l}")
        if numerique is not None:
            n_, n_tex = numerique
            fin, fin_tex = ("", "") if retenu else (f" {egal} {v}", f" {egal_tex} {v_tex}")
            self.an(f"{s} = {n_}{fin}", f"{s_tex} = {n_tex}{fin_tex}")
        if retenu:
            self.encadre(f"{s_tex} = {l_tex} {egal_tex} {v_tex}", f"{s} = {l} {egal} {v}")

    def tableau_composants(self, etages: List[mt.Etage], nom: str) -> None:
        """Tableau récapitulatif : une ligne par cellule, ses résistances puis ses condensateurs
        (repères du montage réel)."""
        self.blocs.append(Bloc("entete", "Cellule\tMontage\tRésistances\tCondensateurs", tableau=nom))
        for e in etages:
            self.blocs.append(Bloc("ligne", "\t".join([e.montage.cellule.nom, e.montage.libelle,
                                                        e.liste("R") or "—", e.liste("C") or "—"]), tableau=nom))

    def controles(self, points: List[mt.PointControle]) -> None:
        """Gain obtenu à chaque fréquence limite du gabarit, comparé à sa limite."""
        for p_ in points:
            signe = "≥" if p_.passante else "≤"
            self.blocs.append(Bloc("controle", f"G({p_.nom}) = {mt.fmt_nombre(p_.G, 4)} dB  {signe}  "
                                               f"{mt.fmt_compact(p_.limite)} dB", ok=p_.ok))

    # ----- nombres : (texte simple, syntaxe mathématique) --------------------------------
    @staticmethod
    def nombre(x: float, chiffres: int = 4) -> Tuple[str, str]:
        s = mt.fmt_nombre(x, chiffres)
        return s, _tex(s)

    @staticmethod
    def decimales(x: float) -> Tuple[str, str]:
        s = mt.fmt_decimales(x)
        return s, _tex(s)

    @staticmethod
    def si(x: float, unite: str) -> Tuple[str, str]:
        return mt.fmt_si(x, unite), _tex_si(x, unite)

    @staticmethod
    def pulsation(w: float) -> Tuple[str, str]:
        return mt.fmt_sci(w, 4) + " rad/s", mt.fmt_sci(w, 4, "tex") + r"\ \mathrm{rad/s}"

    # Valeurs reprises dans une application numérique : 6 chiffres significatifs, pour que
    # le calcul refait à la main tombe sur le résultat encadré (arrondi, lui, à 4 chiffres).
    @staticmethod
    def precis(x: float) -> Tuple[str, str]:
        s = mt.fmt_compact(x, 6)
        return s, _tex(s)

    @staticmethod
    def precis_si(x: float, unite: str) -> Tuple[str, str]:
        return mt.fmt_si(x, unite, 6, compact=True), _tex_si(x, unite, 6, compact=True)

    @staticmethod
    def precis_puls(w: float) -> Tuple[str, str]:
        return mt.fmt_sci(w, 6) + " rad/s", mt.fmt_sci(w, 6, "tex") + r"\ \mathrm{rad/s}"

    def hz(self, x: float) -> Tuple[str, str]:
        """(texte, tex) d'une fréquence saisie."""
        if self.en_hertz:
            s = mt.fmt_compact(x, 6)
            return s, _tex(s)
        return mt.fmt_si(x, "Hz", 6, compact=True), _tex_si(x, "Hz", 6, compact=True)


def etapes_du_calcul(res: mt.Resultat, choix: Optional[mt.ChoixSeries] = None, pont: bool = False) -> List[Bloc]:
    """Les six étapes de la synthèse, rédigées comme une copie de devoir : pour chaque
    résultat, la formule littérale, l'application numérique (A.N.), puis le résultat encadré
    avec la formule qui y mène.

    Étape 1  normalisation du gabarit (k, et f0, B pour les filtres de bande)
    Étape 2  approximation de Butterworth et ondulation ε
    Étape 3  ordre minimal n
    Étape 4  fonction de transfert normalisée (coefficients m du polynôme de Butterworth)
    Étape 5  fonction de transfert réelle : pulsation de référence, transposition de
             fréquence, forme finale, puis chaque cellule
    Étape 6  valeurs des composants : valeurs de référence, puis m, q et les composants de
             chaque cellule (et le pont diviseur du passe-bande), avec leur tableau récapitulatif
    puis, si une série est choisie, la normalisation des valeurs (paragraphe à part), et la
    vérification du gabarit.
    """
    r = _Redaction(res)
    _introduction(r)
    f0 = _etape1_normalisation(r)
    _etape2_butterworth(r)
    _etape3_ordre(r)
    _etape4_prototype(r)
    w, w_tex = _etape5_fonction_reelle(r, f0)
    _etape6_composants(r, choix, pont, w, w_tex)
    _verification(r, choix)
    return r.blocs


def _introduction(r: _Redaction) -> None:
    """Données (le gabarit) et ce qu'on cherche."""
    g = r.res.gabarit
    t = g.type
    r.blocs.append(Bloc("donnees", f"{mt.NOMS_TYPES[t]} : {mt.resume_gabarit(g)}"))
    r.texte("On cherche l'ordre minimal du filtre et sa fonction de transfert"
            + ("." if t == "CB" else ", puis les valeurs des composants de ses cellules."))
    r.detail("Les applications numériques gardent 6 chiffres significatifs ; les résultats encadrés sont "
             "arrondis (4 chiffres significatifs, 4 décimales pour les coefficients m et q).")


def _etape1_normalisation(r: _Redaction) -> Tuple[str, str]:
    """Étape 1 : k et 1/k, précédés de f0 et B pour un filtre de bande. Renvoie f0 tel qu'il
    s'écrit dans les applications numériques (vide pour un passe-bas ou un passe-haut)."""
    r.etape(1, "Normalisation du gabarit")
    if r.res.gabarit.type in ("PB", "PH"):
        _normalisation_pb_ph(r)
        f0 = ("", "")
    else:
        f0 = _normalisation_bande(r)
    r.detail("Gabarit réduit (Bode normalisé) : G ≥ Gp jusqu'à Ω = 1, G ≤ Ga à partir de Ω = 1/k.")
    return f0


def _normalisation_pb_ph(r: _Redaction) -> None:
    """Étape 1, passe-bas ou passe-haut : k = fp/fa (ou fa/fp) et 1/k."""
    g, nm = r.res.gabarit, r.res.norm
    t = g.type
    k_val, inv_val = r.nombre(nm.k), r.nombre(1 / nm.k)
    haut, bas = ("fp", "fa") if t == "PB" else ("fa", "fp")
    (a, a_tex), (b, b_tex) = r.hz(getattr(g, haut)), r.hz(getattr(g, bas))
    reduite = "Ω = ω/ωp" if t == "PB" else "Ω = ωp/ω, qui inverse l'axe des fréquences"
    r.texte(f"On rapporte la pulsation à ωp = 2π·fp ({reduite}) : la bande passante s'arrête en "
            "Ω = 1 et la bande atténuée commence en Ω = 1/k.")
    r.question("a) Coefficient de sélectivité")
    r.calcul(("k", "k"), (f"{haut}/{bas}", r"\dfrac{f_{%s}}{f_{%s}}" % (haut[1], bas[1])),
             (f"{a}/{b}", r"\dfrac{%s}{%s}" % (a_tex, b_tex)), k_val, _approche(nm.k))
    r.question("b) Début réduit de la bande atténuée")
    r.calcul(("1/k", r"\dfrac{1}{k}"), (f"{bas}/{haut}", r"\dfrac{f_{%s}}{f_{%s}}" % (bas[1], haut[1])),
             (f"{b}/{a}", r"\dfrac{%s}{%s}" % (b_tex, a_tex)), inv_val, _approche(1 / nm.k))


def _normalisation_bande(r: _Redaction) -> Tuple[str, str]:
    """Étape 1, passe-bande ou coupe-bande : f0, B, puis la sélectivité. Renvoie f0 tel qu'il
    s'écrit dans les applications numériques."""
    g, nm = r.res.gabarit, r.res.norm
    fp_moins, fp_plus = r.hz(g.fp_moins), r.hz(g.fp_plus)
    (fpm, fpm_t), (fpp, fpp_t) = fp_moins, fp_plus
    r.texte("On centre le gabarit sur f0, moyenne géométrique des limites de la bande passante, et on "
            "mesure sa largeur par la bande relative B.")
    r.question("a) Fréquence centrale")
    r.calcul(("f0", "f_0"), ("√(fp+·fp−)", r"\sqrt{f_{p+}\,f_{p-}}"),
             (f"√({fpp} × {fpm})", r"\sqrt{%s \times %s}" % (fpp_t, fpm_t)), r.si(nm.f_ref, "Hz"),
             _approche(nm.f_ref))
    f0 = r.precis(nm.f_ref) if r.en_hertz else r.precis_si(nm.f_ref, "Hz")
    r.question("b) Largeur de bande relative")
    r.calcul(("B", "B"), ("(fp+ − fp−)/f0", r"\dfrac{f_{p+} - f_{p-}}{f_0}"),
             (f"({fpp} − {fpm})/{f0[0]}", r"\dfrac{%s - %s}{%s}" % (fpp_t, fpm_t, f0[1])), r.nombre(nm.B),
             _approche(nm.B))
    if nm.symetrique:
        _selectivite_symetrique(r, fp_moins, fp_plus)
    else:
        _selectivite_asymetrique(r, f0)
    return f0


def _rapport_largeurs(dessus, dessous) -> Tuple[Tuple[str, str], Tuple[str, str]]:
    """Quotient de deux largeurs de bande : formule littérale et application numérique."""
    (l1, l1_t), (n1, n1_t) = dessus
    (l2, l2_t), (n2, n2_t) = dessous
    return ((f"{l1}/{l2}", r"\dfrac{%s}{%s}" % (l1_t, l2_t)),
            (f"{n1}/{n2}", r"\dfrac{%s}{%s}" % (n1_t, n2_t)))


def _selectivite_symetrique(r: _Redaction, fp_moins: Tuple[str, str], fp_plus: Tuple[str, str]) -> None:
    """Étape 1, gabarit de bande symétrique : k compare les largeurs des deux bandes."""
    g, nm = r.res.gabarit, r.res.norm
    t = g.type
    (fpm, fpm_t), (fpp, fpp_t) = fp_moins, fp_plus
    (fam, fam_t), (fap, fap_t) = r.hz(g.fa_moins), r.hz(g.fa_plus)
    passe = (("(fp+ − fp−)", r"f_{p+} - f_{p-}"), (f"({fpp} − {fpm})", f"{fpp_t} - {fpm_t}"))
    attenue = (("(fa+ − fa−)", r"f_{a+} - f_{a-}"), (f"({fap} − {fam})", f"{fap_t} - {fam_t}"))
    haut_, bas_ = (passe, attenue) if t == "PM" else (attenue, passe)
    r.question("c) Coefficient de sélectivité")
    r.texte("Il compare la largeur de la bande passante à celle de la bande atténuée :" if t == "PM" else
            "Il compare la largeur de la bande rejetée à celle de la bande passante :")
    r.calcul(("k", "k"), *_rapport_largeurs(haut_, bas_), r.nombre(nm.k), _approche(nm.k))
    r.question("d) Début réduit de la bande atténuée")
    r.calcul(("1/k", r"\dfrac{1}{k}"), *_rapport_largeurs(bas_, haut_), r.nombre(1 / nm.k), _approche(1 / nm.k))


def _selectivite_asymetrique(r: _Redaction, f0_an: Tuple[str, str]) -> None:
    """Étape 1, gabarit de bande non symétrique : pulsation réduite en fa− et en fa+, puis k
    d'après la plus contraignante."""
    g, nm = r.res.gabarit, r.res.norm
    t = g.type
    f0_n, f0_t = f0_an
    (fam, fam_t), (fap, fap_t) = r.hz(g.fa_moins), r.hz(g.fa_plus)
    B_an = r.precis(nm.B)
    r.texte(f"Le gabarit n'est pas symétrique : √(fa+·fa−) = {mt.fmt_si(nm.f0_attenuation, 'Hz')} diffère "
            "de f0. On calcule la pulsation réduite atteinte en fa− et en fa+, et on garde la plus "
            "contraignante.")
    f0, B = nm.f_ref, nm.B
    B_t = B_an[1]
    if t == "PM":
        om_m = (f0 / g.fa_moins - g.fa_moins / f0) / B
        om_p = (g.fa_plus / f0 - f0 / g.fa_plus) / B
        lit_m = ("(f0/fa− − fa−/f0)/B", r"\dfrac{1}{B}\left(\dfrac{f_0}{f_{a-}} - \dfrac{f_{a-}}{f_0}\right)")
        num_m = (f"({f0_n}/{fam} − {fam}/{f0_n})/{B_an[0]}",
                 r"\dfrac{1}{%s}\left(\dfrac{%s}{%s} - \dfrac{%s}{%s}\right)" % (B_t, f0_t, fam_t, fam_t, f0_t))
        lit_p = ("(fa+/f0 − f0/fa+)/B", r"\dfrac{1}{B}\left(\dfrac{f_{a+}}{f_0} - \dfrac{f_0}{f_{a+}}\right)")
        num_p = (f"({fap}/{f0_n} − {f0_n}/{fap})/{B_an[0]}",
                 r"\dfrac{1}{%s}\left(\dfrac{%s}{%s} - \dfrac{%s}{%s}\right)" % (B_t, fap_t, f0_t, f0_t, fap_t))
    else:
        om_m = B / (f0 / g.fa_moins - g.fa_moins / f0)
        om_p = B / (g.fa_plus / f0 - f0 / g.fa_plus)
        lit_m = ("B/(f0/fa− − fa−/f0)", r"\dfrac{B}{\dfrac{f_0}{f_{a-}} - \dfrac{f_{a-}}{f_0}}")
        num_m = (f"{B_an[0]}/({f0_n}/{fam} − {fam}/{f0_n})",
                 r"\dfrac{%s}{\dfrac{%s}{%s} - \dfrac{%s}{%s}}" % (B_t, f0_t, fam_t, fam_t, f0_t))
        lit_p = ("B/(fa+/f0 − f0/fa+)", r"\dfrac{B}{\dfrac{f_{a+}}{f_0} - \dfrac{f_0}{f_{a+}}}")
        num_p = (f"{B_an[0]}/({fap}/{f0_n} − {f0_n}/{fap})",
                 r"\dfrac{%s}{\dfrac{%s}{%s} - \dfrac{%s}{%s}}" % (B_t, fap_t, f0_t, f0_t, fap_t))
    r.question("c) Pulsations réduites aux limites de la bande atténuée")
    r.calcul(("Ω(fa−)", r"\Omega(f_{a-})"), lit_m, num_m, r.nombre(om_m), _approche(om_m))
    r.calcul(("Ω(fa+)", r"\Omega(f_{a+})"), lit_p, num_p, r.nombre(om_p), _approche(om_p))
    mini = min(om_m, om_p)
    inv_val = r.nombre(1 / nm.k)
    r.question("d) Coefficient de sélectivité")
    r.calcul(("k", "k"), ("1/min(Ω(fa−), Ω(fa+))",
                          r"\dfrac{1}{\min\left(\Omega(f_{a-}),\,\Omega(f_{a+})\right)}"),
             (f"1/{r.precis(mini)[0]}", r"\dfrac{1}{%s}" % r.precis(mini)[1]), r.nombre(nm.k), _approche(nm.k))
    r.encadre(r"\dfrac{1}{k} = \min\left(\Omega(f_{a-}),\,\Omega(f_{a+})\right) %s %s"
              % (r"\approx" if _approche(mini) else "=", inv_val[1]),
              f"1/k = min(Ω(fa−), Ω(fa+)) {'≈' if _approche(mini) else '='} {inv_val[0]}")


def _etape2_butterworth(r: _Redaction) -> None:
    """Étape 2 : gain du prototype de Butterworth et ondulation ε."""
    g, res = r.res.gabarit, r.res
    r.etape(2, "Approximation de Butterworth")
    r.texte("Le gain du prototype passe-bas d'ordre n est le plus plat possible dans la bande passante :")
    r.formule(r"|H(j\Omega)|^2 = \dfrac{1}{1 + \varepsilon^2\,\Omega^{2n}},\qquad "
              r"G(\Omega) = -10\,\log\left(1 + \varepsilon^2\,\Omega^{2n}\right)",
              "|H(jΩ)|² = 1 / (1 + ε²·Ω²ⁿ)   G(Ω) = −10·log(1 + ε²·Ω²ⁿ)")
    gp10 = mt.fmt_compact(-g.Gp / 10)
    eps_calcule = math.sqrt(10 ** (-g.Gp / 10) - 1)
    r.texte("En Ω = 1, le gain doit valoir Gp : 1 + ε² = 10^(−Gp/10), ce qui fixe l'ondulation ε :")
    lit_eps = ("√(10^(−Gp/10) − 1)", r"\sqrt{10^{-G_p/10} - 1}")
    num_eps = (f"√(10^{gp10} − 1)", r"\sqrt{10^{%s} - 1}" % _tex(gp10))
    if res.eps_convention:
        r.calcul(("ε", r"\varepsilon"), lit_eps, num_eps, r.nombre(eps_calcule), _approche(eps_calcule),
                 retenu=False)
        r.texte("Gp = −3 dB donne ε ≈ 1 : on prend ε = 1, et la coupure à −3 dB du prototype tombe "
                "exactement en Ω = 1.")
        r.encadre(r"\varepsilon = 1", "ε = 1")
    else:
        r.calcul(("ε", r"\varepsilon"), lit_eps, num_eps, r.nombre(eps_calcule), _approche(eps_calcule))


def _etape3_ordre(r: _Redaction) -> None:
    """Étape 3 : ordre minimal n (et N = 2n pour un filtre de bande, Ωc si ε ≠ 1)."""
    res = r.res
    g, nm = res.gabarit, res.norm
    t = g.type
    r.etape(3, "Ordre minimal")
    r.texte("Le gabarit impose aussi G(1/k) ≤ Ga, soit 1 + ε²·(1/k)²ⁿ ≥ 10^(−Ga/10). En prenant le "
            "logarithme, avec ε² = 10^(−Gp/10) − 1, l'ordre n doit vérifier :")
    r.formule(r"n \geq \dfrac{\log\left(10^{-G_a/10} - 1\right) - \log\left(10^{-G_p/10} - 1\right)}"
              r"{2\,\log(1/k)}",
              "n ≥ [log(10^(−Ga/10) − 1) − log(10^(−Gp/10) − 1)] / [2·log(1/k)]")
    gp10 = mt.fmt_compact(-g.Gp / 10)
    ga10 = mt.fmt_compact(-g.Ga / 10)
    numerateur = math.log10(10 ** (-g.Ga / 10) - 1) - math.log10(10 ** (-g.Gp / 10) - 1)
    denominateur = 2 * math.log10(1 / nm.k)
    (num, num_t), (den, den_t), (nex, nex_t) = r.precis(numerateur), r.precis(denominateur), r.nombre(res.n_exact)
    inv_an = r.precis(1 / nm.k)
    r.an(f"n ≥ [log(10^{ga10} − 1) − log(10^{gp10} − 1)] / [2·log({inv_an[0]})] = {num}/{den}",
         r"n \geq \dfrac{\log\left(10^{%s} - 1\right) - \log\left(10^{%s} - 1\right)}{2\,\log(%s)}"
         r" = \dfrac{%s}{%s}" % (_tex(ga10), _tex(gp10), inv_an[1], num_t, den_t))
    r.texte(f"n est l'entier immédiatement supérieur à {nex} :")
    r.encadre(r"n \geq %s \;\Rightarrow\; n = %d" % (nex_t, res.n), f"n ≥ {nex}  ⇒  n = {res.n}")
    if t in ("PM", "CB"):
        r.texte("La transposition donne deux pôles pour chaque pôle du prototype : le filtre réel est d'ordre N = 2n.")
        r.encadre(r"N = 2n = %d" % (2 * res.n), f"N = 2n = {2 * res.n}")
    if not res.eps_convention:
        r.texte("Avec ε ≠ 1, la coupure à −3 dB du prototype n'est plus en Ω = 1 mais en :")
        eps_v = r.precis(res.eps)
        r.calcul(("Ωc", r"\Omega_c"), ("ε^(−1/n)", r"\varepsilon^{-1/n}"),
                 (f"{eps_v[0]}^(−1/{res.n})", r"%s^{-1/%d}" % (eps_v[1], res.n)), r.nombre(res.omega_c),
                 _approche(res.omega_c))


def _etape4_prototype(r: _Redaction) -> None:
    """Étape 4 : polynôme de Butterworth, coefficient m de chaque cellule, fonction normalisée."""
    res = r.res
    r.etape(4, "Fonction de transfert normalisée")
    r.texte("Le dénominateur est le polynôme de Butterworth Bn(p) : un facteur p² + 2m·p + 1 par paire de "
            "pôles, et le facteur (p + 1) si n est impair, avec :")
    r.formule(r"B_n(p) = (p+1)\;\prod_k\left(p^2 + 2\,m_k\,p + 1\right),\qquad "
              r"m_k = \sin\dfrac{(2k-1)\,\pi}{2n}",
              "Bn(p) = (p + 1)·Π(p² + 2mₖ·p + 1)   avec mₖ = sin((2k − 1)π/2n)")
    debut_k = (res.n + 1) // 2 + 1
    valeurs_k = list(range(debut_k, res.n + 1))
    if valeurs_k:
        r.texte(f"Pour n = {res.n}, k prend les valeurs entières telles que (n + 1)/2 < k < n + 1/2 : "
                f"k = {', '.join(map(str, valeurs_k))}.")
    for i, c in enumerate(res.prototype):
        if c.ordre == 2:
            _coefficient_m(r, c, debut_k + i)
        else:
            r.texte("n est impair : le polynôme compte aussi le facteur du premier ordre (p + 1).")
    if not res.eps_convention:
        r.detail(f"Avec Ωc = {mt.fmt_nombre(res.omega_c)}, p est remplacé par p/Ωc dans chaque facteur.")
    r.texte("D'où la fonction de transfert normalisée :")
    facteurs = mt.facteurs_prototype(res)
    simple = "H(p) = 1 / " + ("[" + "·".join(f"({x})" for x in facteurs) + "]" if len(facteurs) > 1
                              else f"({facteurs[0]})")
    r.encadre("\n".join(tex_prototype(res)), simple)


def _coefficient_m(r: _Redaction, c: mt.Cellule, kk: int) -> None:
    """Étape 4, une cellule du second ordre : mₖ = sin((2k − 1)π/2n) et son facteur."""
    n = r.res.n
    angle, angle_tex, degres = _angle(kk, n)
    degres_tex = _tex(degres[:-1]) + r"^{\circ}"
    m = math.sin(math.pi * (2 * kk - 1) / (2 * n))
    (m_txt, m_t), (dm, dm_t) = r.decimales(m), r.decimales(2 * m)
    egal, egal_tex = ("≈", r"\approx") if _approche_dec(m) else ("=", "=")
    r.question(f"Cellule {c.nom} (k = {kk})")
    r.an(f"m{c.nom} = sin((2×{kk} − 1)π/(2×{n})) = sin({angle}) = sin {degres}",
         r"m_{%s} = \sin\dfrac{(2\times %d - 1)\,\pi}{2\times %d} = \sin %s = \sin %s"
         % (c.nom, kk, n, angle_tex, degres_tex))
    r.encadre(r"m_{%s} = \sin %s %s %s \;\Rightarrow\; p^2 + %s\,p + 1" % (c.nom, angle_tex, egal_tex, m_t, dm_t),
              f"m{c.nom} = sin({angle}) {egal} {m_txt}  ⇒  p² + {dm}·p + 1")


def _etape5_fonction_reelle(r: _Redaction, f0: Tuple[str, str]) -> Tuple[str, str]:
    """Étape 5 : pulsation de référence, transposition, fonction réelle puis chaque cellule.
    Renvoie le nom de la pulsation de référence (ωp ou ω0), en texte et en syntaxe mathématique."""
    res = r.res
    g = res.gabarit
    t = g.type
    r.etape(5, "Fonction de transfert réelle")
    if t in ("PB", "PH"):
        w, w_tex, f_nom, f_tex = "ωp", r"\omega_p", "fp", "f_p"
        f_val = r.hz(g.fp)
    else:
        w, w_tex, f_nom, f_tex = "ω0", r"\omega_0", "f0", "f_0"
        f_val = f0
    w_val = r.pulsation(res.w_ref)
    r.question("a) Pulsation de référence")
    r.calcul((w, w_tex), (f"2π·{f_nom}", r"2\pi\,%s" % f_tex), (f"2π × {f_val[0]}", r"2\pi \times %s" % f_val[1]),
             w_val, _approche(res.w_ref))
    r.question("b) Transposition de fréquence")
    regle = {"PB": ("p → p/ωp", r"p \;\rightarrow\; \dfrac{p}{\omega_p}"),
             "PH": ("p → ωp/p", r"p \;\rightarrow\; \dfrac{\omega_p}{p}"),
             "PM": ("p → (1/B)·(p/ω0 + ω0/p)",
                    r"p \;\rightarrow\; \dfrac{1}{B}\left(\dfrac{p}{\omega_0} + \dfrac{\omega_0}{p}\right)"),
             "CB": ("p → B/(p/ω0 + ω0/p)", r"p \;\rightarrow\; \dfrac{B}{\dfrac{p}{\omega_0} + \dfrac{\omega_0}{p}}")}[t]
    r.texte("Pour revenir au filtre réel, on remplace p dans la fonction normalisée :")
    r.formule(regle[1], regle[0])
    if t == "CB":
        r.detail("Pour le coupe-bande, B = (fp+ − fp−)/f0 : c'est cette largeur qui place le gain Gp "
                 "exactement en fp− et fp+.")
    r.question("c) Fonction de transfert réelle")
    if t == "PM":
        r.texte("En unités SI (p en rad/s), la fonction de transfert réelle est le produit des cellules ; "
                "K ramène son gain à 0 dB en f0 :")
    else:
        r.texte("En unités SI (p en rad/s), la fonction de transfert réelle s'écrit :")
    r.encadre("\n".join(tex_fonction_finale(res)), mt.texte_fonction_finale(res))
    r.question("d) Fonction de transfert de chaque cellule")
    if t in ("PB", "PH"):
        r.texte("Chaque facteur correspond à une cellule du montage, qui reprend un facteur de l'étape 4 :")
    else:
        r.texte("Chaque facteur correspond à une cellule du montage" + (", de gain unité :" if t == "PM" else " :"))
    for tex, c in tex_cellules_reelles(res):
        num_c, den_c = mt.fraction_cellule(c)
        nom = f"H{mt.nom_indice(c.nom)}(p)"
        r.encadre(tex, f"{nom} = ({num_c}) / ({den_c})" if "+" in num_c else f"{nom} = {num_c} / ({den_c})")
        r.detail(_description_cellule(c))
    return w, w_tex


def _etape6_composants(r: _Redaction, choix: Optional[mt.ChoixSeries], pont: bool, w: str, w_tex: str) -> None:
    """Étape 6 : valeurs de référence, composants de chaque cellule, pont diviseur, tableau
    récapitulatif ; puis la normalisation des valeurs si une série est choisie."""
    res = r.res
    t = res.gabarit.type
    r.etape(6, "Valeurs des composants")
    if not res.montages:
        r.texte("Le coupe-bande n'est pas réalisable avec la structure de Sallen & Key : il n'y a pas de "
                "composants à calculer.")
        return
    r.texte(f"Cellules de Sallen & Key à gain unité (K = 1). Les valeurs de référence sont liées par "
            f"R0·C0·{w} = 1.")
    r.question("a) Valeurs de référence")
    _valeurs_reference(r, w, w_tex)
    # Repères du montage réel : R1, R2, R3… et C1, C2, C3… d'un bout à l'autre ; dans chaque
    # cellule, éléments en série, puis contre-réaction (en haut), puis masse (en bas)
    etages = mt.etages_reels(res, None, pont)
    porteur = next((e for e in etages if e.pont), None)       # cellule qui porte le pont diviseur
    r.question("b) Composants de chaque cellule")
    r.texte("Les composants sont numérotés d'un bout à l'autre du montage (R1, R2, R3… et C1, C2, C3…) : "
            "dans chaque cellule, d'abord les éléments en série dans l'ordre du signal, puis la "
            "contre-réaction (en haut du schéma), puis l'élément vers la masse (en bas)."
            + (f" Les résistances du pont diviseur d'entrée suivent la même règle (cellule "
               f"{porteur.montage.cellule.nom} : {porteur.designation('R1')} côté entrée, "
               f"{porteur.designation('Rb')} vers la masse) ; leurs valeurs sont calculées plus bas."
               if porteur else "")
            + " Chaque cellule se déduit de ses coefficients m et q, tirés de sa pulsation propre ωn "
              "et de son facteur de qualité Q (étape 5).")
    for e in etages:
        _etapes_cellule(r, e, w, w_tex)
    if t == "PM" and res.attenuateur():
        _pont_diviseur(r, pont, porteur)
    r.texte("Tableau récapitulatif des valeurs calculées" + (", pont diviseur compris" if pont and porteur
                                                              else "") + " :")
    r.tableau_composants(etages, "calculees")
    r.detail("Schéma de chaque cellule : onglet Composants. Montage complet avec les µA741 : onglet Câblage.")
    if choix is not None and choix.actif:
        _normalisation_series(r, choix, pont)


def _valeurs_reference(r: _Redaction, w: str, w_tex: str) -> None:
    """Étape 6 a) : C0 d'après R0 (cellules passe-bas), R0 d'après C0 (cellules passe-haut)."""
    res = r.res
    t = res.gabarit.type
    if res.ref_pb:
        R0, C0 = res.ref_pb
        if t == "PM":
            r.texte("Cellules passe-bas : R0 est imposée.")
        r0, w_an = r.precis_si(R0, "Ω"), r.precis_puls(res.w_ref)
        r.calcul(("C0", "C_0"), (f"1/(R0·{w})", r"\dfrac{1}{R_0\,%s}" % w_tex),
                 (f"1/({r0[0]} × {w_an[0]})", r"\dfrac{1}{%s \times %s}" % (r0[1], w_an[1])),
                 r.si(C0, "F"), _approche(C0))
    if res.ref_ph:
        R0, C0 = res.ref_ph
        if t == "PM":
            r.texte("Cellules passe-haut : C0 est imposé.")
        c0, w_an = r.precis_si(C0, "F"), r.precis_puls(res.w_ref)
        r.calcul(("R0", "R_0"), (f"1/(C0·{w})", r"\dfrac{1}{C_0\,%s}" % w_tex),
                 (f"1/({c0[0]} × {w_an[0]})", r"\dfrac{1}{%s \times %s}" % (c0[1], w_an[1])),
                 r.si(R0, "Ω"), _approche(R0))


def _pont_diviseur(r: _Redaction, pont: bool, porteur: Optional[mt.Etage]) -> None:
    """Étape 6 c), passe-bande : gain du montage à f0 et, avec l'option, le pont diviseur
    d'entrée qui le ramène à 0 dB."""
    res = r.res
    nom_cellule, alpha, Ra, Rb = res.attenuateur()
    gain = res.gain_montage()
    r.question("c) Gain du montage et pont diviseur d'entrée")
    r.texte(f"Chaque cellule a un gain de 1 loin de sa résonance (K = 1), mais près de f0 elles "
            f"amplifient : à f0, le montage a un gain A0 = {mt.fmt_nombre(gain)}, soit "
            f"{mt.fmt_nombre(20 * math.log10(gain), 3)} dB.")
    if not (pont and porteur is not None):
        r.texte(mt.phrase_pont(res, pont))
        return
    R = porteur.montage.composants["R1"]
    (r1, r1_t), (rb, rb_t) = ((n_, _nom_tex(n_)) for n_ in (porteur.designation("R1"),
                                                             porteur.designation("Rb")))
    R_val, A_val, a_val = r.precis_si(R, "Ω"), r.precis(gain), r.precis(alpha)
    r.texte(f"Le pont de la cellule {nom_cellule} atténue l'entrée de α = 1/A0 et remplace sa "
            f"résistance d'entrée R = {R_val[0]} : la cellule voit toujours R (résistances en "
            "parallèle), le gain du montage revient à 0 dB.")
    r.calcul(("α", r"\alpha"), ("1/A0", r"\dfrac{1}{A_0}"), (f"1/{A_val[0]}", r"\dfrac{1}{%s}" % A_val[1]),
             r.nombre(alpha), _approche(alpha))
    r.calcul((r1, r1_t), ("R/α", r"\dfrac{R}{\alpha}"),
             (f"{R_val[0]} / {a_val[0]}", r"\dfrac{%s}{%s}" % (R_val[1], a_val[1])), r.si(Ra, "Ω"), _approche(Ra))
    r.calcul((rb, rb_t), ("R/(1 − α)", r"\dfrac{R}{1 - \alpha}"),
             (f"{R_val[0]} / (1 − {a_val[0]})", r"\dfrac{%s}{1 - %s}" % (R_val[1], a_val[1])), r.si(Rb, "Ω"),
             _approche(Rb))


def _normalisation_series(r: _Redaction, choix: mt.ChoixSeries, pont: bool) -> None:
    """Paragraphe à part, après les valeurs calculées : les valeurs normalisées (séries E)."""
    res = r.res
    r.etape(0, f"Normalisation des valeurs ({choix.court()})")
    seule = (" Les condensateurs gardent leurs valeurs calculées." if not choix.condensateurs else
             " Les résistances gardent leurs valeurs calculées." if not choix.resistances else "")
    r.texte(f"Les composants du commerce suivent les séries normalisées : {choix.libelle()}. Chaque valeur "
            "calculée est remplacée par la valeur la plus proche de sa série"
            + (" ou, si celle-ci s'écarte de plus de 1 %, par l'association de deux valeurs (« a + b » : "
               "résistances en série, condensateurs en parallèle)" if choix.associations else "")
            + "." + seule)
    normalises = mt.etages_reels(res, choix, pont)
    exemple = mt.premiere_association(normalises)
    if exemple:
        r.texte(f"Une association compte deux composants, numérotés chacun (par exemple « {exemple} ») : "
                "les repères qui suivent sont décalés d'autant. Ce sont ceux du montage réel (onglet "
                "Câblage).")
    ajustees = mt.phrase_ajustements(res, choix, pont)
    if ajustees:
        r.texte(ajustees)
    r.texte("Tableau récapitulatif des valeurs normalisées :")
    r.tableau_composants(normalises, "normalisees")
    r.texte(mt.phrase_ecart_serie(res, choix, pont) + " La vérification du gabarit ci-dessous porte aussi "
            "sur ces valeurs.")


def _verification(r: _Redaction, choix: Optional[mt.ChoixSeries]) -> None:
    """Vérification du gabarit (valeurs calculées, puis normalisées), puis les remarques."""
    res = r.res
    t = res.gabarit.type
    r.etape(0, "Vérification du gabarit")
    r.texte("On calcule le gain du filtre aux fréquences limites du gabarit :")
    r.formule(r"G(f) = 20\,\log\left|H(j\,2\pi f)\right|", "G(f) = 20·log|H(j·2πf)|")
    r.controles(res.points_controle())
    if choix is not None and choix.actif and res.montages:
        r.texte(f"Avec les valeurs normalisées ({choix.court()}) :")
        r.controles(res.points_controle_serie(choix))
    for remarque in res.avertissements + res.remarques_montage:
        if not (t == "CB" and "Sallen & Key" in remarque):     # déjà dit à l'étape 6
            r.detail(remarque)


class _RedactionCellule:
    """Étape 6, une cellule : ses valeurs telles qu'on les écrit (résultats et applications
    numériques), et les calculs qui reviennent d'une structure à l'autre."""

    def __init__(self, r: _Redaction, e: mt.Etage, w: str, w_tex: str):
        self.r, self.e, self.w, self.w_tex = r, e, w, w_tex
        m = self.m = e.montage
        c = self.cellule = m.cellule
        self.R0, self.C0 = r.si(m.R0, "Ω"), r.si(m.C0, "F")                       # résultats encadrés
        self.R0_an, self.C0_an = r.precis_si(m.R0, "Ω"), r.precis_si(m.C0, "F")   # applications numériques
        self.mm = r.decimales(m.m)
        self.qq = r.decimales(m.q) if m.q is not None else None
        self.m_an = r.precis(m.m)
        self.q_an = r.precis(m.q) if m.q is not None else None
        self.wn = mt.fmt_sci(c.wn, 4) + " rad/s"
        self.wn_an, self.wref_an = r.precis_puls(c.wn), r.precis_puls(r.res.w_ref)

    def nom(self, cle: str) -> Tuple[str, str]:
        """Repère du composant `cle` dans le montage réel : (« R3 », « R_{3} »)."""
        n_ = self.e.designation(cle)
        return n_, _nom_tex(n_)

    def rapport(self, sens_bas: bool) -> Tuple[Tuple[str, str], Tuple[str, str]]:
        """x = ω_ref/ωn (cellule passe-bas) ou ωn/ω_ref (passe-haut) : formule et A.N."""
        w, w_tex, wref_an, wn_an = self.w, self.w_tex, self.wref_an, self.wn_an
        if sens_bas:
            return ((f"{w}/ωn", r"\dfrac{%s}{\omega_n}" % w_tex),
                    (f"{wref_an[0]} / {wn_an[0]}", r"\dfrac{%s}{%s}" % (wref_an[1], wn_an[1])))
        return ((f"ωn/{w}", r"\dfrac{\omega_n}{%s}" % w_tex),
                (f"{wn_an[0]} / {wref_an[0]}", r"\dfrac{%s}{%s}" % (wn_an[1], wref_an[1])))

    def coefficient(self, cle: str, symbole: str, coef_an: Tuple[str, str], unite: str) -> None:
        """Composant = coefficient × valeur de référence (m·C0, q·C0) ou référence / coefficient
        (R0/m, R0/q)."""
        valeur = self.m.composants[cle]
        if unite == "F":
            self.r.calcul(self.nom(cle), (f"{symbole}·C0", r"%s\,C_0" % symbole),
                          (f"{coef_an[0]} × {self.C0_an[0]}", r"%s \times %s" % (coef_an[1], self.C0_an[1])),
                          self.r.si(valeur, "F"), _approche(valeur))
        else:
            self.r.calcul(self.nom(cle), (f"R0/{symbole}", r"\dfrac{R_0}{%s}" % symbole),
                          (f"{self.R0_an[0]} / {coef_an[0]}", r"\dfrac{%s}{%s}" % (self.R0_an[1], coef_an[1])),
                          self.r.si(valeur, "Ω"), _approche(valeur))


def _etapes_cellule(r: _Redaction, e: mt.Etage, w: str, w_tex: str) -> None:
    """Étape 6, une cellule : ses coefficients m et q, puis chacun de ses composants, rédigés
    comme sur une copie (formule, application numérique, résultat encadré)."""
    rc = _RedactionCellule(r, e, w, w_tex)
    r.question(f"Cellule {rc.cellule.nom} · {rc.m.libelle.replace('Cellule ', '')}")
    if rc.m.structure in ("SK_PB", "SK_PH"):
        _etapes_sallen_key(rc)
    elif rc.m.structure in ("RC", "CR"):
        _etapes_premier_ordre(rc)
    else:
        _etapes_rauch(rc)


def _etapes_sallen_key(rc: _RedactionCellule) -> None:
    """Cellule de Sallen & Key : x (s'il diffère de 1), m et q, puis les composants."""
    r, e, m, c = rc.r, rc.e, rc.m, rc.cellule
    Q, Q_an = mt.fmt_nombre(c.Q), r.precis(c.Q)
    r.texte(f"Pulsation propre ωn = {rc.wn}, facteur de qualité Q = {Q}.")
    x = r.res.w_ref / c.wn if m.structure == "SK_PB" else c.wn / r.res.w_ref
    if abs(x - 1) < 1e-9:
        r.calcul(("m", "m"), ("1/(2Q)", r"\dfrac{1}{2Q}"),
                 (f"1/(2 × {Q_an[0]})", r"\dfrac{1}{2\times %s}" % Q_an[1]), rc.mm, _approche_dec(m.m))
        r.calcul(("q", "q"), ("2Q", "2Q"), (f"2 × {Q_an[0]}", r"2\times %s" % Q_an[1]), rc.qq, _approche_dec(m.q))
    else:
        xx, x_an = r.decimales(x), r.precis(x)
        lit, num = rc.rapport(m.structure == "SK_PB")
        r.calcul(("x", "x"), lit, num, xx, _approche_dec(x))
        r.calcul(("m", "m"), ("x/(2Q)", r"\dfrac{x}{2Q}"),
                 (f"{x_an[0]}/(2 × {Q_an[0]})", r"\dfrac{%s}{2\times %s}" % (x_an[1], Q_an[1])),
                 rc.mm, _approche_dec(m.m))
        r.calcul(("q", "q"), ("2Q·x", r"2Q\,x"),
                 (f"2 × {Q_an[0]} × {x_an[0]}", r"2\times %s\times %s" % (Q_an[1], x_an[1])),
                 rc.qq, _approche_dec(m.q))
    if m.structure == "SK_PB":
        (r1, r1_t), (r2, r2_t) = rc.nom("R1"), rc.nom("R2")
        if e.pont:                       # la résistance d'entrée R est réalisée par le pont diviseur
            r1, r1_t = "R", "R"
        r.encadre(r"%s = %s = R_0 = %s" % (r1_t, r2_t, rc.R0[1]), f"{r1} = {r2} = R0 = {rc.R0[0]}")
        if e.pont:
            r.texte(f"R est la résistance d'entrée de la cellule : le pont diviseur ({e.designation('R1')} et "
                    f"{e.designation('Rb')}) la réalise, ses valeurs sont calculées plus bas.")
        rc.coefficient("C2", "q", rc.q_an, "F")                 # contre-réaction
        rc.coefficient("C1", "m", rc.m_an, "F")                 # vers la masse
    else:
        (c1, c1_t), (c2, c2_t) = rc.nom("C1"), rc.nom("C2")
        r.encadre(r"%s = %s = C_0 = %s" % (c1_t, c2_t, rc.C0[1]), f"{c1} = {c2} = C0 = {rc.C0[0]}")
        rc.coefficient("R2", "q", rc.q_an, "Ω")                 # contre-réaction
        rc.coefficient("R1", "m", rc.m_an, "Ω")                 # vers la masse


def _etapes_premier_ordre(rc: _RedactionCellule) -> None:
    """Cellule RC ou CR : m, puis la référence et l'autre composant."""
    r, m = rc.r, rc.m
    r.texte(f"Pulsation de coupure ωn = {rc.wn}.")
    lit, num = rc.rapport(m.structure == "RC")
    r.calcul(("m", "m"), lit, num, rc.mm, _approche_dec(m.m))
    if m.structure == "RC":
        r1, r1_t = rc.nom("R1")
        r.encadre(r"%s = R_0 = %s" % (r1_t, rc.R0[1]), f"{r1} = R0 = {rc.R0[0]}")
        rc.coefficient("C1", "m", rc.m_an, "F")
    else:
        c1, c1_t = rc.nom("C1")
        r.encadre(r"%s = C_0 = %s" % (c1_t, rc.C0[1]), f"{c1} = C0 = {rc.C0[0]}")
        rc.coefficient("R1", "m", rc.m_an, "Ω")


def _etapes_rauch(rc: _RedactionCellule) -> None:
    """Cellule passe-bande de Rauch (centre d'un passe-bande d'ordre impair) : q, m, puis les
    composants."""
    r, m, c = rc.r, rc.m, rc.cellule
    comp = m.composants
    q_an, m_an, R0_an = rc.q_an, rc.m_an, rc.R0_an
    Q, Q_an = mt.fmt_nombre(c.Q), r.precis(c.Q)
    r.texte(f"Cellule passe-bande centrée sur f0, de facteur de qualité Q = {Q}.")
    r.calcul(("q", "q"), ("2Q", "2Q"), (f"2 × {Q_an[0]}", r"2\times %s" % Q_an[1]), rc.qq, _approche_dec(m.q))
    r.calcul(("m", "m"), ("1/q", r"\dfrac{1}{q}"), (f"1/{q_an[0]}", r"\dfrac{1}{%s}" % q_an[1]), rc.mm,
             _approche_dec(m.m))
    (r1, r1_t), (r3, r3_t) = rc.nom("R1"), rc.nom("R3")
    r.calcul((f"{r1} = {r3}", f"{r1_t} = {r3_t}"), ("q·R0", r"q\,R_0"),
             (f"{q_an[0]} × {R0_an[0]}", r"%s \times %s" % (q_an[1], R0_an[1])), r.si(comp["R1"], "Ω"),
             _approche(comp["R1"]))
    r.calcul(rc.nom("R2"), ("m·R0/(1 − m²)", r"\dfrac{m\,R_0}{1 - m^2}"),
             (f"{m_an[0]} × {R0_an[0]} / (1 − {m_an[0]}²)",
              r"\dfrac{%s \times %s}{1 - %s^2}" % (m_an[1], R0_an[1], m_an[1])),
             r.si(comp["R2"], "Ω"), _approche(comp["R2"]))
    (c2, c2_t), (c1, c1_t) = rc.nom("C2"), rc.nom("C1")
    r.encadre(r"%s = %s = C_0 = %s" % (c2_t, c1_t, rc.C0[1]), f"{c2} = {c1} = C0 = {rc.C0[0]}")


def _description_cellule(c: mt.Cellule) -> str:
    """Phrase qui décrit une cellule : nature, fréquence propre, Q."""
    nature = {"PB": "passe-bas", "PH": "passe-haut", "PM": "passe-bande", "CB": "coupe-bande"}[c.nature]
    f = mt.fmt_si(c.wn / (2 * math.pi), "Hz")
    if c.ordre == 1:
        return f"Cellule {c.nom}, {nature} du 1er ordre : fréquence de coupure {f}."
    return f"Cellule {c.nom}, {nature} : fréquence propre {f}, Q = {mt.fmt_nombre(c.Q)}."


def texte_etapes(blocs: List[Bloc]) -> str:
    """Version texte des étapes (copie dans un compte rendu) ; les tableaux récapitulatifs
    sont alignés en colonnes."""
    lignes: List[str] = []
    i = 0
    while i < len(blocs):
        b = blocs[i]
        i += 1
        if b.genre in ("entete", "ligne") and b.tableau:
            groupe = [b.texte.split("\t")]
            while i < len(blocs) and blocs[i].genre in ("entete", "ligne") and blocs[i].tableau == b.tableau:
                groupe.append(blocs[i].texte.split("\t"))
                i += 1
            largeurs = [max(len(r[j]) for r in groupe if j < len(r)) for j in range(max(map(len, groupe)))]
            lignes += ["  " + "   ".join(c.ljust(largeurs[j]) for j, c in enumerate(r)).rstrip() for r in groupe]
        elif b.genre == "etape":
            if lignes:
                lignes.append("")
            titre = f"Étape {b.numero} — {b.texte}" if b.numero else b.texte
            lignes += [titre, "-" * len(titre)]
        elif b.genre == "controle":
            lignes.append(f"  {b.texte}   " + ("respecté" if b.ok else "NON RESPECTÉ"))
        elif b.genre == "question":
            lignes += ["", b.texte]
        elif b.genre == "an":
            lignes.append("    A.N. : " + b.texte)
        elif b.genre == "resultat":                    # résultat encadré : trait épais à gauche
            lignes += ["  ┃ " + morceau for morceau in b.texte.split("\n")]
        elif b.texte:
            retrait = {"formule": "  ", "ligne": "  ", "detail": "  ", "valeurs": "      "}.get(b.genre, "")
            lignes.append(retrait + b.texte.replace("\t", "   "))
    return "\n".join(lignes)


def icone_png(taille: int = 64) -> bytes:
    """Icône du programme (PNG transparent de `taille` pixels de côté) : la réponse d'un
    filtre de Butterworth, avec son point à −3 dB, sur un carré bleu aux coins arrondis.

    La figure fait toujours 72 points de côté : les épaisseurs, données en points,
    restent proportionnelles à l'icône quelle que soit sa taille en pixels.
    """
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import FancyBboxPatch
    fig = Figure(figsize=(1, 1), dpi=taille, facecolor="none")
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    marge = 0.03 if taille >= 32 else 0.0
    fond = FancyBboxPatch((marge, marge), 1 - 2 * marge, 1 - 2 * marge, boxstyle="round,pad=0,rounding_size=0.21",
                          facecolor="none", edgecolor="none")
    ax.add_patch(fond)
    degrade = LinearSegmentedColormap.from_list("bleu", ["#174A94", "#2C7BDB"])
    image = ax.imshow(np.linspace(0, 1, 256).reshape(-1, 1), extent=(0, 1, 0, 1), origin="lower",
                      cmap=degrade, aspect="auto", interpolation="bicubic")
    image.set_clip_path(fond)
    if taille >= 48:                                     # quadrillage discret
        for x in (0.37, 0.63):
            ax.plot([x, x], [0.2, 0.8], color="white", alpha=0.18, linewidth=0.9)
        ax.plot([0.18, 0.82], [0.5, 0.5], color="white", alpha=0.18, linewidth=0.9)
    # Réponse d'ordre 2 : gain en dB, fréquence en échelle logarithmique
    lx = np.linspace(-1.3, 1.0, 400)
    gain = -10 * np.log10(1 + 10 ** (4 * lx))
    X = 0.19 + (lx + 1.3) / 2.3 * 0.62
    Y = 0.68 + gain / 40 * 0.42
    garder = Y >= 0.24
    ax.plot(X[garder], Y[garder], color="white", linewidth=5.2 if taille >= 32 else 7.5,
            solid_capstyle="round", solid_joinstyle="round")
    if taille >= 32:                                     # point à −3 dB (fréquence de coupure)
        ax.add_patch(Circle((0.19 + 1.3 / 2.3 * 0.62, 0.68 - 3.01 / 40 * 0.42), 0.058,
                            facecolor="#FFC857", edgecolor="white", linewidth=1.6, zorder=5))
    tampon = io.BytesIO()
    fig.savefig(tampon, format="png", dpi=taille, transparent=True)
    return tampon.getvalue()
