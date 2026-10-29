# -*- coding: utf-8 -*-
"""
compte_rendu.py
===============
Compte rendu PDF de la synthèse (menu Fichier > Compte rendu PDF), en pages A4 :

    page 1   gabarit, résultats, vérification du gabarit, valeurs des composants
    puis     diagrammes de Bode (normalisé et réel)
             étapes du calcul (formules et applications numériques)
             schéma de chaque cellule
             schéma de câblage complet (brochage, nomenclature, notes)

Le texte et les formules sont écrits en vectoriel (nets à toutes les tailles) ;
les diagrammes et les schémas sont insérés en images de 220 ppp.
"""

import io
import logging
import math
import time
from typing import List, Optional, Sequence, Tuple

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.image import imread
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import graphes as gr
import moteur as mt

# fontTools (incorporation des polices dans le PDF) signale des dates de police anciennes : sans objet
logging.getLogger("fontTools").setLevel(logging.ERROR)

A4 = (8.27, 11.69)                                  # pouces
MARGE_G, MARGE_D, MARGE_H, MARGE_B = 0.8, 0.8, 0.75, 0.85
LARGEUR = A4[0] - MARGE_G - MARGE_D
DPI_MESURE = 100                                    # résolution des mesures de texte
DPI_IMAGES = 220                                    # diagrammes et schémas

ENCRE, ENCRE2, DISCRET = gr.COULEURS["encre"], gr.COULEURS["encre2"], gr.COULEURS["discret"]
ACCENT, TRAIT = gr.COULEURS["accent"], "#C9D2DC"
VERT, ROUGE = "#0A7A33", "#B42318"

ROLES = {
    ("PB", "fp"): "fin de la bande passante", ("PB", "fa"): "début de la bande atténuée",
    ("PH", "fa"): "fin de la bande atténuée", ("PH", "fp"): "début de la bande passante",
    ("PM", "fa_moins"): "limite basse de la bande atténuée", ("PM", "fp_moins"): "début de la bande passante",
    ("PM", "fp_plus"): "fin de la bande passante", ("PM", "fa_plus"): "limite haute de la bande atténuée",
    ("CB", "fp_moins"): "fin de la bande passante basse", ("CB", "fa_moins"): "début de la bande rejetée",
    ("CB", "fa_plus"): "fin de la bande rejetée", ("CB", "fp_plus"): "début de la bande passante haute",
    "Gp": "gain minimal dans la bande passante", "Ga": "gain maximal dans la bande atténuée",
    "R0": "résistance de référence (cellules passe-bas)", "C0": "condensateur de référence (cellules passe-haut)",
}


class Document:
    """Pages A4 remplies de haut en bas ; une page s'ajoute quand la place manque."""

    def __init__(self):
        self.pages: List[Figure] = []
        self._nouvelle_page()

    # ------------------------------------------------------------------ pages
    def _nouvelle_page(self) -> None:
        fig = Figure(figsize=A4, dpi=DPI_MESURE, facecolor="white")
        FigureCanvasAgg(fig)
        self.pages.append(fig)
        self.fig = fig
        self.rendu = fig.canvas.get_renderer()
        self.y = MARGE_H                             # position courante, en pouces depuis le haut

    def saut_de_page(self, sauf_si_reste: Optional[float] = None) -> None:
        """Nouvelle page ; avec `sauf_si_reste`, seulement s'il reste moins que cette part de page."""
        if self.y <= MARGE_H + 0.01:
            return
        if sauf_si_reste is not None and self.reste >= sauf_si_reste * (A4[1] - MARGE_H - MARGE_B):
            self.y += 0.15
            return
        self._nouvelle_page()

    @property
    def reste(self) -> float:
        return A4[1] - MARGE_B - self.y

    def _place(self, hauteur: float) -> None:
        """Nouvelle page si `hauteur` ne tient plus sur celle-ci."""
        if hauteur > self.reste and self.y > MARGE_H + 0.01:
            self._nouvelle_page()

    @staticmethod
    def _fx(x: float) -> float:
        return x / A4[0]

    @staticmethod
    def _fy(y: float) -> float:
        return 1 - y / A4[1]

    # ------------------------------------------------------------------ texte
    def _largeur(self, texte: str, prop: FontProperties) -> float:
        largeur, _h, _d = self.rendu.get_text_width_height_descent(texte, prop, ismath=False)
        return largeur / DPI_MESURE

    def _couper(self, texte: str, prop: FontProperties, largeur: float) -> List[str]:
        """Lignes d'au plus `largeur` pouces (coupure aux espaces ordinaires seulement)."""
        lignes = []
        for paragraphe in texte.split("\n"):
            courante = ""
            for mot in paragraphe.split(" "):
                essai = mot if not courante else courante + " " + mot
                if courante and self._largeur(essai, prop) > largeur:
                    lignes.append(courante)
                    courante = mot
                else:
                    courante = essai
            lignes.append(courante)
        return lignes

    def texte(self, texte: str, taille: float = 10.0, gras: bool = False, couleur: str = ENCRE,
              retrait: float = 0.0, avant: float = 0.0, apres: float = 0.05, interligne: float = 1.42,
              reserve: float = 0.0) -> None:
        """Paragraphe ; `reserve` : place à garder sous le début (un titre ne reste pas seul en bas)."""
        prop = FontProperties(size=taille, weight="bold" if gras else "normal")
        lignes = self._couper(mt.insecable(texte), prop, LARGEUR - retrait)
        h = taille * interligne / 72
        self.y += avant
        self._place(h + reserve)
        for ligne in lignes:
            self._place(h)
            self.fig.text(self._fx(MARGE_G + retrait), self._fy(self.y), ligne, fontproperties=prop,
                          color=couleur, va="top", ha="left")
            self.y += h
        self.y += apres

    def titre_section(self, texte: str) -> None:
        self.texte(texte, taille=14, gras=True, couleur=ACCENT, avant=0.16, apres=0.08, reserve=0.9)

    def filet(self, apres: float = 0.12) -> None:
        y = self._fy(self.y)
        self.fig.add_artist(Line2D([self._fx(MARGE_G), self._fx(A4[0] - MARGE_D)], [y, y],
                                   transform=self.fig.transFigure, color=TRAIT, linewidth=0.8))
        self.y += apres

    # ------------------------------------------------------------------ formules
    def _texte_math(self, expression: str, taille: float, x: float, y: float):
        """Une ligne de formule posée en (x, y) (pouces depuis le coin haut gauche, haut du texte) ;
        renvoie l'objet texte et son encombrement."""
        try:
            art = self.fig.text(self._fx(x), self._fy(y), f"${expression}$", fontsize=taille, color=ENCRE,
                                va="top", ha="left", zorder=3)
            return art, art.get_window_extent(self.rendu)
        except ValueError:                           # \dfrac ou \text absents des anciennes versions
            for a in list(self.fig.texts):
                if a.get_text() == f"${expression}$":
                    a.remove()
            art = self.fig.text(self._fx(x), self._fy(y), f"${gr.tex_simplifie(expression)}$", fontsize=taille,
                                color=ENCRE, va="top", ha="left", zorder=3)
            return art, art.get_window_extent(self.rendu)

    def formule(self, tex: str, taille: float = 12.5, retrait: float = 0.15, apres: float = 0.1,
                cadre: Optional[Tuple[str, str]] = None) -> None:
        """Formule mathématique (syntaxe LaTeX de matplotlib), réduite si elle est trop large.

        cadre = (bordure, fond) : résultat encadré, comme sur une copie ; `tex` peut alors compter
        plusieurs lignes (séparées par « \\n »), dans le même cadre. Le tout reste sur une page."""
        lignes = tex.split("\n")
        pad_x, pad_y = (0.1, 0.07) if cadre else (0.0, 0.0)
        ecart = 0.05
        dispo = LARGEUR - retrait - 2 * pad_x

        def creer(t: float):
            arts, y = [], self.y + pad_y
            for ligne in lignes:
                art, boite = self._texte_math(ligne, t, MARGE_G + retrait + pad_x, y)
                arts.append((art, boite))
                y += boite.height / DPI_MESURE + ecart
            return arts

        def effacer(arts) -> None:
            for art, _b in arts:
                art.remove()

        arts = creer(taille)
        largeur = max(b.width for _a, b in arts) / DPI_MESURE
        if largeur > dispo:
            effacer(arts)
            taille = max(7.0, taille * dispo / largeur)
            arts = creer(taille)
        hauteur = sum(b.height for _a, b in arts) / DPI_MESURE + ecart * (len(arts) - 1) + 2 * pad_y
        if hauteur > self.reste and self.y > MARGE_H + 0.01:
            effacer(arts)
            self._nouvelle_page()
            arts = creer(taille)
        if cadre:
            largeur = max(b.width for _a, b in arts) / DPI_MESURE + 2 * pad_x
            self.fig.add_artist(Rectangle((self._fx(MARGE_G + retrait), self._fy(self.y + hauteur)),
                                          largeur / A4[0], hauteur / A4[1], transform=self.fig.transFigure,
                                          facecolor=cadre[1], edgecolor=cadre[0], linewidth=0.8, zorder=1))
        self.y += hauteur + apres

    # ------------------------------------------------------------------ tableaux
    def tableau(self, lignes: Sequence[Sequence[str]], taille: float = 9.5, entete: bool = True,
                couleurs: Optional[Sequence[Optional[str]]] = None, retrait: float = 0.0,
                ecart: float = 0.22) -> None:
        """Tableau simple : colonnes alignées, en-tête discret, filets fins."""
        if not lignes:
            return
        n = max(len(l) for l in lignes)

        def largeurs_pour(t: float) -> List[float]:
            normal, gras = FontProperties(size=t), FontProperties(size=t, weight="bold")
            largeurs = [0.0] * n
            for i, ligne in enumerate(lignes):
                for j, cellule in enumerate(ligne):
                    prop = gras if entete and i == 0 else normal
                    largeurs[j] = max(largeurs[j], self._largeur(cellule, prop))
            return largeurs

        largeurs = largeurs_pour(taille)
        total = sum(largeurs) + ecart * (n - 1)
        if total > LARGEUR - retrait:
            taille *= (LARGEUR - retrait) / total
            largeurs = largeurs_pour(taille)
        xs, x = [], MARGE_G + retrait
        for largeur in largeurs:
            xs.append(x)
            x += largeur + ecart
        fin = min(x - ecart, A4[0] - MARGE_D)
        h = taille * 1.6 / 72
        for i, ligne in enumerate(lignes):
            en_tete = entete and i == 0
            self._place(h * (3 if en_tete else 1))
            couleur = (couleurs[i] if couleurs is not None and i < len(couleurs) and couleurs[i] else
                       (DISCRET if en_tete else ENCRE))
            prop = FontProperties(size=taille, weight="bold" if en_tete else "normal")
            for j, cellule in enumerate(ligne):
                self.fig.text(self._fx(xs[j]), self._fy(self.y + 0.03), cellule, fontproperties=prop, color=couleur,
                              va="top", ha="left")
            self.y += h
            if en_tete or i == len(lignes) - 1:
                y = self._fy(self.y - 0.02)
                self.fig.add_artist(Line2D([self._fx(MARGE_G + retrait), self._fx(fin)], [y, y],
                                           transform=self.fig.transFigure, color=TRAIT, linewidth=0.7))
        self.y += 0.1

    # ------------------------------------------------------------------ images
    def _hauteur_texte(self, texte: str, taille: float, interligne: float = 1.42) -> float:
        prop = FontProperties(size=taille)
        return len(self._couper(mt.insecable(texte), prop, LARGEUR)) * taille * interligne / 72

    def image(self, source: Figure, largeur: float = LARGEUR, legende: str = "",
              hauteur_max: Optional[float] = None, titre: str = "") -> None:
        """Figure matplotlib insérée en image (220 ppp), avec sa légende (et son titre) sur la même
        page ; réduite si l'ensemble ne tient pas sur une page."""
        tampon = io.BytesIO()
        source.savefig(tampon, format="png", dpi=DPI_IMAGES, facecolor="white")
        tampon.seek(0)
        img = imread(tampon)
        h_px, l_px = img.shape[:2]
        hauteur = largeur * h_px / l_px
        h_legende = self._hauteur_texte(legende, 8.5) + 0.2 if legende else 0.0
        h_titre = 14 * 1.42 / 72 + 0.24 if titre else 0.0
        limite = A4[1] - MARGE_H - MARGE_B - h_legende - h_titre - 0.1
        if hauteur_max is not None:
            limite = min(limite, hauteur_max)
        if hauteur > limite:
            largeur, hauteur = largeur * limite / hauteur, limite
        self._place(h_titre + hauteur + h_legende)
        if titre:
            self.titre_section(titre)
        x = MARGE_G + (LARGEUR - largeur) / 2
        ax = self.fig.add_axes([self._fx(x), self._fy(self.y + hauteur), largeur / A4[0], hauteur / A4[1]])
        ax.imshow(img, interpolation="none")
        ax.set_axis_off()
        self.y += hauteur + 0.06
        if legende:
            self.texte(legende, taille=8.5, couleur=DISCRET, apres=0.14)

    # ------------------------------------------------------------------ fin
    def enregistrer(self, chemin: str, titre: str, auteur: str) -> None:
        """Pieds de page (titre, numéro) puis écriture du PDF, polices incorporées."""
        total = len(self.pages)
        for i, page in enumerate(self.pages, start=1):
            page.text(0.5, (MARGE_B / 2) / A4[1], f"{titre}  ·  page {i} / {total}", ha="center", va="center",
                      fontsize=8, color=DISCRET)
        with matplotlib.rc_context({"pdf.fonttype": _type_polices_pdf()}):
            with PdfPages(chemin, metadata={"Title": titre, "Author": auteur, "Creator": auteur}) as pdf:
                for page in self.pages:
                    pdf.savefig(page)


def _type_polices_pdf() -> int:
    """42 : polices TrueType incorporées telles quelles (texte sélectionnable, fichier léger), le
    cas de Segoe UI sous Windows. Une police à contours CFF (.otf) ne peut pas l'être ainsi par
    matplotlib : ses caractères sont alors redessinés (Type 3), ce que tous les lecteurs PDF
    acceptent."""
    from matplotlib import font_manager
    for famille in matplotlib.rcParams["font.family"]:
        try:
            chemin = font_manager.findfont(FontProperties(family=famille), fallback_to_default=False)
            with open(chemin, "rb") as fichier:
                if fichier.read(4) == b"OTTO":
                    return 3
        except (OSError, ValueError):
            continue
    return 42


# =============================================================================
# Contenu du compte rendu
# =============================================================================

def _tableau_composants(doc: Document, etages: List[mt.Etage]) -> None:
    """Une ligne par cellule : m, q, puis ses résistances et ses condensateurs (repères du
    montage réel : R1, R2, R3… d'un bout à l'autre)."""
    lignes = [["Cellule", "Montage", "m", "q", "Résistances", "Condensateurs"]]
    for e in etages:
        m = e.montage
        lignes.append([m.cellule.nom, m.libelle, mt.fmt_decimales(m.m), mt.fmt_decimales(m.q) if m.q is not None else "—",
                       e.liste("R") or "—", e.liste("C") or "—"])
    doc.tableau(lignes, taille=9)


def _controles(doc: Document, points: List[mt.PointControle]) -> None:
    lignes, couleurs = [], []
    for p in points:
        signe = "≥" if p.passante else "≤"
        lignes.append([("✓" if p.ok else "✕"), f"G({p.nom}) = {mt.fmt_nombre(p.G, 4)} dB",
                       f"{signe} {mt.fmt_compact(p.limite)} dB", "respecté" if p.ok else "non respecté"])
        couleurs.append(VERT if p.ok else ROUGE)
    doc.tableau(lignes, taille=10, entete=False, couleurs=couleurs, retrait=0.1)


def _figure_bode(res: mt.Resultat, normalise: bool, choix, aop: bool, dispersion: bool):
    """Diagramme de Bode à la largeur de la page ; renvoie (figure, courbe tracée)."""
    fig, ax_g, ax_p = gr.creer_figure_bode(dpi=100)
    FigureCanvasAgg(fig)
    fig.set_size_inches(LARGEUR, 3.85)
    courbe = gr.tracer_bode(ax_g, ax_p, res, normalise, choix, aop=aop, dispersion=dispersion)
    return fig, courbe


def creer_compte_rendu(chemin: str, res: mt.Resultat, choix: Optional[mt.ChoixSeries] = None,
                       pont: bool = False, aop: bool = False, dispersion: bool = False,
                       fichier: str = "", version: str = "") -> None:
    """Écrit le compte rendu PDF complet du résultat affiché dans le programme."""
    g, nm = res.gabarit, res.norm
    t = g.type
    serie = choix is not None and choix.actif and bool(res.montages)
    choix_serie = choix if serie else None
    ordre_reel = 2 * res.n if t in ("PM", "CB") else res.n
    nom_type = mt.NOMS_TYPES[t]
    titre = f"Filtre {nom_type.lower()} de Butterworth d'ordre {ordre_reel}"
    auteur = f"Filtres de Butterworth {version}".strip()
    doc = Document()

    # ----- Page 1 : résumé ----------------------------------------------------
    doc.texte("Synthèse d'un filtre de Butterworth", taille=20, gras=True, apres=0.02)
    doc.texte(f"{nom_type} d'ordre {ordre_reel} · cellules de Sallen & Key à gain unité", taille=12.5,
              couleur=ENCRE2, apres=0.05)
    date = time.strftime("%d/%m/%Y à %H:%M")
    doc.texte(f"Compte rendu du {date}" + (f" · fichier {fichier}" if fichier else "") + f" · {auteur}",
              taille=8.5, couleur=DISCRET, apres=0.12)
    doc.filet()

    doc.titre_section("Gabarit")
    lignes = [["Paramètre", "Valeur", "Rôle"]]
    for nom in list(mt.FREQUENCES[t]) + ["Gp", "Ga"]:
        valeur = getattr(g, nom)
        texte = mt.fmt_si(valeur, "Hz", compact=True) if nom not in ("Gp", "Ga") else f"{mt.fmt_compact(valeur)} dB"
        lignes.append([mt.LIBELLES[nom], texte, ROLES.get((t, nom), ROLES.get(nom, ""))])
    if t in ("PB", "PM"):
        lignes.append(["R0", mt.fmt_si(g.R0, "Ω", compact=True), ROLES["R0"]])
    if t in ("PH", "PM"):
        lignes.append(["C0", mt.fmt_si(g.C0, "F", compact=True), ROLES["C0"]])
    doc.tableau(lignes)

    doc.titre_section("Résultats")
    lignes = [["Grandeur", "Valeur", "Détail"],
              ["Ordre", f"n = {res.n}", f"n ≥ {mt.fmt_nombre(res.n_exact)}"
               + (f" ; filtre réel d'ordre 2n = {ordre_reel}" if t in ("PM", "CB") else "")],
              ["Sélectivité", f"k = {mt.fmt_nombre(nm.k)}", f"1/k = {mt.fmt_nombre(1 / nm.k)} ; {nm.formule_k}"],
              ["Ondulation", "ε = 1" if res.eps_convention else f"ε = {mt.fmt_nombre(res.eps)}",
               "Gp = −3 dB : coupure à −3 dB en Ω = 1" if res.eps_convention
               else f"coupure à −3 dB en Ωc = {mt.fmt_nombre(res.omega_c)}"]]
    if nm.B is not None:
        lignes.append(["Fréquence centrale", f"f0 = {mt.fmt_si(nm.f_ref, 'Hz')}", f"B = {mt.fmt_nombre(nm.B)}"])
    w = "ω0" if t == "PM" else "ωp"
    if res.ref_pb:
        lignes.append(["Référence passe-bas", f"C0 = {mt.fmt_si(res.ref_pb[1], 'F')}",
                       f"R0 = {mt.fmt_si(res.ref_pb[0], 'Ω')}, R0·C0·{w} = 1"])
    if res.ref_ph:
        lignes.append(["Référence passe-haut", f"R0 = {mt.fmt_si(res.ref_ph[0], 'Ω')}",
                       f"C0 = {mt.fmt_si(res.ref_ph[1], 'F')}, R0·C0·{w} = 1"])
    nb = len(res.montages)
    lignes.append(["Montage", f"{nb} cellule{'s' if nb > 1 else ''}" if nb else "—", res.description_montage()])
    if t == "PM" and res.montages:
        gain = mt.fmt_nombre(20 * math.log10(res.gain_montage()), 3)
        lignes.append(["Gain à f0", "0 dB" if pont and res.attenuateur() else f"{gain} dB",
                       "avec le pont diviseur d'entrée" if pont and res.attenuateur() else "cellules à gain unité"])
    doc.tableau(lignes)

    doc.titre_section("Vérification du gabarit")
    doc.texte("Gain du filtre calculé aux fréquences limites du gabarit :", taille=10, couleur=ENCRE2)
    _controles(doc, res.points_controle())
    if serie:
        doc.texte(f"Avec les valeurs normalisées ({choix.court()}) :", taille=10, couleur=ENCRE2)
        _controles(doc, res.points_controle_serie(choix))

    if res.montages:
        doc.titre_section("Valeurs des composants")
        pont_actif = pont and bool(res.attenuateur())
        doc.texte("Valeurs calculées (R0·C0·ω = 1, puis m et q de chaque cellule)"
                  + (", pont diviseur d'entrée compris" if pont_actif else "") + ". Repères du montage réel : "
                  "dans chaque cellule, éléments en série, puis contre-réaction, puis masse.", taille=10,
                  couleur=ENCRE2)
        _tableau_composants(doc, mt.etages_reels(res, None, pont_actif))
        if serie:
            normalises = mt.etages_reels(res, choix, pont_actif)
            exemple = mt.premiere_association(normalises)
            ajustees = mt.phrase_ajustements(res, choix, pont_actif)
            doc.texte(f"Valeurs normalisées : {choix.libelle()}."
                      + (" « a + b » : deux résistances en série ou deux condensateurs en parallèle, numérotés "
                         f"chacun (par exemple « {exemple} ») ; les repères qui suivent sont décalés d'autant."
                         if exemple else "") + (" " + ajustees if ajustees else ""), taille=10, couleur=ENCRE2)
            _tableau_composants(doc, normalises)
    remarques = res.avertissements + res.remarques_montage
    for remarque in remarques:
        doc.texte("•  " + remarque, taille=8.5, couleur=DISCRET, apres=0.02)

    # ----- Diagrammes de Bode (à la suite, s'il reste de la place) -------------------
    doc.saut_de_page(sauf_si_reste=0.45)
    doc.titre_section("Diagrammes de Bode")
    doc.image(_figure_bode(res, True, None, False, False)[0],
              legende=f"Bode normalisé : prototype passe-bas d'ordre {res.n} et gabarit réduit (Ω = 1 et Ω = 1/k).")
    legende = (f"Bode réel : filtre {nom_type.lower()} et gabarit de départ"
               + (f", avec le montage aux valeurs normalisées ({choix.court()}, courbe orange)" if serie else "")
               + ".")
    if res.attenuateur() and not pont:
        legende += (" Gain ramené à 0 dB à f0 pour la comparaison au gabarit : sans pont diviseur, le montage a "
                    f"{mt.fmt_nombre(20 * math.log10(res.gain_montage()), 3)} dB.")
    aop = aop and bool(res.montages)
    dispersion = dispersion and bool(res.montages)
    if aop:
        legende += " " + mt.bilan_aop(res, choix_serie)[1]
    figure_reel, courbe = _figure_bode(res, False, choix_serie, aop, dispersion)
    if courbe.dispersion is not None:
        legende += " " + mt.bilan_dispersion(res, courbe.dispersion, choix_serie)
    doc.image(figure_reel, legende=legende)

    # ----- Étapes du calcul --------------------------------------------------------
    doc.saut_de_page(sauf_si_reste=0.35)
    doc.titre_section("Étapes du calcul")
    blocs = gr.etapes_du_calcul(res, choix_serie, pont and bool(res.attenuateur()))
    h_controle = 10 * 1.42 / 72 + 0.01

    def a_garder(j: int) -> float:
        """Hauteur d'une liste de vérifications (et de sa phrase d'introduction) qui commence au
        bloc j : elle reste d'un seul tenant, sur la même page que son titre."""
        hauteur = 0.0
        if j < len(blocs) and blocs[j].genre == "texte":
            hauteur, j = doc._hauteur_texte(blocs[j].texte, 10) + 0.04, j + 1
        n = 0
        while j + n < len(blocs) and blocs[j + n].genre == "controle":
            n += 1
        return hauteur + n * h_controle if n else 0.0

    i = 0
    while i < len(blocs):
        b = blocs[i]
        if b.genre == "etape":
            titre_etape = f"Étape {b.numero} · {b.texte}" if b.numero else b.texte
            doc.texte(titre_etape, taille=12, gras=True, couleur=ENCRE, avant=0.14, apres=0.05,
                      reserve=max(0.8, a_garder(i + 1) + 0.05))
        elif b.genre == "texte":
            # Une phrase qui annonce une formule ou un tableau reste sur la même page qu'eux
            suite = blocs[i + 1].genre if i + 1 < len(blocs) else ""
            reserve = a_garder(i) or (0.55 if suite in ("formule", "an", "resultat", "entete", "ligne") else 0.0)
            doc.texte(b.texte, taille=10, couleur=ENCRE2, apres=0.04, reserve=reserve)
        elif b.genre == "question":
            doc.texte(b.texte, taille=10.5, gras=True, couleur=ENCRE, avant=0.08, apres=0.03, reserve=0.75)
        elif b.genre == "formule":
            doc.formule(b.tex)
        elif b.genre == "an":
            doc.formule(gr.TEX_AN + b.tex, retrait=0.45, apres=0.08)
        elif b.genre == "resultat":
            doc.formule(b.tex, cadre=gr.CADRE_RESULTAT, apres=0.14)
        elif b.genre in ("ligne", "entete"):
            groupe = []                              # lignes du même tableau (en-tête éventuel en tête)
            while i < len(blocs) and blocs[i].genre in ("ligne", "entete") and blocs[i].tableau == b.tableau:
                groupe.append(blocs[i].texte.split("\t"))
                i += 1
            doc.tableau(groupe, taille=9.5, entete=b.genre == "entete", retrait=0.1)
            continue
        elif b.genre == "valeurs":
            doc.texte(b.texte, taille=9.5, couleur=ENCRE, retrait=0.3, apres=0.06)
        elif b.genre == "detail":
            doc.texte(b.texte, taille=8.5, couleur=DISCRET, retrait=0.05, apres=0.06)
        elif b.genre == "controle":
            doc.texte(("✓  " if b.ok else "✕  ") + b.texte + ("" if b.ok else "   non respecté"), taille=10,
                      couleur=VERT if b.ok else ROUGE, retrait=0.1, apres=0.01, reserve=a_garder(i) - h_controle)
        i += 1

    # ----- Schémas des cellules -------------------------------------------------------
    if res.montages:
        doc.saut_de_page(sauf_si_reste=0.4)
        doc.titre_section("Schémas des cellules")
        for e in mt.etages_reels(res, choix_serie, pont and bool(res.attenuateur())):
            m = e.montage
            fig = Figure(figsize=(8, 2.6), dpi=100, facecolor="white")
            FigureCanvasAgg(fig)
            gr.dessiner_cellule(fig, e)
            c = m.cellule
            f = mt.fmt_si(c.wn / (2 * math.pi), "Hz")
            detail = (f"fréquence de coupure {f}" if c.ordre == 1 else
                      f"fréquence propre {f}, Q = {mt.fmt_nombre(c.Q)}")
            doc.image(fig, largeur=LARGEUR * 0.92, legende=f"Cellule {c.nom} : {m.libelle}, {detail}.")

        # ----- Câblage ---------------------------------------------------------------------
        doc.saut_de_page()
        doc.image(gr.schema_cablage(res, choix_serie, largeur_pouces=9.0, pont=pont and bool(res.attenuateur())),
                  titre="Schéma de câblage")

    doc.enregistrer(chemin, titre, auteur)
