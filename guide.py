# -*- coding: utf-8 -*-
"""
Comprendre la cellule de Sallen & Key : petit cours pour débutant en électronique.

Dix chapitres progressifs, du signal au montage réel : chacun s'appuie sur le
précédent, avec un schéma ou une courbe, une formule au plus et un encadré « À
retenir ». Quand un filtre est calculé, un encadré « Dans votre filtre » relie le
chapitre au montage affiché.

Ce module ne contient que le contenu (textes, formules, figures matplotlib) ;
la fenêtre qui l'affiche est dans interface.py (FenetreGuide).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import NullFormatter

import graphes as gr
import moteur as mt

C = gr.COULEURS
BLEU, ORANGE, VIOLET, GRIS = C["courbe"], C["serie"], C["aop"], C["discret"]


@dataclass
class Chapitre:
    """Un chapitre : titre, phrase d'accroche et blocs à afficher dans l'ordre.

    Blocs : ("texte", str), ("intertitre", str), ("puces", [str]), ("formule", (tex, texte simple)),
    ("figure", (dessin, hauteur)), ("retenir", [str]), ("filtre", fonction(res) -> str | None).
    """
    titre: str
    accroche: str
    blocs: List[tuple]


# =============================================================================
# Figures
# =============================================================================

def _axes_bode(fig: Figure, ylim=(-60, 10), xlim=(0.01, 100), xlabel="Fréquence (f / f0)"):
    """Axes d'un diagramme de Bode (gain en dB, fréquence en échelle logarithmique)."""
    ax = fig.add_axes([0.1, 0.2, 0.86, 0.74])
    ax.set_xscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.grid(True, which="major", color=C["grille"], linewidth=0.8)
    ax.grid(True, which="minor", color=C["grille_fine"], linewidth=0.5)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(C["axe"])
    ax.tick_params(colors=C["discret"], labelsize=9)
    ax.set_xlabel(xlabel, fontsize=9.5, color=C["discret"])
    ax.set_ylabel("Gain (dB)", fontsize=9.5, color=C["discret"])
    return ax


def _graduer(ax, valeurs: List[float], noms: List[str]) -> None:
    """Graduations de l'axe des fréquences en clair (« f0/10 », « f0 », « 10·f0 »)."""
    ax.set_xticks(valeurs)
    ax.set_xticklabels(noms)
    ax.xaxis.set_minor_formatter(NullFormatter())


def _gain_ordre2(x: np.ndarray, Q: float, passe_haut: bool = False) -> np.ndarray:
    """Gain (dB) d'une cellule du second ordre, en fonction de x = f/f0."""
    p = 1j * x
    num = p ** 2 if passe_haut else 1
    return 20 * np.log10(np.abs(num / (1 + p / Q + p ** 2)))


def figure_gabarit(fig: Figure) -> None:
    """Chapitre 1 : réponse d'un passe-bas et son gabarit (zones interdites)."""
    ax = _axes_bode(fig, ylim=(-60, 6), xlim=(0.05, 20), xlabel="Fréquence")
    x = np.logspace(np.log10(0.05), np.log10(20), 600)
    G = -10 * np.log10(1 + x ** 8)                       # Butterworth d'ordre 4, fc = 1
    fp, fa, Gp, Ga = 1.0, 2.6, -3, -30
    style = dict(facecolor=C["interdit"], alpha=0.08, edgecolor=C["interdit"], linewidth=1.2)
    ax.add_patch(Rectangle((0.05, -60), fp - 0.05, Gp + 60, **style))
    ax.add_patch(Rectangle((fa, Ga), 20 - fa, 66, **style))
    ax.plot(x, G, color=BLEU, linewidth=2.2)
    ax.set_xticks([fp, fa])
    ax.set_xticklabels(["fp", "fa"], fontsize=10, color=C["encre"])
    ax.set_yticks([Gp, Ga])
    ax.set_yticklabels(["Gp", "Ga"], fontsize=10, color=C["encre"])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.text(0.22, -32, "zone interdite\n(gain trop faible)", ha="center", fontsize=9, color=C["interdit"])
    ax.text(6.0, -12, "zone interdite\n(gain trop fort)", ha="center", fontsize=9, color=C["interdit"])
    ax.text(0.3, 1.5, "bande passante", ha="center", fontsize=9, color=C["encre2"])
    ax.text(1.6, -50, "transition", ha="center", fontsize=9, color=C["encre2"])


def figure_impedances(fig: Figure) -> None:
    """Chapitre 2 : impédance d'une résistance et d'un condensateur selon la fréquence."""
    ax = fig.add_axes([0.12, 0.2, 0.84, 0.74])
    f = np.logspace(1, 6, 200)
    ax.loglog(f, np.full_like(f, 10e3), color=ORANGE, linewidth=2.2, label="Résistance 10 kΩ")
    ax.loglog(f, 1 / (2 * np.pi * f * 10e-9), color=BLEU, linewidth=2.2, label="Condensateur 10 nF")
    ax.set_xlim(10, 1e6)
    ax.set_ylim(1, 1e7)
    ax.grid(True, which="major", color=C["grille"], linewidth=0.8)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(C["axe"])
    ax.tick_params(colors=C["discret"], labelsize=9)
    ax.set_xlabel("Fréquence (Hz)", fontsize=9.5, color=C["discret"])
    ax.set_ylabel("Impédance (Ω)", fontsize=9.5, color=C["discret"])
    ax.set_xticks([10, 100, 1e3, 1e4, 1e5, 1e6])
    ax.set_xticklabels(["10 Hz", "100 Hz", "1 kHz", "10 kHz", "100 kHz", "1 MHz"])
    ax.set_yticks([1, 10, 100, 1e3, 1e4, 1e5, 1e6, 1e7])
    ax.set_yticklabels(["1 Ω", "10 Ω", "100 Ω", "1 kΩ", "10 kΩ", "100 kΩ", "1 MΩ", "10 MΩ"])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.annotate("presque un circuit ouvert", (30, 5.3e5), fontsize=9, color=BLEU)
    ax.annotate("presque un fil", (1.2e5, 40), fontsize=9, color=BLEU)


def _schema(fig: Figure, xlim, ylim) -> gr._Dessin:
    ax = fig.add_axes([0.01, 0.02, 0.98, 0.96])
    ax.set_axis_off()
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal", anchor="C")
    return gr._Dessin(ax)


def _nom(d: gr._Dessin, x: float, y: float, texte: str, role: str = "", place: str = "haut") -> None:
    """Repère d'un composant (en gras) et son rôle (discret)."""
    gr._Dessin.etiquette(d, x, y, role, texte, place)


def figure_rc(fig: Figure) -> None:
    """Chapitre 3 : filtre RC passe-bas."""
    d = _schema(fig, (-0.4, 8.0), (0.1, 3.7))
    ys, ym, xe, xn, xs = 2.4, 0.6, 0.6, 4.0, 6.8
    d.borne(xe, ys)
    d.borne(xe, ym)
    d.resistance((xe, ys), (xn, ys))
    d.fil((xn, ys), (xs, ys))
    d.condensateur((xn, ys), (xn, ym))
    d.fil((xe, ym), (xs, ym))
    d.noeud(xn, ys)
    d.noeud(xn, ym)
    d.borne(xs, ys)
    d.borne(xs, ym)
    _nom(d, (xe + xn) / 2, ys + 0.2, "R", "en série")
    _nom(d, xn + 0.4, (ys + ym) / 2, "C", "vers la masse", place="droite")
    d.tension(xe + 0.32, ym, ys, "$V_e$")
    d.tension(xs - 0.32, ym, ys, "$V_s$", gauche=True)


def figure_bode_rc(fig: Figure) -> None:
    """Chapitre 3 : Bode du RC, asymptotes et point à −3 dB."""
    ax = _axes_bode(fig, ylim=(-45, 5), xlim=(0.01, 100), xlabel="Fréquence (f / fc)")
    x = np.logspace(-2, 2, 400)
    ax.plot(x, 20 * np.log10(np.abs(1 / (1 + 1j * x))), color=BLEU, linewidth=2.2)
    ax.plot([0.01, 1], [0, 0], color=GRIS, linewidth=1, linestyle="--")
    ax.plot([1, 100], [0, -40], color=GRIS, linewidth=1, linestyle="--")
    ax.plot([1], [-3.01], "o", color=BLEU, markersize=5)
    ax.annotate("−3 dB à fc", (1, -3.01), xytext=(1.6, 0.5), fontsize=9, color=C["encre"])
    ax.annotate("pente −20 dB par décade", (10, -20), xytext=(1.3, -33), fontsize=9, color=C["encre2"],
                arrowprops=dict(arrowstyle="->", color=GRIS, linewidth=0.8))
    _graduer(ax, [0.01, 0.1, 1, 10, 100], ["fc/100", "fc/10", "fc", "10·fc", "100·fc"])


def figure_cascade_rc(fig: Figure) -> None:
    """Chapitre 4 : un RC, deux RC à la suite, et un vrai second ordre (Q = 0,707)."""
    ax = _axes_bode(fig, ylim=(-50, 5), xlim=(0.05, 20), xlabel="Fréquence (f / fc)")
    x = np.logspace(np.log10(0.05), np.log10(20), 400)
    p = 1j * x
    ax.plot(x, 20 * np.log10(np.abs(1 / (1 + p))), color=GRIS, linewidth=1.8, label="un RC (1er ordre)")
    ax.plot(x, 20 * np.log10(np.abs(1 / (1 + p) ** 2)), color=ORANGE, linewidth=2,
            label="deux RC isolés (Q = 0,5)")
    ax.plot(x, _gain_ordre2(x, 1 / math.sqrt(2)), color=BLEU, linewidth=2.2,
            label="second ordre, Q = 0,707 (Butterworth)")
    ax.axhline(-3, color=C["interdit"], linewidth=0.8, linestyle=":")
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    _graduer(ax, [0.1, 1, 10], ["fc/10", "fc", "10·fc"])


def figure_suiveur(fig: Figure) -> None:
    """Chapitre 5 : amplificateur opérationnel monté en suiveur."""
    d = _schema(fig, (-0.4, 8.6), (0.1, 4.2))
    ym, y_plus, y_moins = 0.6, 1.9, 2.9
    xe, xa, xs = 0.6, 3.0, 7.4
    sortie = d.aop(xa, y_moins, y_plus)
    d.borne(xe, y_plus)
    d.borne(xe, ym)
    d.fil((xe, y_plus), (xa, y_plus))
    d.fil(sortie, (xs, sortie[1]))
    xr = sortie[0] + 0.9
    d.fil((xr, sortie[1]), (xr, 3.75), (xa - 0.5, 3.75), (xa - 0.5, y_moins), (xa, y_moins))
    d.noeud(xr, sortie[1])
    d.fil((xe, ym), (xs, ym))
    d.borne(xs, sortie[1])
    d.borne(xs, ym)
    d.tension(xe + 0.32, ym, y_plus, "$V_e$")
    d.tension(xs - 0.32, ym, sortie[1], "$V_s = V_e$", gauche=True)
    d.ax.text((xa + xr) / 2, 3.95, "la sortie est reliée à l'entrée −", ha="center", fontsize=9,
              color=C["encre2"])


def _cellule(fig: Figure, passe_haut: bool) -> None:
    """Chapitres 6 et 9 : cellule de Sallen & Key à gain unité, avec les repères du programme."""
    d = _schema(fig, (0.1, 11.1), (0.15, 5.35))
    ys, ym, yc = 2.4, 0.6, 4.25
    xe, xa, xb, xamp, xsortie, xs = 0.6, 3.3, 6.0, 6.55, 8.75, 10.6
    serie = d.condensateur if passe_haut else d.resistance
    autre = d.resistance if passe_haut else d.condensateur
    d.borne(xe, ys)
    d.borne(xe, ym)
    serie((xe, ys), (xa, ys))
    serie((xa, ys), (xb, ys))
    d.fil((xb, ys), (xamp, ys))
    sortie = d.suiveur(xamp, ys)
    d.fil(sortie, (xs, ys))
    autre((xb, ys), (xb, ym))
    d.fil((xa, ys), (xa, yc))
    autre((xa, yc), (xsortie, yc))
    d.fil((xsortie, yc), (xsortie, ys))
    d.fil((xe, ym), (xs, ym))
    for p in ((xa, ys), (xb, ys), (xsortie, ys), (xb, ym)):
        d.noeud(*p)
    d.borne(xs, ys)
    d.borne(xs, ym)
    l1, l2, l3, l4 = ("C1", "C2", "R1", "R2") if passe_haut else ("R1", "R2", "C1", "C2")
    _nom(d, (xe + xa) / 2, ys + 0.2, l1, "entrée")
    _nom(d, (xa + xb) / 2, ys + 0.2, l2, "série")
    _nom(d, (xa + xsortie) / 2, yc + 0.3, l3, "contre-réaction")
    _nom(d, xb - 0.36, (ys + ym) / 2, l4, "vers la masse", place="gauche")
    d.ax.text(xa, ys - 0.42, "A", ha="center", fontsize=10, color=C["accent"], fontweight="bold")
    d.ax.text(xb + 0.25, ys + 0.3, "B", ha="center", fontsize=10, color=C["accent"], fontweight="bold")
    d.tension(xe + 0.32, ym, ys, "$V_e$")
    d.tension(xs - 0.32, ym, ys, "$V_s$", gauche=True)


def figure_sk_pb(fig: Figure) -> None:
    _cellule(fig, passe_haut=False)


def figure_sk_ph(fig: Figure) -> None:
    _cellule(fig, passe_haut=True)


def figure_q(fig: Figure) -> None:
    """Chapitre 7 : effet de Q sur la réponse d'une cellule passe-bas."""
    ax = _axes_bode(fig, ylim=(-40, 16), xlim=(0.1, 10))
    x = np.logspace(-1, 1, 500)
    for Q, couleur, largeur in ((0.5, GRIS, 1.6), (0.707, BLEU, 2.4), (2, ORANGE, 1.8), (5, VIOLET, 1.6)):
        texte = "0,707" if Q == 0.707 else mt.fmt_compact(Q)
        ax.plot(x, _gain_ordre2(x, Q), color=couleur, linewidth=largeur, label=f"Q = {texte}")
    ax.axvline(1, color=C["axe"], linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    ax.annotate("bosse : gain ≈ Q en f0", (1, 14), xytext=(1.4, 12.5), fontsize=9, color=VIOLET)
    _graduer(ax, [0.1, 1, 10], ["f0/10", "f0", "10·f0"])


def figure_butterworth4(fig: Figure) -> None:
    """Chapitre 8 : ordre 4 = deux cellules (Q = 0,541 et 1,307) et leur somme en dB."""
    ax = _axes_bode(fig, ylim=(-60, 8), xlim=(0.1, 10), xlabel="Fréquence (f / fc)")
    x = np.logspace(-1, 1, 500)
    q1, q2 = 1 / (2 * math.cos(math.pi / 8)), 1 / (2 * math.cos(3 * math.pi / 8))
    g1, g2 = _gain_ordre2(x, q1), _gain_ordre2(x, q2)
    ax.plot(x, g1, color=GRIS, linewidth=1.6, linestyle="--", label="cellule 1 : Q = 0,541")
    ax.plot(x, g2, color=ORANGE, linewidth=1.6, linestyle="--", label="cellule 2 : Q = 1,307")
    ax.plot(x, g1 + g2, color=BLEU, linewidth=2.4, label="filtre complet (somme des dB)")
    ax.axhline(-3, color=C["interdit"], linewidth=0.8, linestyle=":")
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    _graduer(ax, [0.1, 1, 10], ["fc/10", "fc", "10·fc"])


def figure_passe_bande(fig: Figure) -> None:
    """Chapitre 9 : un passe-bas et un passe-haut décalés font un passe-bande."""
    ax = _axes_bode(fig, ylim=(-50, 40), xlim=(0.2, 5), xlabel="Fréquence (f / f0)")
    x = np.logspace(np.log10(0.2), np.log10(5), 600)
    Q, k = 7.42, 1.07
    g_pb = _gain_ordre2(x / k, Q)
    g_ph = _gain_ordre2(x * k, Q, passe_haut=True)
    ax.plot(x, g_pb, color=GRIS, linewidth=1.6, linestyle="--", label="cellule passe-bas (i)")
    ax.plot(x, g_ph, color=ORANGE, linewidth=1.6, linestyle="--", label="cellule passe-haut (i bis)")
    ax.plot(x, g_pb + g_ph, color=BLEU, linewidth=2.4, label="les deux à la suite")
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    ax.annotate("gain de la bande ≈ +30 dB :\nle pont diviseur le ramène à 0 dB", (1, 29.5), xytext=(1.25, 13),
                fontsize=9, color=C["encre2"], arrowprops=dict(arrowstyle="->", color=GRIS, linewidth=0.8))
    _graduer(ax, [0.25, 0.5, 1, 2, 4], ["f0/4", "f0/2", "f0", "2·f0", "4·f0"])


def figure_cascade(fig: Figure) -> None:
    """Chapitre 8 : cellules à la suite, chacune isolée par son suiveur."""
    ax = fig.add_axes([0.01, 0.02, 0.98, 0.96])
    ax.set_axis_off()
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 2.2)
    ax.set_aspect("equal", anchor="C")
    xs = [1.4, 4.6, 7.8]
    for i, x in enumerate(xs):
        ax.add_patch(FancyBboxPatch((x, 0.55), 2.2, 1.1, boxstyle="round,pad=0.02,rounding_size=0.15",
                                    facecolor=C["fond"], edgecolor=C["accent"], linewidth=1.4))
        ax.text(x + 1.1, 1.25, f"cellule {i + 1}", ha="center", va="center", fontsize=10, color=C["encre"],
                fontweight="bold")
        ax.text(x + 1.1, 0.88, "f0, Q", ha="center", va="center", fontsize=9, color=C["encre2"])
    for x1, x2 in ((0.3, xs[0]), (xs[0] + 2.2, xs[1]), (xs[1] + 2.2, xs[2]), (xs[2] + 2.2, 11.7)):
        ax.annotate("", (x2, 1.1), (x1, 1.1), arrowprops=dict(arrowstyle="-|>", color=C["encre"], linewidth=1.2))
    ax.text(0.3, 1.35, "$V_e$", fontsize=11, color=C["encre2"])
    ax.text(11.2, 1.35, "$V_s$", fontsize=11, color=C["encre2"])
    ax.text(6, 0.12, "H = H1 · H2 · H3   ⇔   G = G1 + G2 + G3 (en dB)", ha="center", fontsize=10,
            color=C["encre"])


# =============================================================================
# Encadrés « Dans votre filtre »
# =============================================================================

def _cellules_2e_ordre(res: mt.Resultat) -> List[mt.Montage]:
    return [m for m in res.montages if m.structure in ("SK_PB", "SK_PH")]


def votre_gabarit(res: mt.Resultat) -> Optional[str]:
    g = res.gabarit
    lignes = [f"{mt.NOMS_TYPES[g.type]} : {mt.resume_gabarit(g)}."]
    if g.type in ("PB", "PH"):
        lignes.append(f"Il faut passer de Gp = {mt.fmt_compact(g.Gp)} dB à Ga = {mt.fmt_compact(g.Ga)} dB entre "
                      f"{mt.fmt_si(g.fp, 'Hz', compact=True)} et {mt.fmt_si(g.fa, 'Hz', compact=True)} : "
                      f"la zone de transition couvre un rapport de {mt.fmt_nombre(max(g.fa / g.fp, g.fp / g.fa), 3)}.")
    return " ".join(lignes)


def votre_ordre(res: mt.Resultat) -> Optional[str]:
    n = res.n
    bande = res.gabarit.type in ("PM", "CB")
    if bande:
        return (f"Votre gabarit demande l'ordre n = {n} (n ≥ {mt.fmt_nombre(res.n_exact)}) : une pente de "
                f"−{20 * n} dB par décade de chaque côté de la bande ; le filtre réel est d'ordre 2n = {2 * n}.")
    return (f"Votre gabarit demande l'ordre n = {n} (n ≥ {mt.fmt_nombre(res.n_exact)}) : une pente de "
            f"−{20 * n} dB par décade au-delà de la coupure.")


def votre_cellule(res: mt.Resultat) -> Optional[str]:
    cellules = _cellules_2e_ordre(res)
    if not cellules:
        return None
    morceaux = []
    for m in cellules[:6]:
        c = m.cellule
        rapport = 4 * c.Q ** 2
        morceaux.append(f"cellule {c.nom} : f0 = {mt.fmt_si(c.wn / (2 * math.pi), 'Hz')}, Q = {mt.fmt_nombre(c.Q, 3)}"
                        f" (rapport des deux {'condensateurs' if m.structure == 'SK_PB' else 'résistances'} "
                        f"≈ {mt.fmt_nombre(rapport, 3)})")
    texte = " ; ".join(morceaux)
    texte = texte[0].upper() + texte[1:]
    if len(cellules) > 6:
        texte += f" ; et {len(cellules) - 6} autres"
    return texte + ". Onglet Composants : schéma et valeurs de chaque cellule."


def votre_cascade(res: mt.Resultat) -> Optional[str]:
    if not res.montages:
        return None
    qs = [m.cellule.Q for m in res.montages if m.cellule.Q]
    texte = f"Votre filtre compte {len(res.montages)} cellule{'s' if len(res.montages) > 1 else ''} ({res.description_montage()})"
    if qs and abs(max(qs) - min(qs)) < 1e-6:
        texte += f", toutes avec Q = {mt.fmt_nombre(qs[0], 3)}"
    elif qs:
        texte += f", avec des Q de {mt.fmt_nombre(min(qs), 3)} à {mt.fmt_nombre(max(qs), 3)}"
    return texte + "."


def votre_passe_bande(res: mt.Resultat) -> Optional[str]:
    if res.gabarit.type != "PM" or not res.montages:
        return None
    gain = 20 * math.log10(res.gain_montage())
    texte = (f"Votre passe-bande est centré sur f0 = {mt.fmt_si(res.norm.f_ref, 'Hz')} ; ses cellules à gain "
             f"unité donnent un gain de {mt.fmt_nombre(gain, 3)} dB à f0.")
    if res.attenuateur():
        texte += " L'option « Pont diviseur d'entrée » le ramène à 0 dB."
    if any(m.structure == "RAUCH" for m in res.montages):
        texte += " Son ordre impair ajoute une cellule passe-bande de Rauch, au centre."
    return texte


# =============================================================================
# Les dix chapitres
# =============================================================================

CHAPITRES: List[Chapitre] = [
    Chapitre(
        "Filtrer un signal",
        "Ce qu'est un filtre, et comment on décrit ce qu'il fait.",
        [
            ("texte", "Une tension qui varie (un son capté par un micro, la mesure d'un capteur) peut toujours se "
                      "voir comme une somme de sinusoïdes de fréquences différentes : des lentes (graves) et des "
                      "rapides (aiguës). Un filtre est un montage qui laisse passer certaines de ces fréquences et "
                      "en affaiblit d'autres."),
            ("puces", ["passe-bas : garde les fréquences basses (par exemple pour enlever un sifflement aigu) ;",
                       "passe-haut : garde les fréquences hautes (pour enlever une dérive lente) ;",
                       "passe-bande : garde une plage de fréquences autour d'une fréquence centrale ;",
                       "coupe-bande : enlève une plage de fréquences."]),
            ("intertitre", "Le gain, en décibels"),
            ("texte", "Si l'on envoie une sinusoïde d'amplitude Ve à l'entrée, on retrouve à la sortie une "
                      "sinusoïde de même fréquence, d'amplitude Vs. Le rapport Vs / Ve est le gain du filtre à "
                      "cette fréquence. On l'exprime en décibels :"),
            ("formule", (r"G = 20\,\log\left(\dfrac{V_s}{V_e}\right)\ \ \mathrm{(dB)}", "G = 20·log(Vs/Ve), en dB")),
            ("puces", ["0 dB : la sinusoïde passe sans changer ;",
                       "−3 dB : son amplitude est multipliée par 0,707 (sa puissance est divisée par 2) ;",
                       "−20 dB : amplitude divisée par 10 ; −40 dB : divisée par 100."]),
            ("intertitre", "Le diagramme de Bode et le gabarit"),
            ("texte", "Le diagramme de Bode trace le gain en fonction de la fréquence, sur une échelle "
                      "logarithmique : chaque graduation multiplie la fréquence par 10 (une décade). Le cahier des "
                      "charges du filtre se dessine dessus : c'est le gabarit. Pour un passe-bas : jusqu'à fp (bande "
                      "passante), le gain doit rester au-dessus de Gp ; à partir de fa (bande atténuée), il doit "
                      "rester sous Ga. Entre les deux, la zone de transition."),
            ("figure", (figure_gabarit, 0.42)),
            ("filtre", votre_gabarit),
            ("retenir", ["un filtre se décrit par son gain en fonction de la fréquence ;",
                         "G = 20·log(Vs/Ve) : −3 dB = amplitude × 0,707, −20 dB = ÷ 10 ;",
                         "le gabarit fixe fp, fa, Gp et Ga : la courbe doit éviter les zones interdites."]),
        ]),
    Chapitre(
        "Résistance et condensateur",
        "Le condensateur se comporte différemment selon la fréquence : c'est lui qui filtre.",
        [
            ("texte", "Une résistance oppose la même « gêne » au courant quelle que soit la fréquence : "
                      "U = R·I. Un condensateur, lui, laisse d'autant mieux passer le courant que la tension varie "
                      "vite. Cette gêne, qui dépend de la fréquence, s'appelle son impédance :"),
            ("formule", (r"Z_C = \dfrac{1}{C\,\omega} \qquad \mathrm{avec}\quad \omega = 2\pi f",
                         "Zc = 1/(C·ω), avec ω = 2π·f")),
            ("texte", "Pour un condensateur de 10 nF : 159 kΩ à 100 Hz, 1,59 kΩ à 10 kHz, 15,9 Ω à 1 MHz. Aux "
                      "basses fréquences, il se comporte presque comme un circuit ouvert (un interrupteur ouvert) ; "
                      "aux hautes fréquences, presque comme un fil."),
            ("figure", (figure_impedances, 0.4)),
            ("texte", "En régime sinusoïdal, on écrit cette impédance avec le nombre complexe j (j² = −1) : "
                      "Z = 1/(jCω). Le j traduit le décalage entre la tension et le courant ; il sert à calculer "
                      "la phase, mais pour comprendre le filtre, la taille de l'impédance suffit."),
            ("retenir", ["un condensateur est un « interrupteur qui dépend de la fréquence » : ouvert aux basses "
                         "fréquences, fermé aux hautes ;",
                         "son impédance vaut 1/(Cω) : elle est divisée par 10 quand la fréquence est multipliée "
                         "par 10."]),
        ]),
    Chapitre(
        "Le filtre RC, premier filtre",
        "Une résistance et un condensateur suffisent pour faire un filtre du premier ordre.",
        [
            ("figure", (figure_rc, 0.34)),
            ("texte", "La résistance R et le condensateur C forment un diviseur de tension : la sortie est prise "
                      "aux bornes du condensateur. Aux basses fréquences, le condensateur est presque ouvert : "
                      "aucun courant ne circule, et Vs = Ve. Aux hautes fréquences, il est presque un fil : Vs "
                      "tend vers 0. C'est un passe-bas."),
            ("formule", (r"\dfrac{V_s}{V_e} = \dfrac{1}{1 + jRC\omega} \qquad\qquad f_c = \dfrac{1}{2\pi R C}",
                         "Vs/Ve = 1/(1 + jRCω)      fc = 1/(2π·R·C)")),
            ("texte", "À la fréquence de coupure fc, le gain vaut −3 dB. Au-delà, chaque fois que la fréquence "
                      "est multipliée par 10, l'amplitude est divisée par 10 : la pente est de −20 dB par "
                      "décade. C'est la signature d'un filtre du premier ordre (un seul condensateur)."),
            ("figure", (figure_bode_rc, 0.4)),
            ("texte", "En échangeant R et C (condensateur en série, résistance vers la masse), on obtient le "
                      "passe-haut CR, avec la même fréquence de coupure."),
            ("retenir", ["RC : diviseur de tension dont le rapport dépend de la fréquence ;",
                         "fc = 1/(2πRC) ; gain −3 dB à fc ;",
                         "premier ordre : pente de −20 dB par décade."]),
        ]),
    Chapitre(
        "Pourquoi aller plus loin que le RC",
        "Un gabarit exigeant demande une pente plus raide et un coude plus net.",
        [
            ("texte", "Un gabarit demande souvent de passer de −3 dB à −40 dB en peu de place : par exemple "
                      "entre 2,4 kHz et 6,24 kHz, soit un rapport de 2,6 seulement. Avec −20 dB par décade, un "
                      "seul RC en est loin. Il faut un filtre d'ordre n, dont la pente vaut −20·n dB par décade."),
            ("intertitre", "Mettre plusieurs RC à la suite ?"),
            ("texte", "C'est la première idée, mais elle a deux défauts. D'abord, chaque RC tire du courant sur "
                      "le précédent et modifie sa tension : les étages se perturbent. Ensuite, même bien isolés, "
                      "deux RC identiques s'affaiblissent ensemble trop tôt : à fc, chacun perd 3 dB et le total "
                      "perd déjà 6 dB. Le coude est mou, arrondi (on dira plus loin que Q = 0,5)."),
            ("figure", (figure_cascade_rc, 0.42)),
            ("texte", "Pour un coude net, il faudrait qu'un étage « remonte » un peu le gain juste avant la "
                      "coupure, pour compenser la chute. Avec seulement des résistances et des condensateurs, "
                      "c'est impossible ; il faut un composant actif, alimenté : l'amplificateur opérationnel."),
            ("filtre", votre_ordre),
            ("retenir", ["ordre n : pente de −20·n dB par décade ;",
                         "des RC à la suite se chargent les uns les autres et donnent un coude mou ;",
                         "un amplificateur permet de redresser le coude."]),
        ]),
    Chapitre(
        "L'amplificateur opérationnel en suiveur",
        "Un composant actif qui recopie une tension sans rien prélever.",
        [
            ("texte", "L'amplificateur opérationnel (AOP), par exemple le µA741, a deux entrées, notées + et −, "
                      "et une sortie. Il amplifie énormément la différence entre ses entrées : environ 200 000 "
                      "fois pour le µA741. Il est alimenté, ici en ±15 V, et sa sortie ne peut pas dépasser "
                      "±13 V environ."),
            ("figure", (figure_suiveur, 0.36)),
            ("intertitre", "Le montage suiveur"),
            ("texte", "Relions la sortie à l'entrée −. Si la sortie était plus basse que Ve, la différence "
                      "(V+ − V−) serait positive et l'AOP ferait monter sa sortie ; si elle était plus haute, il "
                      "la ferait descendre. L'équilibre est atteint quand V− = V+, à quelques microvolts près : la "
                      "sortie recopie l'entrée. Le gain est 1."),
            ("formule", (r"V_s = V_e", "Vs = Ve")),
            ("texte", "À quoi bon recopier une tension ? Le suiveur ne prélève presque aucun courant sur ce qui "
                      "est branché à son entrée, et sa sortie fournit le courant demandé sans que sa tension "
                      "change. Il isole ce qui le précède de ce qui le suit : on peut enchaîner des étages sans "
                      "qu'ils se perturbent. C'est la pièce qui manquait aux RC à la suite."),
            ("retenir", ["un AOP amplifie énormément la différence V+ − V− ;",
                         "monté en suiveur (sortie reliée à l'entrée −), il recopie la tension : gain 1 ;",
                         "il isole les étages : rien n'est prélevé à l'entrée, la sortie ne faiblit pas."]),
        ]),
    Chapitre(
        "La cellule de Sallen & Key passe-bas",
        "Deux RC, un suiveur, et un condensateur relié à la sortie : un vrai second ordre.",
        [
            ("figure", (figure_sk_pb, 0.42)),
            ("texte", "La cellule reprend deux RC (R1 avec C1, R2 avec C2) et un suiveur. La différence avec deux "
                      "RC à la suite : le premier condensateur, C1, n'est pas relié à la masse mais à la sortie. "
                      "Les repères sont ceux du programme : R1 et R2 en série, C1 en contre-réaction (il ramène "
                      "la sortie vers l'entrée, en haut du schéma), C2 vers la masse (en bas)."),
            ("intertitre", "Trois régimes pour comprendre"),
            ("puces", ["fréquences basses : C1 et C2 sont presque ouverts ; aucun courant ne passe dans R1 et R2, "
                       "donc la tension en B vaut Ve, et le suiveur la recopie : Vs = Ve (0 dB). C1 a alors la "
                       "même tension à ses deux bornes : il ne joue aucun rôle ;",
                       "fréquences hautes : C2 relie presque B à la masse, donc Vs tend vers 0 ; C1 relie A à la "
                       "sortie, presque nulle, ce qui affaiblit encore le signal. Deux condensateurs : la pente "
                       "est de −40 dB par décade, c'est un second ordre ;",
                       "autour de f0 : C2 commence à faire baisser B et la sortie prend du retard sur l'entrée. "
                       "Par C1, elle renvoie au point A une part du signal qui, à ces fréquences, s'ajoute au "
                       "signal d'entrée au lieu de s'y opposer : c'est une réaction positive. Elle relève le gain "
                       "juste avant la coupure, puis le décalage devient trop grand et le gain chute vite. Le "
                       "coude devient net."]),
            ("texte", "Plus C1 est grand devant C2, plus cette réaction est forte : le coude se raidit, et peut "
                      "même former une bosse. C'est ce que mesure le facteur de qualité Q, au chapitre suivant."),
            ("retenir", ["Sallen & Key passe-bas = R1, R2 en série, C1 vers la sortie, C2 vers la masse, un "
                         "suiveur ;",
                         "gain 1 aux basses fréquences, −40 dB par décade aux hautes ;",
                         "la contre-réaction par C1 règle la netteté du coude."]),
        ]),
    Chapitre(
        "f0 et Q, les deux réglages d'une cellule",
        "Toute cellule du second ordre se résume à deux nombres.",
        [
            ("texte", "Comme le RC a sa fréquence de coupure, une cellule du second ordre a deux réglages : sa "
                      "fréquence propre f0 (où se situe le coude) et son facteur de qualité Q (la netteté du "
                      "coude). Sa fonction de transfert s'écrit, avec x = f/f0 :"),
            ("formule", (r"H = \dfrac{1}{1 - x^2 + j\,\dfrac{x}{Q}} \qquad\qquad |H(f_0)| = Q",
                         "H = 1/(1 − x² + j·x/Q)      |H(f0)| = Q")),
            ("texte", "À f = f0, le gain vaut exactement Q. Q = 0,5 : −6 dB, le coude mou de deux RC. "
                      "Q = 0,707 : −3 dB à f0, la courbe la plus plate sans bosse (c'est le filtre de Butterworth "
                      "d'ordre 2). Q = 2 : une bosse d'environ +6 dB juste avant la coupure."),
            ("figure", (figure_q, 0.42)),
            ("intertitre", "Avec les composants de la cellule"),
            ("formule", (r"f_0 = \dfrac{1}{2\pi\sqrt{R_1 R_2 C_1 C_2}} \qquad\qquad "
                         r"Q = \dfrac{\sqrt{R_1 R_2 C_1 C_2}}{C_2\,(R_1 + R_2)}",
                         "f0 = 1/(2π·√(R1·R2·C1·C2))      Q = √(R1·R2·C1·C2) / (C2·(R1 + R2))")),
            ("texte", "Avec R1 = R2, la formule de Q se simplifie : Q = ½·√(C1/C2). Q ne dépend que du rapport "
                      "des deux condensateurs : pour Q = 0,707, C1 = 2·C2 ; pour Q = 5, C1 = 100·C2. Une cellule à "
                      "Q élevé demande des condensateurs très différents, et elle est très sensible à leurs "
                      "écarts : quelques pour cent sur C1 ou C2 déplacent nettement la bosse."),
            ("filtre", votre_cellule),
            ("retenir", ["f0 place le coude, Q règle sa netteté ; |H(f0)| = Q ;",
                         "Q = 0,707 : la courbe la plus plate sans bosse (Butterworth d'ordre 2) ;",
                         "avec R1 = R2 : Q = ½·√(C1/C2) ; un Q élevé rend la cellule sensible aux composants."]),
        ]),
    Chapitre(
        "Butterworth : des cellules pour une courbe plate",
        "Un filtre d'ordre n est une chaîne de cellules dont les Q sont choisis ensemble.",
        [
            ("texte", "Pour un filtre d'ordre n, on enchaîne n/2 cellules du second ordre (plus une cellule RC si "
                      "n est impair). Chacune est isolée par son suiveur : leurs gains se multiplient, c'est-à-dire "
                      "que leurs gains en dB s'additionnent."),
            ("figure", (figure_cascade, 0.2)),
            ("texte", "L'approximation de Butterworth choisit les Q des cellules pour que la courbe totale soit "
                      "la plus plate possible dans la bande passante, sans aucune bosse :"),
            ("formule", (r"|H|^2 = \dfrac{1}{1 + \left(f/f_c\right)^{2n}}", "|H|² = 1/(1 + (f/fc)^(2n))")),
            ("texte", "Exemple, l'ordre 4 : une cellule à Q = 0,541 commence à chuter tôt ; l'autre, à Q = 1,307, "
                      "a une petite bosse juste au bon endroit pour compenser. Ensemble, elles donnent une courbe "
                      "plate jusqu'à fc, puis une pente de −80 dB par décade."),
            ("figure", (figure_butterworth4, 0.42)),
            ("texte", "Plus l'ordre est élevé, plus la pente est raide, et plus le Q de la dernière cellule est "
                      "grand (2,56 à l'ordre 8, 3,20 à l'ordre 10). L'ordre minimal se déduit du gabarit : "
                      "c'est l'étape 3 du calcul."),
            ("filtre", votre_cascade),
            ("retenir", ["ordre n : n/2 cellules du second ordre (+ un RC si n est impair), isolées par leurs "
                         "suiveurs ;",
                         "les gains en dB s'additionnent ;",
                         "Butterworth : les Q sont choisis pour une bande passante la plus plate possible."]),
        ]),
    Chapitre(
        "Passe-haut et passe-bande",
        "Les mêmes idées, en échangeant les composants ou en combinant les cellules.",
        [
            ("intertitre", "Le passe-haut : on échange R et C"),
            ("figure", (figure_sk_ph, 0.42)),
            ("texte", "Les condensateurs C1 et C2 passent en série, la résistance R1 en contre-réaction et R2 vers "
                      "la masse. Le raisonnement s'inverse : aux basses fréquences, les condensateurs en série "
                      "bloquent le signal ; aux hautes, ils sont presque des fils et Vs = Ve. Avec C1 = C2, "
                      "Q = ½·√(R2/R1) : cette fois, c'est le rapport des résistances qui règle Q."),
            ("intertitre", "Le passe-bande : un passe-bas et un passe-haut"),
            ("texte", "Un passe-bas qui coupe au-dessus de la bande et un passe-haut qui coupe en dessous, à la "
                      "suite, ne laissent passer que la bande. Pour un passe-bande de Butterworth, chaque cellule "
                      "du filtre de départ devient une paire : une cellule passe-bas (i) et une passe-haut "
                      "(i bis), à Q élevé, de fréquences propres un peu décalées autour de f0."),
            ("figure", (figure_passe_bande, 0.42)),
            ("texte", "Chaque cellule à Q élevé « résonne » près de sa fréquence propre : le montage amplifie "
                      "alors la bande passante, de plusieurs dizaines de dB parfois, et sa sortie peut saturer. "
                      "L'option « Pont diviseur d'entrée » remplace la résistance d'entrée de la première cellule "
                      "par deux résistances qui atténuent juste ce qu'il faut : le gain revient à 0 dB, sans "
                      "changer la forme de la courbe. Pour un ordre impair, la cellule du centre est une cellule "
                      "passe-bande de Rauch, car une cellule de Sallen & Key à gain unité ne peut pas réaliser "
                      "seule le Q demandé."),
            ("filtre", votre_passe_bande),
            ("retenir", ["passe-haut : les condensateurs en série, les résistances règlent Q ;",
                         "passe-bande : des paires passe-bas + passe-haut, à Q élevé ;",
                         "le gain de la bande peut être fort : le pont diviseur d'entrée le ramène à 0 dB."]),
        ]),
    Chapitre(
        "Du calcul au montage réel",
        "Valeurs de référence, séries normalisées, vrais amplificateurs.",
        [
            ("intertitre", "Les valeurs de référence R0 et C0"),
            ("texte", "Le calcul donne f0 et Q de chaque cellule, mais une infinité de couples (R, C) conviennent. "
                      "On en fixe un : R0 (pour les cellules passe-bas) ou C0 (passe-haut), l'autre s'en déduit "
                      "par R0·C0·ω = 1. Chaque composant vaut alors R0 ou C0 multiplié par un coefficient (m ou q) "
                      "propre à la cellule. Choisissez R0 entre 1 kΩ et 100 kΩ : trop petit, l'AOP doit fournir "
                      "trop de courant ; trop grand, les petits courants de fuite comptent."),
            ("intertitre", "Les séries normalisées"),
            ("texte", "Les composants du commerce n'existent qu'en certaines valeurs : 6 par décade en E6 (±20 %), "
                      "12 en E12 (±10 %), 24 en E24 (±5 %). Remplacer chaque valeur calculée par la plus proche "
                      "déplace un peu f0 et Q, et le gabarit, calculé au plus juste, peut ne plus être respecté "
                      "— surtout avec des cellules à Q élevé. Trois remèdes : associer deux valeurs (deux "
                      "résistances en série, deux condensateurs en parallèle), prendre une série plus fine, ou "
                      "choisir la valeur du dessous ou du dessus pour certains composants. C'est ce que fait "
                      "« Corriger les valeurs », dans l'onglet Composants, sans toucher à R0 ni à C0."),
            ("intertitre", "Le vrai amplificateur"),
            ("texte", "Le suiveur parfait n'existe pas : le gain du µA741 diminue quand la fréquence augmente "
                      "(son produit gain-bande vaut environ 1 MHz). Pour des filtres de quelques kilohertz, l'écart "
                      "reste faible ; au-delà, la case « µA741 réel » du Bode réel le montre, et un TL081 (3 MHz, "
                      "même brochage) fait mieux. Enfin, chaque AOP s'alimente en ±15 V, avec un condensateur de "
                      "découplage de 100 nF près de ses broches d'alimentation : l'onglet Câblage donne le schéma "
                      "complet et la liste des composants."),
            ("retenir", ["R0 ou C0 se choisit librement ; le reste s'en déduit ;",
                         "les valeurs normalisées déplacent f0 et Q : vérifiez le gabarit, corrigez si besoin ;",
                         "l'AOP réel a un produit gain-bande fini : à surveiller aux fréquences élevées."]),
        ]),
]


def chapitre(i: int) -> Chapitre:
    """Chapitre numéro i (0 à 9)."""
    return CHAPITRES[i]


# Chapitre à ouvrir depuis l'onglet Composants, selon la structure de la cellule affichée
CHAPITRE_DE_STRUCTURE = {"SK_PB": 5, "SK_PH": 8, "RC": 2, "CR": 2, "RAUCH": 8}


def dessiner(fig: Figure, dessin: Callable[[Figure], None]) -> None:
    """Dessine une figure du guide (fond blanc, police du programme)."""
    fig.clear()
    fig.set_facecolor(C["fond"])
    dessin(fig)


def texte_chapitre(i: int, res: Optional[mt.Resultat] = None) -> str:
    """Chapitre en texte simple (copie)."""
    ch = CHAPITRES[i]
    lignes = [f"{i + 1}. {ch.titre}", ch.accroche, ""]
    for genre, contenu in ch.blocs:
        if genre == "texte":
            lignes += [contenu, ""]
        elif genre == "intertitre":
            lignes += [contenu, ""]
        elif genre == "puces":
            lignes += [f"  • {p}" for p in contenu] + [""]
        elif genre == "formule":
            lignes += ["    " + contenu[1], ""]
        elif genre == "retenir":
            lignes += ["À retenir :"] + [f"  • {p}" for p in contenu] + [""]
        elif genre == "filtre" and res is not None:
            texte = contenu(res)
            if texte:
                lignes += ["Dans votre filtre : " + texte, ""]
    return "\n".join(lignes).strip() + "\n"
