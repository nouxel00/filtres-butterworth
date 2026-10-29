# -*- coding: utf-8 -*-
"""
saisie.py
=========
Colonne de saisie de la fenêtre principale : textes d'aide et infobulles des champs,
tuiles des types de filtre, champs du gabarit avec leur unité, croquis du gabarit,
listes des séries de composants, et ligne d'état du calcul.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable, Dict, List, Optional

import moteur as mt
from commun import texte_souple, Theme, UI


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
    """Liste déroulante sobre (attribut valeur, méthode selectionner) : un cadre comme
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
