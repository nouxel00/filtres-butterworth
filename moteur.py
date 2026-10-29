# -*- coding: utf-8 -*-
"""
moteur.py
=========
Moteur de calcul : synthèse d'un filtre de Butterworth et dimensionnement des
cellules de Sallen & Key à gain unité (K = 1).

Ce fichier ne contient que des calculs (aucune fenêtre). Il suit les six étapes
classiques de la synthèse d'un filtre actif :

    Étape 1  normalisation du gabarit : coefficient de sélectivité k (et f0, B)
    Étape 2  choix de l'approximation : Butterworth
    Étape 3  ordre minimal n
    Étape 4  fonction de transfert normalisée (polynôme de Butterworth)
    Étape 5  fonction de transfert réelle (transposition de fréquence)
    Étape 6  valeurs des composants (cellules de Sallen & Key à gain unité)

Codes des types de filtres :
    "PB" passe-bas, "PH" passe-haut, "PM" passe-bande, "CB" coupe-bande.

Idée directrice
---------------
Toute fonction de transfert est gardée sous la forme d'un PRODUIT DE CELLULES
d'ordre 1 ou 2. Chaque cellule correspond directement à un étage du montage
final, ce qui rend le calcul des composants immédiat. Une cellule d'ordre 2 est
décrite par sa pulsation propre wn et son facteur de qualité Q :

    passe-bas    H(p) = 1                 / (p²/wn² + p/(Q·wn) + 1)
    passe-haut   H(p) = (p²/wn²)          / (p²/wn² + p/(Q·wn) + 1)
    passe-bande  H(p) = (p/(Q·wn))        / (p²/wn² + p/(Q·wn) + 1)
    coupe-bande  H(p) = (p²/wz² + 1)      / (p²/wn² + p/(Q·wn) + 1)

Le coefficient d'amortissement m utilisé pour le dimensionnement vaut m = 1/(2Q).

Le fichier calcule aussi le montage réel : valeurs normalisées (séries E6, E12,
E24, associations de deux valeurs), étages câblés avec des µA741, nomenclature et
effet du produit gain-bande fini de l'amplificateur.

Utilisation sans interface graphique :   python moteur.py
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


# =============================================================================
# 0. Constantes
# =============================================================================

NOMS_TYPES = {
    "PB": "Passe-bas",
    "PH": "Passe-haut",
    "PM": "Passe-bande",
    "CB": "Coupe-bande",
}

# Nom affiché de chaque paramètre du gabarit.
LIBELLES = {
    "fp": "fp", "fa": "fa",
    "fp_moins": "fp−", "fp_plus": "fp+",
    "fa_moins": "fa−", "fa_plus": "fa+",
    "Gp": "Gp", "Ga": "Ga", "R0": "R0", "C0": "C0",
}

# Fréquences à saisir pour chaque type, dans l'ordre croissant.
FREQUENCES = {
    "PB": ("fp", "fa"),
    "PH": ("fa", "fp"),
    "PM": ("fa_moins", "fp_moins", "fp_plus", "fa_plus"),
    "CB": ("fp_moins", "fa_moins", "fa_plus", "fp_plus"),
}

# Gp = -3 dB : on prend alors ε = 1 (coupure à −3 dB exactement en Ω = 1).
TOLERANCE_GP_3DB = 0.02      # dB
# Gabarit passe-bande / coupe-bande jugé symétrique si les deux fréquences
# centrales diffèrent de moins de 0,5 %.
TOLERANCE_SYMETRIE = 0.005
# Tolérance utilisée pour vérifier que la réponse respecte le gabarit.
TOLERANCE_GABARIT_DB = 0.02
# Au-delà, le filtre n'a plus de sens pratique.
ORDRE_MAX = 30


class ErreurGabarit(ValueError):
    """Saisie incorrecte ou gabarit impossible.

    `champ` désigne le paramètre fautif (par exemple "fa"), pour que
    l'interface puisse mettre le champ correspondant en évidence.
    """

    def __init__(self, message: str, champ: Optional[str] = None):
        super().__init__(message)
        self.champ = champ


# =============================================================================
# 1. Lecture et écriture des nombres (virgule décimale, préfixes k, n, µ…)
# =============================================================================

_MULTIPLICATEURS = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
    "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}

_UNITES = re.compile(r"(hz|ohms?|Ω|Ω|db|f)$", re.IGNORECASE)


def lire_valeur(texte: str, champ: str) -> float:
    """Convertit une saisie en nombre.

    Formats acceptés : 2400 ; 2 400 ; 2,4k ; 2.4 kHz ; 2,4e3 ; 10n ; 10 nF ;
    4k7 (notation des résistances) ; −3 dB.
    """
    s = (texte or "").strip()
    for espace in (" ", " ", " ", " "):
        s = s.replace(espace, "")
    s = s.replace("−", "-").replace(",", ".")
    s = _UNITES.sub("", s)

    if not s:
        raise ErreurGabarit(f"Indiquez une valeur pour {LIBELLES.get(champ, champ)}.", champ)

    # Notation « 4k7 » = 4,7 k ; « 2n2 » = 2,2 n ; « 4R7 » = 4,7
    rkm = re.fullmatch(r"(\d+)([pnuµμmkKMGR])(\d+)", s)
    if rkm:
        prefixe = "" if rkm.group(2) == "R" else rkm.group(2)
        return float(f"{rkm.group(1)}.{rkm.group(3)}") * _MULTIPLICATEURS[prefixe]

    nombre = re.fullmatch(r"([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([pnuµμmkKMG]?)", s)
    if not nombre:
        raise ErreurGabarit(
            f"Valeur illisible pour {LIBELLES.get(champ, champ)} : « {texte.strip()} ». "
            "Exemples acceptés : 2400, 2,4k, 10n.", champ)
    return float(nombre.group(1)) * _MULTIPLICATEURS[nombre.group(2)]


_EXPOSANTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


# (chiffre ou exposant, « 3,921·10⁴ rad/s », suivi d'une unité)
_UNITE_COLLEE = re.compile(r"([\d⁰¹²³⁴⁵⁶⁷⁸⁹]) (?=(?:[GMkmµnp]?(?:Hz|F|Ω|V|s)|dB|%|rad/s|°)(?![A-Za-zÀ-ÿ]))")


def insecable(texte: str) -> str:
    """Espaces insécables, comme en typographie française : un nombre reste avec son unité
    (2,4 kHz, −3 dB, 36 %), les signes : ; ? ! et le guillemet fermant ne commencent jamais
    une ligne, le guillemet ouvrant n'en termine jamais une, et une égalité courte
    (« Ω = 1/k ») n'est pas coupée."""
    texte = _UNITE_COLLEE.sub("\\1\u00a0", texte)
    for avant, apres in ((" :", "\u00a0:"), (" ;", "\u00a0;"), (" ?", "\u00a0?"), (" !", "\u00a0!"),
                         ("« ", "«\u00a0"), (" »", "\u00a0»"), (" = ", "\u00a0=\u00a0"), ("§ ", "§\u00a0")):
        texte = texte.replace(avant, apres)
    return texte


def exposant(entier: int) -> str:
    """Écrit un entier en exposant Unicode : -9 -> ⁻⁹."""
    return str(entier).translate(_EXPOSANTS)


def fmt_nombre(x: float, chiffres: int = 4) -> str:
    """Nombre avec `chiffres` chiffres significatifs et virgule décimale."""
    if x == 0:
        return "0"
    e = math.floor(math.log10(abs(x)))
    decimales = max(0, chiffres - 1 - e)
    s = f"{x:.{decimales}f}"
    if abs(float(s)) >= 10 ** (e + 1) and decimales > 0:   # 9,9996 arrondi en 10,000
        s = f"{x:.{decimales - 1}f}"
    return s.replace(".", ",").replace("-", "−")


def fmt_decimales(x: float, decimales: int = 4) -> str:
    """Nombre arrondi à un nombre fixe de décimales (coefficients du prototype, m et q)."""
    return f"{x:.{decimales}f}".replace(".", ",").replace("-", "−")


_PREFIXES_SI = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""),
                (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")]


def fmt_si(x: float, unite: str = "", chiffres: int = 4, compact: bool = False) -> str:
    """Valeur avec préfixe SI : 6.631e-9, 'F' -> '6,631 nF'.

    compact=True supprime les zéros inutiles (2,400 kHz -> 2,4 kHz) : on l'utilise
    pour rappeler les valeurs saisies.
    """
    if x == 0:
        return f"0 {unite}".strip()
    rang = len(_PREFIXES_SI) - 1
    for rang, (facteur, prefixe) in enumerate(_PREFIXES_SI):
        if abs(x) >= facteur:
            break
    mantisse = fmt_nombre(x / facteur, chiffres)
    # L'arrondi peut donner 1000 (999,96 -> 1000) : on passe alors au préfixe supérieur.
    if rang > 0 and abs(float(mantisse.replace(",", ".").replace("−", "-"))) >= 1000:
        facteur, prefixe = _PREFIXES_SI[rang - 1]
        mantisse = fmt_nombre(x / facteur, chiffres)
    if compact and "," in mantisse:
        mantisse = mantisse.rstrip("0").rstrip(",")
    return f"{mantisse} {prefixe}{unite}".strip()


def fmt_compact(x: float, chiffres: int = 4) -> str:
    """Nombre sans zéros inutiles : -3.0 -> '−3', 0.25 -> '0,25'."""
    s = fmt_nombre(x, chiffres)
    return s.rstrip("0").rstrip(",") if "," in s else s


def fmt_sci(x: float, chiffres: int = 4, style: str = "texte") -> str:
    """Coefficient d'une fonction de transfert.

    style "texte" : 4,397·10⁻⁹      style "tex" (rendu mathématique) : 4{,}397\\cdot10^{-9}
    """
    if x == 0:
        return "0"
    e = math.floor(math.log10(abs(x)))
    if -2 <= e <= 3:
        s = fmt_nombre(x, chiffres)
    else:
        mantisse = x / 10 ** e
        if abs(round(mantisse, chiffres - 1)) >= 10:
            mantisse /= 10
            e += 1
        m = fmt_nombre(mantisse, chiffres)
        s = f"{m}·10{exposant(e)}" if style == "texte" else f"{m}\\cdot10^{{{e}}}"
    if style == "tex":
        s = s.replace(",", "{,}").replace("−", "-")
    return s


def ecrire_polynome(coeffs, formater: Callable[[float], str], style: str = "texte",
                    variable: str = "p") -> str:
    """Écrit a_n·pⁿ + … + a_0 (puissances décroissantes, termes nuls omis)."""
    degre = len(coeffs) - 1
    termes = []
    for i, a in enumerate(coeffs):
        puissance = degre - i
        if abs(a) < 1e-300:
            continue
        if puissance == 0:
            termes.append("1" if abs(a - 1) < 1e-12 else formater(a))
            continue
        if style == "texte":
            p = variable + (exposant(puissance) if puissance > 1 else "")
        else:
            p = variable + (f"^{{{puissance}}}" if puissance > 1 else "")
        if abs(a - 1) < 1e-12:
            termes.append(p)
        else:
            nombre = formater(a)
            if style == "texte":
                sep = "·" if "10" in nombre and "·" in nombre else ""
            else:
                sep = r"\,"
            termes.append(nombre + sep + p)
    return " + ".join(termes)


# =============================================================================
# 2. Le gabarit (cahier des charges)
# =============================================================================

@dataclass
class Gabarit:
    """Gabarit du filtre à synthétiser."""
    type: str                          # "PB", "PH", "PM" ou "CB"
    Gp: float                          # gain minimal dans la bande passante (dB)
    Ga: float                          # gain maximal dans la bande atténuée (dB)
    fp: Optional[float] = None         # PB, PH : limite de la bande passante (Hz)
    fa: Optional[float] = None         # PB, PH : limite de la bande atténuée (Hz)
    fp_moins: Optional[float] = None   # PM, CB : fp−
    fp_plus: Optional[float] = None    # PM, CB : fp+
    fa_moins: Optional[float] = None   # PM, CB : fa−
    fa_plus: Optional[float] = None    # PM, CB : fa+
    R0: Optional[float] = None         # résistance de référence (Ω) : PB, PM
    C0: Optional[float] = None         # condensateur de référence (F) : PH, PM


def verifier_gabarit(g: Gabarit) -> None:
    """Contrôle la cohérence du gabarit ; lève ErreurGabarit sinon."""
    if g.type not in NOMS_TYPES:
        raise ErreurGabarit(f"Type de filtre inconnu : {g.type}.")

    if not g.Gp < 0:
        raise ErreurGabarit("Gp doit être négatif (gain en dB, par exemple −3).", "Gp")
    if not g.Ga < g.Gp:
        raise ErreurGabarit("Ga doit être inférieur à Gp (par exemple −40 dB).", "Ga")

    for nom in FREQUENCES[g.type]:
        v = getattr(g, nom)
        if v is None or not v > 0:
            raise ErreurGabarit(f"{LIBELLES[nom]} doit être une fréquence positive.", nom)

    if g.type == "PB" and not g.fp < g.fa:
        raise ErreurGabarit("Pour un passe-bas, fa doit être supérieure à fp.", "fa")
    if g.type == "PH" and not g.fa < g.fp:
        raise ErreurGabarit("Pour un passe-haut, fa doit être inférieure à fp.", "fa")
    if g.type in ("PM", "CB"):
        noms = FREQUENCES[g.type]
        valeurs = [getattr(g, nom) for nom in noms]
        for gauche, droite, nom in zip(valeurs, valeurs[1:], noms[1:]):
            if not gauche < droite:
                ordre = " < ".join(LIBELLES[x] for x in noms)
                raise ErreurGabarit(
                    f"Pour un {NOMS_TYPES[g.type].lower()}, il faut {ordre}.", nom)

    if g.type in ("PB", "PM") and not (g.R0 and g.R0 > 0):
        raise ErreurGabarit("R0 doit être une résistance positive (par exemple 10k).", "R0")
    if g.type in ("PH", "PM") and not (g.C0 and g.C0 > 0):
        raise ErreurGabarit("C0 doit être une capacité positive (par exemple 10n).", "C0")


# =============================================================================
# 3. Étape 1 : normalisation du gabarit et coefficient de sélectivité k
# =============================================================================

@dataclass
class Normalisation:
    """Résultat de l'étape 1 : coefficient k, fréquence de référence et bande relative."""
    k: float                      # coefficient de sélectivité (0 < k < 1)
    f_ref: float                  # fréquence de normalisation : fp (PB, PH) ou f0 (PM, CB)
    B: Optional[float]            # largeur de bande relative (PM, CB)
    symetrique: bool              # gabarit centré : √(fp+·fp−) = √(fa+·fa−)
    f0_attenuation: Optional[float]
    formule_k: str                # rappel de la formule, pour l'affichage


def normaliser(g: Gabarit) -> Normalisation:
    """Calcule k ; f0 et B pour le passe-bande et le coupe-bande."""
    if g.type == "PB":
        return Normalisation(g.fp / g.fa, g.fp, None, True, None, "k = fp / fa")
    if g.type == "PH":
        return Normalisation(g.fa / g.fp, g.fp, None, True, None, "k = fa / fp")

    # Passe-bande et coupe-bande : normalisation par la fréquence centrale.
    f0 = math.sqrt(g.fp_plus * g.fp_moins)
    # B sert à la transposition p -> (1/B)(p/ω0 + ω0/p) ou p -> B/(p/ω0 + ω0/p).
    # Pour le coupe-bande, on utilise aussi les limites de la bande PASSANTE :
    # c'est ce qui place exactement le gain Gp en fp− et fp+.
    B = (g.fp_plus - g.fp_moins) / f0
    f0a = math.sqrt(g.fa_plus * g.fa_moins)
    symetrique = abs(f0a / f0 - 1) <= TOLERANCE_SYMETRIE

    if g.type == "PM":
        formule = "k = (fp+ − fp−) / (fa+ − fa−)"
        if symetrique:
            k = (g.fp_plus - g.fp_moins) / (g.fa_plus - g.fa_moins)
        else:
            # Gabarit non centré : on calcule la pulsation réduite du prototype
            # atteinte en fa− et en fa+ (transposition) et on garde la plus contraignante.
            om_moins = (f0 / g.fa_moins - g.fa_moins / f0) / B
            om_plus = (g.fa_plus / f0 - f0 / g.fa_plus) / B
            k = 1 / min(om_moins, om_plus)
    else:
        formule = "k = (fa+ − fa−) / (fp+ − fp−)"
        if symetrique:
            k = (g.fa_plus - g.fa_moins) / (g.fp_plus - g.fp_moins)
        else:
            om_moins = B / (f0 / g.fa_moins - g.fa_moins / f0)
            om_plus = B / (g.fa_plus / f0 - f0 / g.fa_plus)
            k = 1 / min(om_moins, om_plus)
    return Normalisation(k, f0, B, symetrique, f0a, formule)


# =============================================================================
# 4. Étape 3 : ordre minimal et ondulation ε
# =============================================================================

def ordre_minimal(Gp: float, Ga: float, k: float) -> Tuple[int, float]:
    """Ordre minimal : n ≥ [log(10^(−Ga/10) − 1) − log(10^(−Gp/10) − 1)] / [2·log(1/k)].

    Renvoie (n, valeur exacte du second membre). n est l'entier immédiatement
    supérieur à cette valeur.
    """
    numerateur = math.log10(10 ** (-Ga / 10) - 1) - math.log10(10 ** (-Gp / 10) - 1)
    denominateur = 2 * math.log10(1 / k)
    n_exact = numerateur / denominateur
    n = max(1, math.ceil(n_exact - 1e-9))
    return n, n_exact


def ondulation(Gp: float) -> Tuple[float, bool]:
    """Ondulation : ε² = 10^(−Gp/10) − 1.

    Pour Gp = −3 dB, on prend ε = 1 exactement (coupure à −3 dB en Ω = 1) ;
    le booléen renvoyé l'indique.
    """
    if abs(Gp + 3) <= TOLERANCE_GP_3DB:
        return 1.0, True
    return math.sqrt(10 ** (-Gp / 10) - 1), False


# =============================================================================
# 5. Les cellules (facteurs d'ordre 1 ou 2 de la fonction de transfert)
# =============================================================================

@dataclass
class Cellule:
    """Un facteur d'ordre 1 ou 2 de la fonction de transfert (un étage du montage)."""
    nom: str                       # nom de la cellule : "1", "1 bis", "3"…
    nature: str                    # "PB", "PH", "PM" ou "CB"
    ordre: int                     # 1 ou 2
    wn: float                      # pulsation propre (rad/s ; réduite pour le prototype)
    Q: Optional[float] = None      # facteur de qualité (ordre 2)
    wz: Optional[float] = None     # pulsation des zéros (coupe-bande)

    @property
    def m(self) -> Optional[float]:
        """Coefficient d'amortissement m = 1/(2Q) (ordre 2)."""
        return None if self.Q is None else 1 / (2 * self.Q)

    def polynomes(self) -> Tuple[np.ndarray, np.ndarray]:
        """Numérateur et dénominateur en puissances décroissantes de p."""
        wn = self.wn
        if self.ordre == 1:
            den = np.array([1 / wn, 1.0])
            num = np.array([1.0]) if self.nature == "PB" else np.array([1 / wn, 0.0])
            return num, den
        den = np.array([1 / wn ** 2, 1 / (self.Q * wn), 1.0])
        if self.nature == "PB":
            num = np.array([1.0])
        elif self.nature == "PH":
            num = np.array([1 / wn ** 2, 0.0, 0.0])
        elif self.nature == "PM":
            num = np.array([1 / (self.Q * wn), 0.0])
        else:                                         # coupe-bande
            num = np.array([1 / self.wz ** 2, 0.0, 1.0])
        return num, den

    def reponse(self, w) -> np.ndarray:
        """H(jω) de la cellule pour un tableau de pulsations ω."""
        num, den = self.polynomes()
        p = 1j * np.asarray(w, dtype=float)
        return np.polyval(num, p) / np.polyval(den, p)

    def phase(self, w) -> np.ndarray:
        """Phase continue (rad), recalée sur sa valeur exacte en très basse fréquence."""
        ph = np.unwrap(np.angle(self.reponse(w)))
        depart = {"PB": 0.0, "PH": self.ordre * math.pi / 2,
                  "PM": math.pi / 2, "CB": 0.0}[self.nature]
        return ph + 2 * math.pi * round((depart - ph[0]) / (2 * math.pi))


# =============================================================================
# 6. Étape 4 : fonction de transfert normalisée (prototype passe-bas)
# =============================================================================

def prototype_butterworth(n: int, omega_c: float = 1.0) -> List[Cellule]:
    """Polynôme de Butterworth :

        Bn(p) = (p + 1) · Π (p² + 2·sin(π(2k − 1)/2n)·p + 1),  (n+1)/2 < k < n + 1/2

    Le facteur (p + 1) n'existe que si n est impair. Chaque facteur du second
    degré donne une cellule avec m = sin(π(2k − 1)/2n), soit Q = 1/(2m).

    `omega_c` = ε^(−1/n) décale la coupure quand Gp ≠ −3 dB (omega_c = 1 sinon).
    """
    cellules = []
    numero = 1
    for k in range((n + 1) // 2 + 1, n + 1):          # entiers tels que (n+1)/2 < k < n + 1/2
        m = math.sin(math.pi * (2 * k - 1) / (2 * n))
        cellules.append(Cellule(str(numero), "PB", 2, omega_c, Q=1 / (2 * m)))
        numero += 1
    if n % 2 == 1:
        cellules.append(Cellule(str(numero), "PB", 1, omega_c))
    return cellules


# =============================================================================
# 7. Étape 5 : transposition de fréquence
# =============================================================================

def _paire_de_poles(r: complex) -> Tuple[float, float]:
    """Pulsation propre et facteur Q de la paire de pôles conjugués r, r*."""
    wn = abs(r)
    return wn, wn / (-2 * r.real)


def transposer(prototype: List[Cellule], type_: str, w_ref: float,
               B: Optional[float], omega_c: float, n: int) -> Tuple[List[Cellule], float]:
    """Passe du prototype normalisé au filtre réel (transposition de fréquence).

    Renvoie la liste des cellules réelles et une constante K telle que
    H(p) = K · Π cellules(p). K vaut 1 sauf pour le passe-bande, où les
    cellules ont chacune un gain unité (voir plus bas).
    """
    if type_ == "PB":                       # p -> p/ω0 : chaque pulsation est multipliée
        return [Cellule(c.nom, "PB", c.ordre, c.wn * w_ref, c.Q) for c in prototype], 1.0

    if type_ == "PH":                       # p -> ω0/p : chaque pulsation est inversée
        return [Cellule(c.nom, "PH", c.ordre, w_ref / c.wn, c.Q) for c in prototype], 1.0

    cellules: List[Cellule] = []

    if type_ == "PM":
        # p -> (1/B)(p/ω0 + ω0/p). En variable réduite x = p/ω0, chaque pôle s
        # du prototype donne l'équation x² − B·s·x + 1 = 0, dont les deux racines
        # ont des pulsations ωh > 1 et ωl = 1/ωh, avec le même Q.
        #   - la paire de plus haute fréquence -> cellule passe-bas  (cellule i)
        #   - celle de plus basse fréquence    -> cellule passe-haut (cellule i bis)
        # Le calcul vaut pour n'importe quelle valeur de B.
        for c in prototype:
            if c.ordre == 2:
                s = c.wn * complex(-1 / (2 * c.Q), math.sqrt(1 - 1 / (4 * c.Q ** 2)))
                racines = np.roots([1, -B * s, 1])
                haute, basse = sorted((_paire_de_poles(r) for r in racines), reverse=True)
                cellules.append(Cellule(c.nom, "PB", 2, haute[0] * w_ref, haute[1]))
                cellules.append(Cellule(c.nom + " bis", "PH", 2, basse[0] * w_ref, basse[1]))
            else:
                # Pôle réel s = −Ωc : x² + B·Ωc·x + 1 = 0 -> cellule passe-bande
                # centrée sur ω0 avec Q = 1/(B·Ωc) (dernière cellule).
                a = B * c.wn
                if a < 2:
                    cellules.append(Cellule(c.nom, "PM", 2, w_ref, Q=1 / a))
                else:
                    # Bande très large : les deux pôles sont réels. La cellule se
                    # réduit à une cellule CR (passe-haut) et une cellule RC (passe-bas).
                    x1, x2 = sorted(abs(r.real) for r in np.roots([1, a, 1]))
                    cellules.append(Cellule(c.nom, "PB", 1, x2 * w_ref))
                    cellules.append(Cellule(c.nom + " bis", "PH", 1, x1 * w_ref))

        # Le vrai filtre vaut H(p) = (Ωc·B·ω0)ⁿ·pⁿ / Π(dénominateurs unitaires)
        # (gain 1 en f0), alors que chaque cellule a un gain unité
        # « à sa façon » (en continu, en haute fréquence ou à sa résonance).
        # La constante K recolle les deux écritures.
        produit = 1.0
        for c in cellules:
            if c.nature == "PB":
                produit *= (c.wn / w_ref) ** c.ordre
            elif c.nature == "PM":
                produit *= (c.wn / w_ref) / c.Q
        return cellules, (omega_c * B) ** n / produit

    # Coupe-bande : p -> B / (p/ω0 + ω0/p). Un pôle s donne x² − (B/s)·x + 1 = 0.
    # Chaque cellule a des zéros en ±jω0 (fréquence rejetée).
    for c in prototype:
        if c.ordre == 2:
            s = c.wn * complex(-1 / (2 * c.Q), math.sqrt(1 - 1 / (4 * c.Q ** 2)))
            racines = np.roots([1, -B / s, 1])
            haute, basse = sorted((_paire_de_poles(r) for r in racines), reverse=True)
            cellules.append(Cellule(c.nom, "CB", 2, haute[0] * w_ref, haute[1], wz=w_ref))
            cellules.append(Cellule(c.nom + " bis", "CB", 2, basse[0] * w_ref, basse[1], wz=w_ref))
        else:
            cellules.append(Cellule(c.nom, "CB", 2, w_ref, Q=c.wn / B, wz=w_ref))
    return cellules, 1.0


# =============================================================================
# 8. Étape 6 : composants (cellules de Sallen & Key, RC, CR et Rauch)
# =============================================================================

def sallen_key(Y1, Y2, Y3, Y4, K: float = 1.0):
    """Transmittance de la structure de Sallen & Key (théorème de Millman) :

        T = K·Y1·Y3 / [ (Y1 + Y2)(Y3 + Y4) + Y3(Y4 − K·Y2) ]
    """
    return K * Y1 * Y3 / ((Y1 + Y2) * (Y3 + Y4) + Y3 * (Y4 - K * Y2))


# Ordre d'affichage des composants d'une cellule (clés internes, désignations locales).
ORDRE_COMPOSANTS = ("R1", "R2", "R3", "C1", "C2")

# Numérotation du montage réel (R1, R2, R3… et C1, C2, C3… d'un bout à l'autre du montage).
# Dans chaque cellule : d'abord les éléments en série, dans l'ordre du signal, puis la
# contre-réaction (en haut du schéma), puis l'élément vers la masse (en bas). Clés internes
# dans cet ordre ; les résistances et les condensateurs ont chacun leur compteur.
ORDRE_REEL = {
    "SK_PB": ("R1", "R2", "C2", "C1"),          # R série, R série, C contre-réaction, C masse
    "SK_PH": ("C1", "C2", "R2", "R1"),          # C série, C série, R contre-réaction, R masse
    "RC": ("R1", "C1"),
    "CR": ("C1", "R1"),
    "RAUCH": ("R1", "C2", "R3", "C1", "R2"),    # R entrée, C série, R et C contre-réaction, R masse
}
# Rôle de chaque composant dans sa cellule (« Rb » : résistance du pont diviseur d'entrée)
ROLES = {
    "SK_PB": {"R1": "entrée", "R2": "série", "C2": "contre-réaction", "C1": "vers la masse",
              "Rb": "pont, vers la masse"},
    "SK_PH": {"C1": "entrée", "C2": "série", "R2": "contre-réaction", "R1": "vers la masse"},
    "RC": {"R1": "série", "C1": "vers la masse"},
    "CR": {"C1": "série", "R1": "vers la masse"},
    "RAUCH": {"R1": "entrée", "C2": "série", "R3": "contre-réaction", "C1": "contre-réaction",
              "R2": "vers la masse"},
}

STRUCTURES = {
    "SK_PB": "Sallen & Key passe-bas",
    "SK_PH": "Sallen & Key passe-haut",
    "RC": "Cellule RC (1er ordre)",
    "CR": "Cellule CR (1er ordre)",
    "RAUCH": "Passe-bande de Rauch",
}


@dataclass
class Montage:
    """Valeurs des composants d'une cellule. Les clés sont les désignations locales de
    la cellule (calculs) ; l'affichage utilise la numérotation du montage réel
    (voir ORDRE_REEL et etages_reels : R1, R2, R3… d'un bout à l'autre).

    Sallen & Key passe-bas  : R1 (entrée), R2 (série), C1 (vers la masse),
                              C2 (contre-réaction vers la sortie)
    Sallen & Key passe-haut : C1 (entrée), C2 (série), R1 (vers la masse),
                              R2 (contre-réaction vers la sortie)
    RC / CR (1er ordre)     : élément série puis élément vers la masse
    Rauch                   : R1 = q·R0 (entrée), R2 = m·R0/(1 − m²) (masse),
                              R3 = q·R0 (contre-réaction), C1 = C2 = C0
    """
    cellule: Cellule
    structure: str
    m: float
    q: Optional[float]
    composants: Dict[str, float]
    R0: float
    C0: float
    # Réalisation de chaque valeur avec des composants normalisés (vide : valeurs calculées)
    realisations: Dict[str, "Realisation"] = field(default_factory=dict)

    @property
    def libelle(self) -> str:
        """Nom du montage (« Sallen & Key passe-bas »…)."""
        return STRUCTURES[self.structure]

    @property
    def gain_propre(self) -> float:
        """Gain propre de la cellule réalisée (−1/2 au centre pour la cellule de Rauch)."""
        return -0.5 if self.structure == "RAUCH" else 1.0

    def reponse(self, w, A=None) -> np.ndarray:
        """H(jω) recalculée à partir des valeurs des composants (vérification).

        A : gain en boucle ouverte de l'amplificateur (tableau complexe, même forme
        que w). None : amplificateur idéal (A infini).
        """
        p = 1j * np.asarray(w, dtype=float)
        c = self.composants
        K = 1.0 if A is None else A / (1 + A)      # gain du suiveur : 1 si A est infini
        if self.structure == "SK_PB":     # Y1 = 1/R1, Y2 = jC2ω, Y3 = 1/R2, Y4 = jC1ω
            return sallen_key(1 / c["R1"], p * c["C2"], 1 / c["R2"], p * c["C1"], K)
        if self.structure == "SK_PH":     # Y1 = jC1ω, Y2 = 1/R2, Y3 = jC2ω, Y4 = 1/R1
            return sallen_key(p * c["C1"], 1 / c["R2"], p * c["C2"], 1 / c["R1"], K)
        if self.structure == "RC":
            return 1 / (1 + p * c["R1"] * c["C1"])
        if self.structure == "CR":
            x = p * c["R1"] * c["C1"]
            return x / (1 + x)
        # Rauch (montage inverseur) : C1 vers la sortie, C2 vers l'entrée −
        R1, R2, R3, C1, C2 = (c[x] for x in ("R1", "R2", "R3", "C1", "C2"))
        if A is None:
            return -(p / (R1 * C1)) / (p ** 2 + p * (C1 + C2) / (C1 * C2 * R3)
                                       + (1 / R1 + 1 / R2) / (C1 * C2 * R3))
        # Gain fini : lois des nœuds en X (après R1) et en N (entrée −), avec Vs = −A·V(N).
        # Elles donnent V(X) = −Φ·Vs puis H = G1 / (−Φ·Y + p·C2/A − p·C1).
        G1, G2, G3 = 1 / R1, 1 / R2, 1 / R3
        phi = ((p * C2 + G3) / A + G3) / (p * C2)
        Y = G1 + G2 + p * (C1 + C2)
        return G1 / (-phi * Y + p * C2 / A - p * C1)


def dimensionner(cellules: List[Cellule], w_ref: float,
                 ref_pb: Optional[Tuple[float, float]],
                 ref_ph: Optional[Tuple[float, float]]) -> List[Montage]:
    """Calcule les composants de chaque cellule.

    ref_pb = (R0, C0) des cellules passe-bas et ref_ph = (R0, C0) des cellules
    passe-haut, avec dans les deux cas R0·C0·ω_ref = 1.

    Les coefficients m et q sont déduits de la pulsation propre et du Q de
    chaque cellule :
        passe-bas  : m = x/(2Q), q = 2Q·x avec x = ω_ref/ωn   (ωn = 1/(R0·C0·√(q·m)))
        passe-haut : m = x/(2Q), q = 2Q·x avec x = ωn/ω_ref
    """
    montages = []
    for c in cellules:
        if c.nature == "PB" and c.ordre == 2:
            R0, C0 = ref_pb
            x = w_ref / c.wn
            m, q = x / (2 * c.Q), 2 * c.Q * x
            comp = {"R1": R0, "R2": R0, "C1": m * C0, "C2": q * C0}
            montages.append(Montage(c, "SK_PB", m, q, comp, R0, C0))
        elif c.nature == "PH" and c.ordre == 2:
            R0, C0 = ref_ph
            x = c.wn / w_ref
            m, q = x / (2 * c.Q), 2 * c.Q * x
            comp = {"C1": C0, "C2": C0, "R1": R0 / m, "R2": R0 / q}
            montages.append(Montage(c, "SK_PH", m, q, comp, R0, C0))
        elif c.nature == "PB":                          # 1er ordre : R0 et m·C0
            R0, C0 = ref_pb
            m = w_ref / c.wn
            montages.append(Montage(c, "RC", m, None, {"R1": R0, "C1": m * C0}, R0, C0))
        elif c.nature == "PH":                          # 1er ordre : C0 et R0/m
            R0, C0 = ref_ph
            m = c.wn / w_ref
            montages.append(Montage(c, "CR", m, None, {"C1": C0, "R1": R0 / m}, R0, C0))
        elif c.nature == "PM":
            # Cellule passe-bande d'ordre 2 centrée sur ω0 (n impair). Une cellule
            # de Sallen & Key à gain unité ne peut pas dépasser Q = 1/2 : on utilise
            # ici la structure de Rauch, avec q = 2Q et m = 1/q.
            R0, C0 = ref_pb
            q = 2 * c.Q
            m = 1 / q
            comp = {"R1": q * R0, "R2": m * R0 / (1 - m * m), "R3": q * R0, "C1": C0, "C2": C0}
            montages.append(Montage(c, "RAUCH", m, q, comp, R0, C0))
    return montages


# =============================================================================
# 9. Résultat complet de la synthèse
# =============================================================================

@dataclass
class PointControle:
    """Gain obtenu à une fréquence limite du gabarit."""
    nom: str           # "fp", "fa−"…
    f: float           # fréquence (Hz) ou pulsation réduite (Bode normalisé)
    G: float           # gain obtenu (dB)
    limite: float      # Gp ou Ga (dB)
    passante: bool     # True : limite de bande passante (G ≥ Gp exigé)
    cote: int          # côté où se trouve la bande passante (−1 gauche, +1 droite)

    @property
    def ok(self) -> bool:
        """Vrai si le gain obtenu respecte la limite du gabarit."""
        if self.passante:
            return self.G >= self.limite - TOLERANCE_GABARIT_DB
        return self.G <= self.limite + TOLERANCE_GABARIT_DB


@dataclass
class Resultat:
    """Tout ce que produit la synthèse : ordre, cellules, composants et contrôles."""
    gabarit: Gabarit
    norm: Normalisation
    n: int
    n_exact: float
    eps: float
    eps_convention: bool
    omega_c: float                         # ε^(−1/n)
    w_ref: float                           # 2π·fp ou 2π·f0 (rad/s)
    prototype: List[Cellule]
    cellules: List[Cellule]
    K: float                               # H(p) = K · Π cellules(p)
    montages: List[Montage]
    ref_pb: Optional[Tuple[float, float]]  # (R0, C0) des cellules passe-bas
    ref_ph: Optional[Tuple[float, float]]  # (R0, C0) des cellules passe-haut
    avertissements: List[str] = field(default_factory=list)      # remarques sur le gabarit
    remarques_montage: List[str] = field(default_factory=list)   # remarques sur le montage
    passe_haut_dabord: bool = False      # passe-bande câblé passe-haut d'abord
    _cache_series: Dict = field(default_factory=dict, repr=False, compare=False)

    # ---------------------------------------------------------------- réponses
    def H(self, f) -> np.ndarray:
        """Fonction de transfert réelle H(jω) aux fréquences f (Hz)."""
        w = 2 * np.pi * np.asarray(f, dtype=float)
        h = np.full(w.shape, self.K, dtype=complex)
        for c in self.cellules:
            h = h * c.reponse(w)
        return h

    def phase(self, f) -> np.ndarray:
        """Phase continue de H(jω) en degrés."""
        w = 2 * np.pi * np.asarray(f, dtype=float)
        return np.degrees(sum(c.phase(w) for c in self.cellules))

    def H_normalisee(self, omega) -> np.ndarray:
        """Prototype passe-bas normalisé H(jΩ)."""
        h = np.ones(np.shape(omega), dtype=complex)
        for c in self.prototype:
            h = h * c.reponse(omega)
        return h

    def phase_normalisee(self, omega) -> np.ndarray:
        """Phase continue du prototype normalisé, en degrés."""
        return np.degrees(sum(c.phase(omega) for c in self.prototype))

    def H_realisee(self, f) -> np.ndarray:
        """Transmittance du montage, recalculée à partir des composants."""
        w = 2 * np.pi * np.asarray(f, dtype=float)
        h = np.ones(w.shape, dtype=complex)
        for m in self.montages:
            h = h * m.reponse(w)
        return h

    # ------------------------------------------------------------ contrôles
    def points_controle(self, reponse: Optional[Callable] = None) -> List[PointControle]:
        """Gain obtenu aux fréquences limites du gabarit initial.

        `reponse` est la fonction f -> H(jω) à contrôler ; par défaut, la fonction
        de transfert exacte H. On l'utilise aussi pour le montage aux valeurs normalisées.
        """
        reponse = reponse or self.H
        g = self.gabarit
        definition = {
            "PB": [("fp", g.fp, True, -1), ("fa", g.fa, False, -1)],
            "PH": [("fa", g.fa, False, 1), ("fp", g.fp, True, 1)],
            "PM": [("fa−", g.fa_moins, False, 1), ("fp−", g.fp_moins, True, 1),
                   ("fp+", g.fp_plus, True, -1), ("fa+", g.fa_plus, False, -1)],
            "CB": [("fp−", g.fp_moins, True, -1), ("fa−", g.fa_moins, False, -1),
                   ("fa+", g.fa_plus, False, 1), ("fp+", g.fp_plus, True, 1)],
        }[g.type]
        points = []
        for nom, f, passante, cote in definition:
            G = float(20 * np.log10(abs(reponse(np.array([f]))[0])))
            points.append(PointControle(nom, f, G, g.Gp if passante else g.Ga, passante, cote))
        return points

    def points_controle_normalises(self) -> List[PointControle]:
        """Gain du prototype en Ω = 1 et Ω = 1/k."""
        g = self.gabarit
        points = []
        for nom, om, passante in (("1", 1.0, True), ("1/k", 1 / self.norm.k, False)):
            G = float(20 * np.log10(abs(self.H_normalisee(np.array([om]))[0])))
            points.append(PointControle(nom, om, G, g.Gp if passante else g.Ga, passante, -1))
        return points

    def gabarit_respecte(self) -> bool:
        """Vrai si le gain respecte le gabarit à toutes ses fréquences limites."""
        return all(p.ok for p in self.points_controle())

    def ecart_verification(self) -> Optional[float]:
        """Écart relatif maximal entre le montage (composants) et la théorie.

        On recalcule la transmittance de chaque étage à partir de ses
        composants et on la compare au produit des cellules : l'écart doit être
        de l'ordre de 1e-15 (erreurs d'arrondi).
        """
        if not self.montages:
            return None
        f = self.norm.f_ref * np.logspace(-2, 2, 400)
        w = 2 * np.pi * f
        theorique = np.ones(f.shape, dtype=complex)
        for c in self.cellules:
            theorique = theorique * c.reponse(w)
        attendu = np.prod([m.gain_propre for m in self.montages])
        return float(np.max(np.abs(self.H_realisee(f) / theorique / attendu - 1)))

    def gain_montage(self) -> Optional[float]:
        """Gain du montage à la fréquence de référence (rapport, pas en dB).

        Il vaut 1 pour le passe-bas et le passe-haut. Pour le passe-bande, les
        cellules à gain unité amplifient la bande passante : le montage réalise
        H(p)·|gain propre|/K.
        """
        if not self.montages:
            return None
        return abs(np.prod([m.gain_propre for m in self.montages])) / self.K

    def attenuateur(self) -> Optional[Tuple[str, float, float, float]]:
        """Pont diviseur qui ramène le gain du passe-bande à 0 dB.

        On remplace R1 (entrée) de la première cellule passe-bas par Ra en série
        et Rb vers la masse, avec Ra // Rb = R1 : la cellule garde la même
        réponse mais le signal est multiplié par α = Rb/(Ra + Rb).
        Renvoie (nom de la cellule, α, Ra, Rb) ou None.
        """
        gain = self.gain_montage()
        if self.gabarit.type != "PM" or gain is None or gain <= 1.0001:
            return None
        for m in self.montages:
            if m.structure == "SK_PB":
                alpha = 1 / gain
                R1 = m.composants["R1"]
                return m.cellule.nom, alpha, R1 / alpha, R1 / (1 - alpha)
        return None

    # ------------------------------------------------------------ descriptions
    def description_montage(self) -> str:
        """Résumé du montage : « 2 Sallen & Key + 1 RC »."""
        if self.gabarit.type == "CB":
            return "Non réalisable en Sallen & Key"
        compte: Dict[str, int] = {}
        for m in self.montages:
            nom = {"SK_PB": "Sallen & Key", "SK_PH": "Sallen & Key", "RC": "RC",
                   "CR": "CR", "RAUCH": "Rauch"}[m.structure]
            compte[nom] = compte.get(nom, 0) + 1
        return " + ".join(f"{v} {k}" for k, v in compte.items())

    # ------------------------------------------------- valeurs normalisées (séries E)
    def montages_serie(self, choix: Optional["ChoixSeries"]) -> List[Montage]:
        """Montages réalisés avec les séries choisies (None ou choix inactif : valeurs calculées)."""
        if choix is None or not choix.actif:
            return self.montages
        if choix not in self._cache_series:          # la recherche d'associations est mémorisée
            self._cache_series[choix] = [normaliser_montage(m, choix) for m in self.montages]
        return self._cache_series[choix]

    def pont_reel(self, choix: Optional["ChoixSeries"]) -> Optional[Tuple[str, "Realisation", "Realisation"]]:
        """Pont diviseur d'entrée réalisé avec des résistances normalisées : (cellule, résistance
        côté entrée, résistance vers la masse). None sans pont, ou s'il garde ses valeurs calculées
        (il est alors exact : la réponse ne change pas)."""
        if choix is None or not choix.pont or not choix.resistances:
            return None
        att = self.attenuateur()
        if att is None:
            return None
        nom, _alpha, Ra, Rb = att
        return nom, choix.realisation(nom, "Ra", Ra), choix.realisation(nom, "Rb", Rb)

    def _cascade(self, choix: Optional["ChoixSeries"]) -> Tuple[List[Montage], float]:
        """Cellules du montage aux valeurs choisies, et facteur qui ramène sa réponse à l'échelle
        de H(p). Sans pont, ce facteur compense exactement le gain de la cascade (passe-bande),
        comme le ferait un pont exact. Avec un pont normalisé (Ra côté entrée, Rb vers la masse),
        sa cellule voit Ra // Rb à la place de R1 (théorème de Thévenin) et le signal est
        multiplié par Rb/(Ra + Rb) au lieu de α exactement : le gain du montage s'en écarte."""
        montages = self.montages_serie(choix)
        echelle = self.K / np.prod([m.gain_propre for m in self.montages])
        pont = self.pont_reel(choix)
        if pont is not None:
            nom, ra, rb = pont
            a, b = ra.valeur, rb.valeur
            montages = [replace(m, composants={**m.composants, "R1": a * b / (a + b)})
                        if m.cellule.nom == nom and m.structure == "SK_PB" else m for m in montages]
            echelle *= (b / (a + b)) / self.attenuateur()[1]
        return montages, echelle

    def H_serie(self, f, choix: Optional["ChoixSeries"]) -> np.ndarray:
        """Réponse du montage construit avec les composants normalisés.

        Elle est calculée à partir des composants (théorème de Millman) puis
        ramenée à la même échelle que H(p) : pour le passe-bande, cela revient à
        compenser le gain de la cascade, comme le ferait le pont diviseur d'entrée
        (avec ses vraies valeurs s'il est coché et normalisé, voir _cascade).
        """
        w = 2 * np.pi * np.asarray(f, dtype=float)
        montages, echelle = self._cascade(choix)
        h = np.ones(w.shape, dtype=complex)
        for m in montages:
            h = h * m.reponse(w)
        return h * echelle

    def H_aop(self, f, choix: Optional["ChoixSeries"] = None, gbw: float = None,
              a0: float = None) -> np.ndarray:
        """Réponse du montage réel avec des amplificateurs non idéaux.

        Modèle à un pôle du µA741 : A(p) = A0 / (1 + p/ωa), avec ωa = 2π·GBW/A0
        (gain statique A0 = 2·10⁵, produit gain-bande GBW = 1 MHz). Les suiveurs
        ajoutés après une cellule RC ou CR (voir etages_reels) sont pris en compte.
        Même mise à l'échelle que H_serie : on compare directement à H(p).
        """
        gbw = AOP_GBW if gbw is None else gbw
        a0 = AOP_A0 if a0 is None else a0
        w = 2 * np.pi * np.asarray(f, dtype=float)
        A = a0 / (1 + 1j * w * a0 / (2 * np.pi * gbw))
        montages, echelle = self._cascade(choix)
        h = np.ones(w.shape, dtype=complex)
        for i, m in enumerate(montages):
            if m.structure in ("RC", "CR"):
                h = h * m.reponse(w)
                if i < len(montages) - 1:                   # suiveur d'isolation
                    h = h * A / (1 + A)
            else:
                h = h * m.reponse(w, A)
        return h * echelle

    def points_controle_aop(self, choix: Optional["ChoixSeries"] = None) -> List[PointControle]:
        """Gain du montage réel (µA741) aux fréquences limites du gabarit."""
        return self.points_controle(lambda f: self.H_aop(f, choix))

    def points_controle_serie(self, choix: "ChoixSeries") -> List[PointControle]:
        """Gain du montage aux valeurs normalisées, aux fréquences limites du gabarit."""
        return self.points_controle(lambda f: self.H_serie(f, choix))


def passe_haut_en_premier(cellules: List[Cellule]) -> List[Cellule]:
    """Passe-bande : place chaque cellule « i bis » (passe-haut) avant sa cellule « i »
    (passe-bas). La cellule finale (Rauch) ne bouge pas."""
    ordre = list(cellules)
    i = 0
    while i < len(ordre) - 1:
        if ordre[i + 1].nom == ordre[i].nom + " bis":
            ordre[i], ordre[i + 1] = ordre[i + 1], ordre[i]
            i += 2
        else:
            i += 1
    return ordre


def synthese(g: Gabarit, passe_haut_dabord: bool = False) -> Resultat:
    """Enchaîne les six étapes de la synthèse.

    passe_haut_dabord : pour le passe-bande, câble chaque paire de cellules en
    commençant par la passe-haut (i bis, puis i). H(p) est inchangée (produit).
    """
    verifier_gabarit(g)

    # Étape 1 : normalisation et coefficient de sélectivité
    norm = normaliser(g)

    # Étapes 2 et 3 : approximation de Butterworth, ordre minimal
    n, n_exact = ordre_minimal(g.Gp, g.Ga, norm.k)
    if n > ORDRE_MAX:
        raise ErreurGabarit(
            f"L'ordre nécessaire (n = {n}) est trop élevé : élargissez la zone de "
            "transition ou augmentez Ga.")
    eps, convention = ondulation(g.Gp)
    omega_c = eps ** (-1 / n)

    # Étape 4 : prototype passe-bas normalisé
    proto = prototype_butterworth(n, omega_c)

    # Étape 5 : transposition inverse
    w_ref = 2 * math.pi * norm.f_ref
    cellules, K = transposer(proto, g.type, w_ref, norm.B, omega_c, n)
    passe_haut_dabord = passe_haut_dabord and g.type == "PM"
    if passe_haut_dabord:
        cellules = passe_haut_en_premier(cellules)

    # Étape 6 : composants, avec R0·C0·ω_ref = 1
    ref_pb = (g.R0, 1 / (g.R0 * w_ref)) if g.type in ("PB", "PM") else None
    ref_ph = (1 / (g.C0 * w_ref), g.C0) if g.type in ("PH", "PM") else None
    montages = [] if g.type == "CB" else dimensionner(cellules, w_ref, ref_pb, ref_ph)

    res = Resultat(g, norm, n, n_exact, eps, convention, omega_c, w_ref,
                   proto, cellules, K, montages, ref_pb, ref_ph)
    res.passe_haut_dabord = passe_haut_dabord
    if passe_haut_dabord:
        res.remarques_montage.append(
            "Ordre de câblage : chaque cellule passe-haut (i bis) est placée avant sa cellule "
            "passe-bas (i). La fonction de transfert est la même.")

    # Remarques utiles à l'utilisateur
    if g.type in ("PM", "CB") and not norm.symetrique:
        res.avertissements.append(
            f"Gabarit non symétrique : √(fp+·fp−) = {fmt_si(norm.f_ref, 'Hz')} mais "
            f"√(fa+·fa−) = {fmt_si(norm.f0_attenuation, 'Hz')}. "
            "k est calculé du côté le plus contraignant.")
    if any(c.nature == "PB" and c.ordre == 1 for c in cellules) and g.type == "PM":
        res.remarques_montage.append(
            "Bande très large : la cellule passe-bande d'ordre 1 est remplacée par "
            "une cellule RC et une cellule CR.")
    if g.type == "CB":
        res.remarques_montage.append(
            "Le coupe-bande n'est pas réalisable avec la structure de Sallen & Key : "
            "seules les fonctions de transfert sont calculées.")
    if montages:
        valeurs_R = [v for m in montages for k, v in m.composants.items() if k[0] == "R"]
        valeurs_C = [v for m in montages for k, v in m.composants.items() if k[0] == "C"]
        if (min(valeurs_R) < 100 or max(valeurs_R) > 10e6
                or min(valeurs_C) < 10e-12 or max(valeurs_C) > 100e-6):
            res.remarques_montage.append(
                "Certaines valeurs sont peu réalistes (résistances entre "
                f"{fmt_si(min(valeurs_R), 'Ω', 3)} et {fmt_si(max(valeurs_R), 'Ω', 3)}, "
                f"condensateurs entre {fmt_si(min(valeurs_C), 'F', 3)} et "
                f"{fmt_si(max(valeurs_C), 'F', 3)}). Essayez une autre valeur de référence.")
    return res


# =============================================================================
# 9 ter. Valeurs normalisées des composants (séries E6, E12, E24)
# =============================================================================

# Valeurs de base de chaque série, pour une décade (on les multiplie par 10ⁿ).
# Les séries sont géométriques : 6, 12 ou 24 valeurs par décade.
SERIES_E = {
    "E6": (1.0, 1.5, 2.2, 3.3, 4.7, 6.8),
    "E12": (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2),
    "E24": (1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
            3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1),
}
TOLERANCE_SERIE = {"E6": "±20 %", "E12": "±10 %", "E24": "±5 %"}

# Une valeur seule est gardée si elle est à moins de 1 % de la valeur calculée ;
# sinon, si les associations sont permises, on cherche une somme de deux valeurs.
SEUIL_ASSOCIATION = 0.01


@dataclass(frozen=True)
class Ajustement:
    """Valeur choisie pour un composant à la place de la valeur normalisée la plus proche
    (correction du gabarit, voir corriger_gabarit).

    cle : clé interne du composant dans sa cellule (« R1 », « C2 »…), ou « Ra » et « Rb »
    pour les deux résistances du pont diviseur d'entrée. L'ajustement ne vaut que pour la
    valeur calculée indiquée : si le calcul change (autre gabarit, autre R0…), il est ignoré.
    """
    cellule: str
    cle: str
    calculee: float
    elements: Tuple[float, ...]

    def convient(self, cellule: str, cle: str, valeur: float) -> bool:
        """Vrai si l'ajustement porte sur ce composant, pour cette valeur calculée."""
        return (self.cellule == cellule and self.cle == cle
                and abs(valeur / self.calculee - 1) < 1e-6)


@dataclass(frozen=True)
class ChoixSeries:
    """Séries utilisées pour réaliser les composants.

    resistances / condensateurs : "E6", "E12", "E24" ou None (valeur calculée gardée).
    associations : permet de réaliser une valeur par la somme de deux valeurs de la
    série, c'est-à-dire deux résistances en série ou deux condensateurs en parallèle.
    pont : passe-bande avec le pont diviseur d'entrée ; ses deux résistances sont aussi
        normalisées, et la réponse du montage en tient compte (gain et résistance vue
        par la cellule).
    ajustements : valeurs choisies à la place de la valeur la plus proche (correction du
        gabarit) ; les autres composants prennent la valeur la plus proche.
    """
    resistances: Optional[str] = None
    condensateurs: Optional[str] = None
    associations: bool = False
    pont: bool = False
    ajustements: Tuple[Ajustement, ...] = ()

    @property
    def actif(self) -> bool:
        """Vrai si au moins un type de composant est normalisé."""
        return bool(self.resistances or self.condensateurs)

    def serie(self, nom_composant: str) -> Optional[str]:
        """Série à utiliser pour un composant (« R1 », « C2 »…)."""
        return self.resistances if nom_composant.startswith("R") else self.condensateurs

    def realisation(self, cellule: str, cle: str, x: float) -> "Realisation":
        """Valeur(s) à câbler pour le composant `cle` de la cellule, de valeur calculée x :
        l'ajustement s'il y en a un, sinon la valeur normalisée la plus proche (ou
        l'association), sinon la valeur calculée si ce type de composant n'est pas normalisé."""
        for a in self.ajustements:
            if a.convient(cellule, cle, x):
                return Realisation(sum(a.elements), tuple(a.elements))
        serie = self.serie(cle)
        return realiser(x, serie, self.associations) if serie else Realisation(x, (x,))

    def libelle(self) -> str:
        """Description complète : « résistances E12, condensateurs E6, associations de deux valeurs »."""
        morceaux = []
        if self.resistances:
            morceaux.append(f"résistances {self.resistances} ({TOLERANCE_SERIE[self.resistances]})")
        if self.condensateurs:
            morceaux.append(f"condensateurs {self.condensateurs} ({TOLERANCE_SERIE[self.condensateurs]})")
        texte = ", ".join(morceaux)
        return texte + (", associations de deux valeurs" if self.associations else "")

    def court(self) -> str:
        """Description courte : « E12 », « R E12, C E6 », « E12 + assoc. »."""
        if self.resistances == self.condensateurs:
            texte = self.resistances or ""
        else:
            texte = ", ".join(t for t in (f"R {self.resistances}" if self.resistances else "",
                                          f"C {self.condensateurs}" if self.condensateurs else "") if t)
        return texte + (" + assoc." if self.associations else "")


@dataclass(frozen=True)
class Realisation:
    """Façon d'obtenir une valeur : une valeur normalisée, ou la somme de deux.

    Pour des résistances, la somme correspond à un montage en série ; pour des
    condensateurs, à un montage en parallèle.
    """
    valeur: float                     # valeur obtenue
    elements: Tuple[float, ...]       # valeur(s) normalisée(s) utilisée(s), la plus grande d'abord

    def texte(self, unite: str) -> str:
        """« 4,7 nF + 680 pF » ou « 10 kΩ »."""
        return " + ".join(fmt_si(v, unite, compact=True) for v in self.elements)


def valeur_normalisee(x: float, serie: str) -> float:
    """Valeur de la série E6, E12 ou E24 la plus proche de x.

    Les séries étant géométriques, l'écart se mesure en rapport (échelle
    logarithmique) : la frontière entre deux valeurs voisines a et b est leur
    moyenne géométrique √(a·b). Entre 1,0 et 1,5 (série E6), elle vaut √1,5 ≈ 1,22 :
    1,2 kΩ devient 1,0 kΩ et 1,3 kΩ devient 1,5 kΩ.
    Autres exemples : 220,8 nF -> 220 nF (E12) ; 252,8 kΩ -> 270 kΩ (E12) ou 220 kΩ (E6).
    """
    if x <= 0:
        raise ValueError("Une valeur de composant doit être positive.")
    decade = math.floor(math.log10(x))
    candidats = [v * 10.0 ** d for d in (decade - 1, decade, decade + 1) for v in SERIES_E[serie]]
    meilleur = min(candidats, key=lambda c: abs(math.log(c / x)))
    return float(f"{meilleur:.2g}")          # supprime les erreurs d'arrondi (4.7e3 = 4700.000…1)


def realiser(x: float, serie: str, associations: bool = False) -> Realisation:
    """Réalise la valeur x avec la série donnée.

    On prend la valeur normalisée la plus proche. Si elle s'écarte de plus de 1 %
    et que les associations sont permises, on cherche la meilleure somme a + b de
    deux valeurs de la série (inférieures à x), et on la garde si elle fait mieux.
    Exemples en E12 : 252,8 kΩ -> 220 kΩ + 33 kΩ ; 5,365 nF -> 4,7 nF + 680 pF.
    """
    seule = valeur_normalisee(x, serie)
    erreur = abs(math.log(seule / x))
    meilleure = Realisation(seule, (seule,))
    if not associations or erreur <= math.log(1 + SEUIL_ASSOCIATION):
        return meilleure
    decade = math.floor(math.log10(x))
    valeurs = sorted({float(f"{v * 10.0 ** d:.2g}") for d in range(decade - 3, decade + 1)
                      for v in SERIES_E[serie] if v * 10.0 ** d < x})
    for i, a in enumerate(valeurs):
        for b in valeurs[:i + 1]:                       # b ≤ a : chaque paire une seule fois
            e = abs(math.log((a + b) / x))
            if e < erreur:
                erreur, meilleure = e, Realisation(a + b, (a, b))
    return meilleure


def normaliser_montage(m: "Montage", choix: ChoixSeries) -> "Montage":
    """Copie d'un montage dont les composants sont réalisés avec les séries choisies
    (valeur la plus proche, ou valeur ajustée pour respecter le gabarit)."""
    composants, realisations = {}, {}
    for nom, v in m.composants.items():
        if choix.serie(nom):
            r = choix.realisation(m.cellule.nom, nom, v)
            composants[nom], realisations[nom] = r.valeur, r
        else:
            composants[nom] = v                         # type de composant non normalisé
    return Montage(m.cellule, m.structure, m.m, m.q, composants, m.R0, m.C0, realisations)


# =============================================================================
# 9 quater. Montage réel : µA741, pont diviseur d'entrée et nomenclature
# =============================================================================

AOP_NOM = "µA741"
AOP_GBW = 1e6          # produit gain-bande typique du µA741 (Hz)
AOP_A0 = 2e5           # gain en boucle ouverte aux basses fréquences
TL081_GBW = 3e6        # TL081 : même brochage, produit gain-bande 3 MHz
ALIMENTATION = "±15 V"


def realisation_composant(m: Montage, nom: str) -> Realisation:
    """Valeur(s) à câbler pour un composant : normalisée(s) si une série est choisie,
    sinon la valeur calculée."""
    r = m.realisations.get(nom)
    return r if r is not None else Realisation(m.composants[nom], (m.composants[nom],))


@dataclass
class Etage:
    """Un étage du montage réel, dans l'ordre de la cascade.

    composants : valeur(s) à câbler pour chaque composant de la cellule (clés internes).
        Pour la cellule qui porte le pont diviseur d'entrée (passe-bande), la résistance
        d'entrée R1 prend la valeur du pont côté entrée et « Rb » relie à la masse le
        nœud entre l'entrée et la résistance série.
    calcules : valeur calculée de chaque composant (pour les comparer aux valeurs normalisées).
    noms : désignations du montage réel (« R3 », ou « R3 », « R4 » pour une association).
    series : série utilisée pour les résistances (« R ») et les condensateurs (« C »), ou None.
    aop : amplificateur de la cellule (« U1 »), None pour une cellule RC ou CR.
    suiveur : amplificateur monté en suiveur après une cellule RC ou CR qui n'est
        pas la dernière : le calcul suppose des étages isolés les uns des autres.
    """
    montage: Montage
    composants: Dict[str, Realisation]
    calcules: Dict[str, float] = field(default_factory=dict)
    noms: Dict[str, List[str]] = field(default_factory=dict)
    series: Dict[str, Optional[str]] = field(default_factory=dict)
    aop: Optional[str] = None
    suiveur: Optional[str] = None

    @property
    def pont(self) -> bool:
        """Vrai si l'étage porte le pont diviseur d'entrée."""
        return "Rb" in self.composants

    @property
    def ordre(self) -> List[str]:
        """Clés des composants dans l'ordre de la numérotation (série, contre-réaction, masse)."""
        ordre = list(ORDRE_REEL[self.montage.structure])
        if self.pont:
            ordre.insert(ordre.index("R2") + 1, "Rb")       # après les résistances en série
        return [cle for cle in ordre if cle in self.composants]

    def designation(self, cle: str) -> str:
        """« R3 », ou « R3 + R4 » pour deux composants associés."""
        return " + ".join(self.noms[cle])

    def valeur(self, cle: str) -> str:
        """Valeur à câbler : normalisée (« 220 kΩ + 33 kΩ ») ou calculée (« 252,8 kΩ »)."""
        unite = "Ω" if cle[0] == "R" else "F"
        r = self.composants[cle]
        return r.texte(unite) if self.series.get(cle[0]) else fmt_si(r.valeur, unite, 4)

    def liste(self, genre: str) -> str:
        """Composants d'un genre (« R » ou « C ») : « R1 = 10,00 kΩ   R2 = 10,00 kΩ »."""
        return "   ".join(f"{self.designation(cle)} = {self.valeur(cle)}"
                          for cle in self.ordre if cle[0] == genre)

    def role(self, cle: str) -> str:
        """Rôle du composant dans sa cellule (« contre-réaction », « vers la masse »…)."""
        role = ROLES[self.montage.structure].get(cle, "")
        return "pont, côté entrée" if self.pont and cle == "R1" else role


def etages_reels(res: Resultat, choix: Optional[ChoixSeries] = None, pont: bool = False) -> List[Etage]:
    """Étages du montage réel : cellules, amplificateurs U1, U2…, suiveurs, et numérotation
    des composants R1, R2, R3… et C1, C2, C3… d'un bout à l'autre du montage.

    Dans chaque cellule, on numérote d'abord les éléments en série (dans l'ordre du signal),
    puis la contre-réaction (en haut), puis l'élément vers la masse (en bas) : sans
    association, les numéros impairs sont en haut et les pairs en bas. Une association de
    deux composants reçoit deux numéros qui se suivent.

    pont : pour le passe-bande, remplace la résistance d'entrée de la première cellule
    passe-bas par un pont diviseur (une résistance côté entrée, une vers la masse) qui
    ramène le gain du montage à 0 dB (option ; sans lui, les cellules restent à gain unité
    et le montage amplifie la bande passante).
    """
    montages = res.montages_serie(choix)
    att = res.attenuateur() if pont else None
    series = {"R": choix.resistances if choix is not None else None,
              "C": choix.condensateurs if choix is not None else None}
    etages: List[Etage] = []
    numero = 0
    compteurs = {"R": 0, "C": 0}
    for i, (m, exact) in enumerate(zip(montages, res.montages)):
        comp = {nom: realisation_composant(m, nom) for nom in ORDRE_COMPOSANTS if nom in m.composants}
        calcules = dict(exact.composants)
        if att and m.cellule.nom == att[0] and m.structure == "SK_PB":
            # pont diviseur d'entrée : « Ra » (côté entrée) prend la place de R1, « Rb » va à la masse
            for nom, cle, v in (("R1", "Ra", att[2]), ("Rb", "Rb", att[3])):
                comp[nom] = (choix.realisation(m.cellule.nom, cle, v) if series["R"]
                             else Realisation(v, (v,)))
                calcules[nom] = v
        etage = Etage(m, comp, calcules, series=series)
        for cle in etage.ordre:                                  # numérotation du montage réel
            genre = cle[0]
            etage.noms[cle] = []
            for _ in comp[cle].elements:
                compteurs[genre] += 1
                etage.noms[cle].append(f"{genre}{compteurs[genre]}")
        if m.structure in ("SK_PB", "SK_PH", "RAUCH"):
            numero += 1
            etage.aop = f"U{numero}"
        elif i < len(montages) - 1:
            numero += 1
            etage.suiveur = f"U{numero}"
        etages.append(etage)
    return etages


def ecart_etages(etages: List[Etage]) -> Tuple[float, str, str]:
    """Plus grand écart relatif entre une valeur à câbler et sa valeur calculée.
    Renvoie (écart, désignation, cellule)."""
    pire = (0.0, "", "")
    for e in etages:
        for cle, r in e.composants.items():
            ecart = abs(r.valeur / e.calcules[cle] - 1)
            if ecart > pire[0]:
                pire = (ecart, e.designation(cle), e.montage.cellule.nom)
    return pire


def premiere_association(etages: List[Etage]) -> Optional[str]:
    """Désignation de la première association de deux valeurs du montage (« C1 + C2 »),
    ou None s'il n'y en a pas."""
    return next((e.designation(cle) for e in etages for cle in e.ordre
                 if len(e.composants[cle].elements) > 1), None)


def amplificateurs(etages: List[Etage]) -> List[str]:
    """Repères de tous les amplificateurs du montage (« U1 », « U2 »…)."""
    return [u for e in etages for u in (e.aop, e.suiveur) if u]


def _plage(reperes: List[str]) -> str:
    """« U1 », « U1 et U2 », « U1 à U4 »."""
    if len(reperes) == 1:
        return reperes[0]
    if len(reperes) == 2:
        return f"{reperes[0]} et {reperes[1]}"
    return f"{reperes[0]} à {reperes[-1]}"


@dataclass
class LigneNomenclature:
    """Une ligne de la liste des composants à réunir pour câbler le filtre."""
    categorie: str        # « Résistances », « Condensateurs », « Circuits intégrés », « Découplage »
    valeur: str           # « 10 kΩ », « µA741 »…
    quantite: int
    reperes: str          # « R1, R2, R5 » ou « R1 à R4 »


def liste_reperes(noms: List[str]) -> str:
    """« R1, R2, R5 » ; trois numéros ou plus qui se suivent : « R1 à R4 »."""
    numeros = sorted({int(n[1:]) for n in noms})
    if not numeros:
        return ""
    genre = noms[0][0]
    suites: List[List[int]] = []                  # [premier, dernier] des numéros qui se suivent
    for n in numeros:
        if suites and n == suites[-1][1] + 1:
            suites[-1][1] = n
        else:
            suites.append([n, n])
    morceaux: List[str] = []
    for debut, fin in suites:
        if fin - debut >= 2:
            morceaux.append(f"{genre}{debut} à {genre}{fin}")
        else:
            morceaux += [f"{genre}{k}" for k in range(debut, fin + 1)]
    return ", ".join(morceaux)


def nomenclature(etages: List[Etage], choix: Optional[ChoixSeries] = None) -> List[LigneNomenclature]:
    """Composants à réunir, regroupés par valeur, avec leur quantité et leurs repères
    (numérotation du montage réel).

    Une association « a + b » compte pour deux composants. Les valeurs calculées
    (sans série) sont données avec 4 chiffres significatifs.
    """
    groupes: Dict[Tuple[str, float], List[str]] = {}
    for e in etages:
        for cle, r in e.composants.items():
            for v, nom in zip(r.elements, e.noms[cle]):
                groupes.setdefault((cle[0], float(f"{v:.4g}")), []).append(nom)
    lignes = []
    for genre, categorie, unite in (("R", "Résistances", "Ω"), ("C", "Condensateurs", "F")):
        normalise = choix is not None and bool(choix.resistances if genre == "R" else choix.condensateurs)
        for (g, v) in sorted(k for k in groupes if k[0] == genre):
            noms = groupes[(g, v)]
            texte = fmt_si(v, unite, compact=True) if normalise else fmt_si(v, unite, 4)
            lignes.append(LigneNomenclature(categorie, texte, len(noms), liste_reperes(noms)))
    aops = amplificateurs(etages)
    if aops:
        lignes.append(LigneNomenclature("Circuits intégrés", AOP_NOM, len(aops), _plage(aops)))
        lignes.append(LigneNomenclature("Découplage", "100 nF", 2 * len(aops),
                                        "broches 7 et 4 de chaque circuit"))
    return lignes


EXCURSION_SORTIE = 13.0     # amplitude de sortie d'un µA741 alimenté en ±15 V (V crête, environ)


def entree_maximale(res: Resultat, etages: List[Etage], choix: Optional[ChoixSeries] = None
                    ) -> Tuple[float, Optional[str], str]:
    """Amplitude d'entrée (V crête) au-delà de laquelle la sortie d'un amplificateur sature.

    On suit le signal d'étage en étage (amplificateurs idéaux, pont diviseur compris)
    et on cherche, pour chaque sortie d'amplificateur, le plus grand gain sur toutes
    les fréquences : les cellules à Q élevé amplifient près de leur résonance.
    Renvoie (amplitude, repère de l'amplificateur, position : « 1re cellule »…).
    """
    f = res.norm.f_ref * np.logspace(-2, 2, 4001)
    w = 2 * np.pi * f
    att = res.attenuateur()
    h = np.ones(w.shape, dtype=complex)
    limite, repere, position = float("inf"), None, ""
    for rang, e in enumerate(etages, start=1):
        h = h * e.montage.reponse(w)
        if e.pont and att:
            h = h * att[1]                           # α = Rb/(Ra + Rb) : signal divisé à l'entrée
        u = e.aop or e.suiveur
        if u:
            v = EXCURSION_SORTIE / float(np.max(np.abs(h)))
            if v < limite:
                cellule = f"cellule {e.montage.cellule.nom}"
                position = cellule + (", sortie du filtre" if rang == len(etages) else
                                      f", {rang}e étage" if rang > 1 else ", 1er étage")
                limite, repere = v, u
    return limite, repere, position


def notes_cablage(res: Resultat, etages: List[Etage], choix: Optional[ChoixSeries] = None) -> List[str]:
    """Remarques pratiques pour câbler et essayer le montage."""
    notes = [f"Alimentation symétrique {ALIMENTATION} (±12 V convient aussi) : broche 7 au +15 V, "
             "broche 4 au −15 V, masse commune à tous les étages.",
             "Découplage : 100 nF entre la broche 7 et la masse et 100 nF entre la broche 4 et la masse, "
             f"au plus près de chaque {AOP_NOM}. Broches 1, 5 (réglage d'offset) et 8 : non connectées."]
    att = res.attenuateur()
    if att and not any(e.pont for e in etages):
        gain = res.gain_montage()
        notes.append(f"Sans pont diviseur, le montage a un gain de {fmt_nombre(20 * math.log10(gain), 3)} dB "
                     "à f0 (cellules à gain unité). L'option « pont diviseur » le ramène à 0 dB.")
    limite, repere, position = entree_maximale(res, etages, choix)
    if repere:
        notes.append(f"Entrée maximale avant saturation (sorties des {AOP_NOM} limitées à ±13 V environ) : "
                     f"{fmt_si(limite, 'V', 3)} crête, imposée par {repere} ({position}).")
    for e in etages:
        nom = e.montage.cellule.nom
        if e.pont:
            R1 = e.montage.composants["R1"]
            gain = 20 * math.log10(res.gain_montage())
            notes.append(f"Pont diviseur d'entrée de la cellule {nom} : {e.designation('R1')} (côté entrée) et "
                         f"{e.designation('Rb')} (vers la masse, au nœud entre {e.designation('R1')} et "
                         f"{e.designation('R2')}) remplacent la résistance d'entrée de {fmt_si(R1, 'Ω', 4)} et "
                         f"ramènent le gain à 0 dB dans la bande passante (sans le pont : "
                         f"{fmt_nombre(gain, 3)} dB à f0).")
        if e.montage.structure == "RAUCH":
            notes.append(f"La cellule {nom} (Rauch) est un montage inverseur : gain −1/2 à f0, "
                         "sortie en opposition de phase.")
        if e.suiveur:
            notes.append(f"{e.suiveur} est monté en suiveur : il isole la cellule {nom} de la suivante, "
                         "qui sinon la chargerait et modifierait la réponse.")
    dernier = etages[-1] if etages else None
    if dernier is not None and dernier.aop is None and dernier.suiveur is None:
        notes.append(f"La sortie de la cellule {dernier.montage.cellule.nom} n'est pas tamponnée : "
                     "chargez-la par une impédance élevée (100 kΩ ou plus) ou ajoutez un suiveur.")
    # Effet du produit gain-bande fini du µA741 (estimation avec le modèle à un pôle)
    ideal = (res.points_controle(lambda f: res.H_serie(f, choix)) if choix is not None and choix.actif
             else res.points_controle())
    reel = res.points_controle_aop(choix)
    ecart = fmt_compact(max(abs(a.G - b.G) for a, b in zip(ideal, reel)), 2)

    def gains(points):
        return ", ".join(f"G({p.nom}) = {fmt_nombre(p.G, 3)} dB" for p in points if p.passante)
    debut = f"Avec de vrais {AOP_NOM} (produit gain-bande 1 MHz)"
    if all(p.ok for p in reel):
        texte = (f"{debut}, le gabarit reste respecté : {gains(reel)} "
                 f"(écart de {ecart} dB au plus avec l'amplificateur idéal).")
    else:
        texte = (f"{debut} : {gains(reel)}, hors gabarit (écart de {ecart} dB avec l'amplificateur idéal"
                 + ("" if all(p.ok for p in ideal) else " ; les valeurs choisies sortaient déjà du gabarit")
                 + ").")
        if max(abs(a.G - b.G) for a, b in zip(ideal, reel)) > 0.1:
            tl081 = res.points_controle(lambda f: res.H_aop(f, choix, gbw=TL081_GBW))
            texte += (f" Avec des TL081 (même brochage, 3 MHz) : {gains(tl081)}, "
                      + ("gabarit respecté." if all(p.ok for p in tl081) else "écart réduit mais toujours hors gabarit."))
    notes.append(texte)
    return notes


# Dispersion des composants : tolérance de chaque série, et tolérances supposées pour les
# valeurs calculées (résistances à couche ±5 %, condensateurs ±10 %, les plus courants).
TOLERANCE_NUMERIQUE = {"E6": 0.20, "E12": 0.10, "E24": 0.05}
TOLERANCE_DEFAUT = {"R": 0.05, "C": 0.10}


def tolerances(choix: Optional[ChoixSeries] = None) -> Tuple[float, float]:
    """(tolérance des résistances, tolérance des condensateurs), en valeur relative."""
    serie_R = choix.resistances if choix is not None else None
    serie_C = choix.condensateurs if choix is not None else None
    return (TOLERANCE_NUMERIQUE.get(serie_R, TOLERANCE_DEFAUT["R"]),
            TOLERANCE_NUMERIQUE.get(serie_C, TOLERANCE_DEFAUT["C"]))


@dataclass
class Dispersion:
    """Montages tirés au hasard dans les tolérances des composants."""
    gain_min: np.ndarray        # enveloppe du gain (dB) aux fréquences demandées
    gain_max: np.ndarray
    rendement: float            # proportion des montages qui respectent le gabarit
    tirages: int
    tol_R: float
    tol_C: float
    echecs: Dict[str, float] = field(default_factory=dict)   # limite -> proportion des montages hors gabarit


def dispersion(res: Resultat, f, choix: Optional[ChoixSeries] = None, tirages: int = 300,
               graine: int = 2024, tol: Optional[Tuple[float, float]] = None) -> Optional[Dispersion]:
    """Chaque composant est tiré au hasard (loi uniforme) dans sa tolérance, pour `tirages`
    montages ; on garde l'enveloppe du gain aux fréquences f et la proportion des montages qui
    respectent le gabarit (amplificateurs idéaux). Le tirage est toujours le même (graine fixe) :
    le dessin ne change pas d'un affichage à l'autre."""
    if not res.montages:
        return None
    tol_R, tol_C = tol if tol is not None else tolerances(choix)
    rng = np.random.default_rng(graine)
    base = res.montages_serie(choix)
    pont = res.pont_reel(choix)
    echelle = res.K / np.prod([m.gain_propre for m in res.montages])
    tires = []
    for m in base:
        composants = {}
        for nom, valeur in m.composants.items():
            tol = tol_R if nom[0] == "R" else tol_C
            composants[nom] = valeur * (1 + tol * rng.uniform(-1, 1, (tirages, 1)))
        if pont is not None and m.cellule.nom == pont[0] and m.structure == "SK_PB":
            # pont diviseur normalisé : ses deux résistances sont tirées chacune dans leur tolérance
            ra = pont[1].valeur * (1 + tol_R * rng.uniform(-1, 1, (tirages, 1)))
            rb = pont[2].valeur * (1 + tol_R * rng.uniform(-1, 1, (tirages, 1)))
            composants["R1"] = ra * rb / (ra + rb)
            echelle = echelle * (rb / (ra + rb)) / res.attenuateur()[1]
        tires.append(Montage(m.cellule, m.structure, m.m, m.q, composants, m.R0, m.C0))

    def gains(frequences) -> np.ndarray:
        w = 2 * np.pi * np.asarray(frequences, dtype=float)
        h = np.ones((tirages, w.size), dtype=complex)
        for m in tires:
            h = h * m.reponse(w)
        return 20 * np.log10(np.maximum(np.abs(h * echelle), 1e-300))

    g = gains(f)
    points = res.points_controle()
    g_points = gains([p.f for p in points])
    respecte = np.ones(tirages, dtype=bool)
    echecs = {}
    for j, p in enumerate(points):
        if p.passante:
            bon = g_points[:, j] >= p.limite - TOLERANCE_GABARIT_DB
        else:
            bon = g_points[:, j] <= p.limite + TOLERANCE_GABARIT_DB
        respecte &= bon
        echecs[p.nom] = float(1 - bon.mean())
    return Dispersion(g.min(axis=0), g.max(axis=0), float(respecte.mean()), tirages, tol_R, tol_C, echecs)


def bilan_dispersion(res: Resultat, d: Dispersion, choix: Optional[ChoixSeries] = None) -> str:
    """Phrase qui résume la dispersion (légende du Bode réel)."""
    pourcent = lambda x: f"{round(100 * x)} %"          # noqa: E731
    texte = (f"Zone colorée : {d.tirages} montages dont chaque composant est tiré au hasard dans sa "
             f"tolérance (R ±{fmt_compact(100 * d.tol_R)} %, C ±{fmt_compact(100 * d.tol_C)} %) ; "
             f"{pourcent(d.rendement)} des montages respectent le gabarit.")
    if d.rendement < 0.995 and d.echecs:
        nom = max(d.echecs, key=d.echecs.get)
        serie = choix is not None and choix.actif
        nominaux = res.points_controle_serie(choix) if serie else res.points_controle()
        point = next(p for p in nominaux if p.nom == nom)
        texte += (f" La limite la plus souvent dépassée est G({nom}) {'≥' if point.passante else '≤'} "
                  f"{fmt_compact(point.limite)} dB ({pourcent(d.echecs[nom])} des montages)")
        marge = point.G - point.limite if point.passante else point.limite - point.G
        if marge < -TOLERANCE_GABARIT_DB:
            texte += (f" : avec les valeurs {'normalisées' if serie else 'nominales'}, elle est déjà dépassée "
                      f"(G({nom}) = {fmt_nombre(point.G, 3)} dB).")
        elif marge < 0.1:
            conseil = ("une bande passante un peu plus large que demandé" if point.passante
                       else "une atténuation Ga un peu plus forte que demandé")
            texte += (" : le calcul place le gain sur cette limite, sans marge. Pour un vrai montage, "
                      f"calculez avec {conseil}.")
        else:
            texte += f" ({fmt_compact(marge, 2)} dB de marge dans le calcul)."
        precis = dispersion(res, [p.f for p in res.points_controle()], choix, tol=(0.01, 0.01))
        if precis is not None and precis.rendement > d.rendement + 0.05:
            texte += f" Avec des composants à ±1 % : {pourcent(precis.rendement)}."
    return texte


def bilan_aop(res: Resultat, choix: Optional[ChoixSeries] = None) -> Tuple[bool, str]:
    """Effet de vrais µA741 sur le gabarit, en une phrase (légende du Bode réel).

    Renvoie (gabarit respecté avec les µA741, phrase).
    """
    serie = choix is not None and choix.actif
    ideal = res.points_controle_serie(choix) if serie else res.points_controle()
    reel = res.points_controle_aop(choix if serie else None)
    ecart = max(abs(a.G - b.G) for a, b in zip(ideal, reel))
    if all(p.ok for p in reel):
        return True, (f"Avec de vrais {AOP_NOM} (courbe violette), le gabarit reste respecté : écart de "
                      f"{fmt_compact(ecart, 2)} dB au plus avec l'amplificateur idéal.")
    hors = ", ".join(f"G({p.nom}) = {fmt_nombre(p.G, 3)} dB" for p in reel if not p.ok)
    texte = (f"Avec de vrais {AOP_NOM} (courbe violette) : {hors}, hors gabarit "
             f"(écart de {fmt_compact(ecart, 2)} dB avec l'amplificateur idéal).")
    if all(p.ok for p in ideal):
        tl081 = res.points_controle(lambda f: res.H_aop(f, choix if serie else None, gbw=TL081_GBW))
        texte += (" Des TL081 (3 MHz, même brochage) le respectent." if all(p.ok for p in tl081)
                  else " Des TL081 (3 MHz, même brochage) réduisent l'écart.")
    elif serie:
        texte += " Les valeurs normalisées sortaient déjà du gabarit avec un amplificateur idéal."
    return False, texte


# =============================================================================
# 9 quinquies. Correction du gabarit avec les valeurs normalisées
# =============================================================================
# Le calcul place le gain exactement à Gp en fp : l'arrondi des valeurs suffit souvent à
# franchir la limite. La correction cherche d'autres valeurs normalisées qui respectent le
# gabarit, sans jamais changer les valeurs de référence R0 et C0 :
#   1. pour chaque composant, une autre valeur de sa série (celle du dessous ou du dessus,
#      ou une voisine à moins de 12 %) ou, si elles sont permises, une autre association ;
#   2. si cela ne suffit pas, les associations de deux valeurs ;
#   3. puis des séries plus fines (E6 → E12 → E24), la plus grossière d'abord.

ORDRE_SERIES = ("E6", "E12", "E24")
CORRECTION_MARGE = 0.1         # marge visée (dB) : au-delà, on préfère changer moins de composants
CORRECTION_BOSSE = 0.3         # dans la bande passante, le gain ne dépasse pas 0 dB de plus (dB)
CORRECTION_COUT = 0.004        # « prix » d'un composant changé, en dB de marge
CORRECTION_COUT_ECART = 0.0005  # à marge égale, les valeurs les plus proches du calcul
CORRECTION_CANDIDATS = 7       # réalisations essayées par composant, au plus


@dataclass
class Changement:
    """Un composant dont la valeur à câbler change avec la correction."""
    cellule: str
    designation: str           # repère avec la correction (« R3 », « R3 + R4 »)
    role: str
    avant: str                 # valeur à câbler avant la correction
    apres: str                 # valeur à câbler avec la correction


@dataclass
class Correction:
    """Résultat de corriger_gabarit : valeurs proposées, ou None si rien ne convient."""
    depart: ChoixSeries
    choix: Optional[ChoixSeries]
    changements: List[Changement] = field(default_factory=list)
    points: List[PointControle] = field(default_factory=list)    # gabarit avec les valeurs proposées
    marge: float = 0.0          # marge la plus faible (dB) sur toute la bande (−0,02 dB toléré)

    @property
    def trouvee(self) -> bool:
        return self.choix is not None

    def leviers(self) -> List[str]:
        """Séries ou options changées : « associations de deux valeurs », « condensateurs E12 »…"""
        if self.choix is None:
            return []
        d, c = self.depart, self.choix
        leviers = []
        if c.associations and not d.associations:
            leviers.append("associations de deux valeurs")
        if c.resistances != d.resistances:
            leviers.append(f"résistances {c.resistances}")
        if c.condensateurs != d.condensateurs:
            leviers.append(f"condensateurs {c.condensateurs}")
        return leviers


def _valeurs_serie(x: float, serie: str) -> List[float]:
    """Valeurs de la série autour de x (de trois décades en dessous à une au-dessus)."""
    d = math.floor(math.log10(x))
    return sorted({float(f"{v * 10.0 ** e:.2g}") for e in range(d - 3, d + 2) for v in SERIES_E[serie]})


def _candidats(x: float, serie: str, associations: bool) -> List[Realisation]:
    """Réalisations essayées pour la valeur calculée x. La première est celle de départ (la
    plus proche, comme normaliser_montage) ; viennent ensuite les valeurs de la série juste en
    dessous et juste au-dessus, puis les plus proches des autres valeurs à moins de 12 % et,
    si elles sont permises, des associations à moins de 3 %."""
    valeurs = _valeurs_serie(x, serie)
    depart = realiser(x, serie, associations)
    candidats = {depart.elements: depart}
    dessous = max(v for v in valeurs if v <= x * (1 + 1e-12))
    dessus = min(v for v in valeurs if v >= x * (1 - 1e-12))
    for v in (dessous, dessus):
        candidats.setdefault((v,), Realisation(v, (v,)))
    autres = [(abs(math.log(v / x)), (v,)) for v in valeurs if abs(math.log(v / x)) <= math.log(1.12)]
    if associations:
        petites = [v for v in valeurs if v < x]
        for i, a in enumerate(petites):
            for b in petites[:i + 1]:
                e = abs(math.log((a + b) / x))
                if e < math.log(1.03):
                    autres.append((e, (a, b)))
    for _, elements in sorted(autres):
        if len(candidats) >= CORRECTION_CANDIDATS:
            break
        candidats.setdefault(elements, Realisation(sum(elements), elements))
    return list(candidats.values())


class _Combinaisons:
    """Toutes les combinaisons de réalisations des composants d'une cellule (et de son pont
    diviseur d'entrée) : gain de la cellule (dB) aux fréquences contrôlées, nombre de composants
    changés et écart total aux valeurs calculées. La combinaison 0 est celle de départ."""

    def __init__(self, m: Montage, choix: ChoixSeries, w: np.ndarray,
                 pont: Optional[Tuple[str, float, float, float]] = None):
        self.m = m
        self.cles = [k for k in m.composants if not (pont and k == "R1")]
        self.calc = {k: m.composants[k] for k in self.cles}
        if pont:                     # Ra (côté entrée) et Rb (vers la masse) remplacent R1
            self.calc["Ra"], self.calc["Rb"] = pont[2], pont[3]
            self.cles += ["Ra", "Rb"]
        self.listes: List[List[Realisation]] = []
        for k in self.cles:
            x = self.calc[k]
            serie = choix.serie(k)
            self.listes.append(_candidats(x, serie, choix.associations) if serie else [Realisation(x, (x,))])
        self.idx = np.array(list(itertools.product(*[range(len(l)) for l in self.listes])), dtype=int)
        valeurs: Dict[str, np.ndarray] = {}
        self.changes = np.zeros(len(self.idx))
        self.ecart = np.zeros(len(self.idx))
        for j, k in enumerate(self.cles):
            v = np.array([r.valeur for r in self.listes[j]])
            valeurs[k] = v[self.idx[:, j]][:, None]
            self.changes += (self.idx[:, j] > 0)
            self.ecart += np.abs(np.log(v / self.calc[k]))[self.idx[:, j]]
        gain = 0.0
        if pont:
            Ra, Rb = valeurs.pop("Ra"), valeurs.pop("Rb")
            valeurs["R1"] = Ra * Rb / (Ra + Rb)
            gain = 20 * np.log10((Rb / (Ra + Rb)) / pont[1])
        essai = Montage(m.cellule, m.structure, m.m, m.q, valeurs, m.R0, m.C0)
        self.G = 20 * np.log10(np.maximum(np.abs(essai.reponse(w[None, :])), 1e-300)) + gain


def _contraintes(res: Resultat) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fréquences contrôlées par la correction, sens (+1 : G ≥ limite, −1 : G ≤ limite) et
    limites (dB). Bande passante (11 points) : G ≥ Gp partout, pas seulement aux bords, et
    G ≤ CORRECTION_BOSSE (pas de bosse marquée) ; bande atténuée : G ≤ Ga, aux fréquences
    limites et au-delà."""
    g = res.gabarit
    if g.type == "PB":
        bandes, attenuees = [np.geomspace(g.fp / 10, g.fp, 11)], [np.geomspace(g.fa, 4 * g.fa, 5)]
    elif g.type == "PH":
        bandes, attenuees = [np.geomspace(g.fp, 10 * g.fp, 11)], [np.geomspace(g.fa / 4, g.fa, 5)]
    else:
        bandes = [np.geomspace(g.fp_moins, g.fp_plus, 11)]
        attenuees = [np.geomspace(g.fa_moins / 4, g.fa_moins, 5), np.geomspace(g.fa_plus, 4 * g.fa_plus, 5)]
    f: List[float] = []
    sens: List[float] = []
    limites: List[float] = []
    for b in bandes:
        f += list(b) * 2
        sens += [1.0] * len(b) + [-1.0] * len(b)
        limites += [g.Gp] * len(b) + [CORRECTION_BOSSE] * len(b)
    for a in attenuees:
        f += list(a)
        sens += [-1.0] * len(a)
        limites += [g.Ga] * len(a)
    return np.array(f), np.array(sens), np.array(limites)


def _optimiser(res: Resultat, choix: ChoixSeries) -> Tuple[float, Tuple[Ajustement, ...]]:
    """Meilleures valeurs pour ces séries : (marge la plus faible en dB, ajustements).

    On part des valeurs les plus proches. Puis, cellule par cellule, on essaie toutes les
    combinaisons de ses candidats et on garde celle qui améliore le plus l'objectif : la marge
    la plus faible (plafonnée à CORRECTION_MARGE), moins un petit prix par composant changé.
    On recommence tant que l'objectif s'améliore."""
    f, sens, limites = _contraintes(res)
    w = 2 * np.pi * f
    att = res.attenuateur() if choix.pont else None
    blocs = [_Combinaisons(m, choix, w, att if (att and m.cellule.nom == att[0] and m.structure == "SK_PB")
                           else None) for m in res.montages]
    G = 20 * math.log10(abs(res.K / np.prod([m.gain_propre for m in res.montages]))) + sum(b.G[0] for b in blocs)
    n, e = 0.0, float(sum(b.ecart[0] for b in blocs))
    etat = [0] * len(blocs)

    def objectif(G, n, e):
        marge = np.min(sens * (G - limites), axis=-1)
        return np.minimum(marge, CORRECTION_MARGE) - CORRECTION_COUT * n - CORRECTION_COUT_ECART * e, marge

    J = float(objectif(G, n, e)[0])
    for _ in range(12):
        ameliore = False
        for k, b in enumerate(blocs):
            i = etat[k]
            Gk, nk, ek = G - b.G[i], n - b.changes[i], e - b.ecart[i]
            Jc, _ = objectif(Gk[None, :] + b.G, nk + b.changes, ek + b.ecart)
            j = int(np.argmax(Jc))
            if Jc[j] > J + 1e-12:
                etat[k] = j
                G, n, e, J = Gk + b.G[j], nk + b.changes[j], ek + b.ecart[j], float(Jc[j])
                ameliore = True
        if not ameliore:
            break
    marge = float(objectif(G, n, e)[1])
    ajustements = tuple(Ajustement(b.m.cellule.nom, k, float(b.calc[k]),
                                   tuple(float(x) for x in b.listes[j][b.idx[i, j]].elements))
                        for b, i in zip(blocs, etat) for j, k in enumerate(b.cles) if b.idx[i, j] > 0)
    return marge, ajustements


def _configurations(choix: ChoixSeries) -> List[ChoixSeries]:
    """Séries et options à essayer, de la plus simple à la plus coûteuse : celles choisies,
    puis les associations, puis des séries plus fines (d'abord la plus grossière)."""
    def plus_fines(serie: Optional[str]) -> List[Optional[str]]:
        return [None] if serie is None else list(ORDRE_SERIES[ORDRE_SERIES.index(serie):])

    def pas(avant: Optional[str], apres: Optional[str]) -> int:
        return ORDRE_SERIES.index(apres) - ORDRE_SERIES.index(avant) if avant else 0

    essais = []
    for R in plus_fines(choix.resistances):
        for C in plus_fines(choix.condensateurs):
            for a in sorted({choix.associations, True}):
                cout = 2 * pas(choix.resistances, R) + 2 * pas(choix.condensateurs, C) \
                    + (1 if a and not choix.associations else 0)
                plus_fine = max(ORDRE_SERIES.index(s) for s in (R, C) if s)
                essais.append((cout, plus_fine, a, ChoixSeries(R, C, a, choix.pont)))
    essais.sort(key=lambda t: t[:3])
    return [t[3] for t in essais]


def corriger_gabarit(res: Resultat, choix: ChoixSeries) -> Correction:
    """Cherche des valeurs normalisées qui respectent le gabarit, sans changer R0 ni C0.

    Les configurations sont essayées dans l'ordre de _configurations ; on garde la première
    qui respecte le gabarit sur toute la bande (voir _contraintes). La correction indique les
    composants dont la valeur à câbler change par rapport à `choix`."""
    if choix is None or not choix.actif or not res.montages:
        return Correction(choix, None)
    for essai in _configurations(replace(choix, ajustements=())):
        marge, ajustements = _optimiser(res, essai)
        if marge >= -TOLERANCE_GABARIT_DB:       # même tolérance que le contrôle du gabarit
            proposee = replace(essai, ajustements=ajustements)
            return Correction(choix, proposee, changements_valeurs(res, choix, proposee),
                              res.points_controle_serie(proposee), marge)
    return Correction(choix, None)


def changements_valeurs(res: Resultat, avant: ChoixSeries, apres: ChoixSeries) -> List[Changement]:
    """Composants dont la valeur à câbler n'est pas la même avec `avant` et avec `apres`
    (repères, rôles et valeurs du montage réel, dans l'ordre de câblage)."""
    anciens = {(e.montage.cellule.nom, cle): e for e in etages_reels(res, avant, avant.pont) for cle in e.ordre}
    changements = []
    for e in etages_reels(res, apres, apres.pont):
        for cle in e.ordre:
            ancien = anciens.get((e.montage.cellule.nom, cle))
            if ancien is not None and ancien.composants[cle].elements != e.composants[cle].elements:
                changements.append(Changement(e.montage.cellule.nom, e.designation(cle), e.role(cle),
                                              ancien.valeur(cle), e.valeur(cle)))
    return changements


def composants_ajustes(res: Resultat, choix: Optional[ChoixSeries], pont: bool = False
                       ) -> List[Tuple[Etage, str, Realisation]]:
    """Composants dont la valeur à câbler est un ajustement (correction du gabarit) :
    (étage, clé, valeur normalisée la plus proche, qu'il remplace)."""
    if choix is None or not choix.ajustements:
        return []
    proches = {(e.montage.cellule.nom, cle): e.composants[cle]
               for e in etages_reels(res, replace(choix, ajustements=()), pont) for cle in e.ordre}
    ajustes = []
    for e in etages_reels(res, choix, pont):
        for cle in e.ordre:
            proche = proches.get((e.montage.cellule.nom, cle))
            if proche is not None and proche.elements != e.composants[cle].elements:
                ajustes.append((e, cle, proche))
    return ajustes


def phrase_ajustements(res: Resultat, choix: Optional[ChoixSeries], pont: bool = False) -> str:
    """Valeurs ajustées pour respecter le gabarit, en une phrase ("" s'il n'y en a pas)."""
    ajustes = composants_ajustes(res, choix, pont)
    if not ajustes:
        return ""
    def lie(texte: str) -> str:                # « R1 + R2 », « 270 kΩ + 39 kΩ » : jamais coupés
        return texte.replace(" + ", "\u00a0+\u00a0")
    morceaux = [f"{lie(e.designation(cle))} = {lie(e.valeur(cle))} (au lieu de "
                f"{lie(proche.texte('Ω' if cle[0] == 'R' else 'F'))})" for e, cle, proche in ajustes]
    return ("Valeurs ajustées pour respecter le gabarit, à la place de la valeur normalisée la plus proche "
            "(R0 et C0 inchangés) : " + ", ".join(morceaux) + ".")


def signature_calcul(res: Resultat) -> str:
    """Identifie le calcul : type de filtre et valeurs du gabarit, R0 et C0 compris. Les valeurs
    ajustées par la correction ne valent que pour le calcul qui les a produites."""
    g = res.gabarit
    return ";".join(f"{nom}={repr(float(v)) if isinstance(v, (int, float)) else v}"
                    for nom in ("type", "Gp", "Ga", "fp", "fa", "fp_moins", "fp_plus", "fa_moins", "fa_plus",
                                "R0", "C0")
                    for v in [getattr(g, nom)])


def ajustements_valides(res: Resultat, ajustements: Tuple[Ajustement, ...]) -> bool:
    """Vrai si chaque ajustement porte sur un composant du calcul actuel, de même valeur calculée
    (sinon le calcul a changé depuis la correction)."""
    att = res.attenuateur()
    for a in ajustements:
        m = next((m for m in res.montages if m.cellule.nom == a.cellule), None)
        if m is None:
            return False
        if a.cle in ("Ra", "Rb"):
            if att is None or att[0] != a.cellule:
                return False
            valeur = att[2] if a.cle == "Ra" else att[3]
        elif a.cle in m.composants:
            valeur = m.composants[a.cle]
        else:
            return False
        if not a.convient(a.cellule, a.cle, valeur):
            return False
    return True


# =============================================================================
# 10. Écriture des fonctions de transfert et rapport texte
# =============================================================================

def nom_indice(nom: str, style: str = "texte") -> str:
    """Indice d'une cellule : « 1 bis » -> H1bis (texte) ou H_{1\\,\\mathrm{bis}} (tex)."""
    if style == "texte":
        return nom.replace(" ", "")
    return nom.replace(" bis", r"\,\mathrm{bis}")


def facteurs_prototype(res: Resultat, style: str = "texte") -> List[str]:
    """Facteurs du polynôme de Butterworth normalisé : « p² + 1,6180p + 1 »…"""
    facteurs = []
    for c in res.prototype:
        _, den = c.polynomes()
        facteurs.append(ecrire_polynome(den, lambda a: _decimales(a, style), style))
    return facteurs


def _decimales(a: float, style: str) -> str:
    """Coefficient du prototype avec 4 décimales."""
    s = fmt_decimales(a, 4)
    return s.replace(",", "{,}").replace("−", "-") if style == "tex" else s


def fraction_cellule(c: Cellule, style: str = "texte") -> Tuple[str, str]:
    """(numérateur, dénominateur) d'une cellule réelle, coefficients en unités SI."""
    num, den = c.polynomes()
    formater = lambda a: fmt_sci(a, 4, style)     # noqa: E731
    return ecrire_polynome(num, formater, style), ecrire_polynome(den, formater, style)


def texte_transposition(res: Resultat) -> str:
    """Changement de variable utilisé (transposition), en texte simple."""
    t = res.gabarit.type
    w = fmt_sci(res.w_ref, 4)
    if t == "PB":
        return f"p → p/ωp   avec ωp = 2π·fp = {w} rad/s"
    if t == "PH":
        return f"p → ωp/p   avec ωp = 2π·fp = {w} rad/s"
    B = fmt_nombre(res.norm.B, 4)
    if t == "PM":
        return f"p → (1/B)·(p/ω0 + ω0/p)   avec B = {B} et ω0 = 2π·f0 = {w} rad/s"
    return f"p → B / (p/ω0 + ω0/p)   avec B = {B} et ω0 = 2π·f0 = {w} rad/s"


def fonction_reelle_finale(res: Resultat, style: str = "texte") -> Tuple[str, List[str], List[str]]:
    """Fonction de transfert réelle sous sa forme finale, H(p) = K·N(p) / Π Dᵢ(p), coefficients
    en unités SI (p en rad/s).

    Renvoie (numérateur, facteurs du numérateur, facteurs du dénominateur). Les numérateurs
    des cellules passe-bas, passe-haut et passe-bande sont des monômes : leur produit est
    écrit en un seul terme (« 1 », « 8,412·10⁻¹⁷p⁴ »…), et la liste des facteurs du
    numérateur est vide. Pour le coupe-bande, chaque cellule apporte un facteur (p²/ωz² + 1) :
    le numérateur est alors "" et ses facteurs sont listés. K n'est pas compris (voir res.K).
    """
    formater = lambda a: fmt_sci(a, 4, style)     # noqa: E731
    coefficient, puissance = 1.0, 0
    facteurs_num: List[str] = []
    facteurs_den: List[str] = []
    for c in res.cellules:
        num, den = c.polynomes()
        facteurs_den.append(ecrire_polynome(den, formater, style))
        termes = [i for i, a in enumerate(num) if abs(a) > 1e-300]
        if len(termes) == 1:                           # monôme a·pᵏ
            coefficient *= num[termes[0]]
            puissance += len(num) - 1 - termes[0]
        else:
            facteurs_num.append(ecrire_polynome(num, formater, style))
    numerateur = "" if facteurs_num else ecrire_polynome([coefficient] + [0.0] * puissance, formater, style)
    return numerateur, facteurs_num, facteurs_den


def texte_fonction_finale(res: Resultat) -> str:
    """H(p) sous sa forme finale, sur une ligne (texte simple) : « H(p) = 1 / [(…)·(…)] »."""
    numerateur, facteurs_num, facteurs_den = fonction_reelle_finale(res)
    num = "·".join(f"({f})" for f in facteurs_num) if facteurs_num else numerateur
    den = "·".join(f"({f})" for f in facteurs_den)
    den = f"[{den}]" if len(facteurs_den) > 1 else den
    avec_K = abs(res.K - 1) > 1e-9
    return (f"H(p) = {'K·' if avec_K else ''}{num} / {den}"
            + (f"   avec K = {fmt_sci(res.K, 4)}" if avec_K else ""))


def lignes_fonction_reelle(res: Resultat) -> List[str]:
    """Fonction de transfert réelle : forme finale, puis une cellule par ligne (texte simple)."""
    lignes = [texte_fonction_finale(res), "dont les cellules :"]
    for c in res.cellules:
        num, den = fraction_cellule(c)
        nom = f"H{nom_indice(c.nom)}(p)"
        lignes.append("  " + (f"{nom} = ({num}) / ({den})" if "+" in num else f"{nom} = {num} / ({den})"))
    return lignes


def phrase_pont(res: Resultat, pont: bool, choix: Optional["ChoixSeries"] = None) -> str:
    """Pont diviseur d'entrée du passe-bande, en une phrase : composants et valeurs si l'option
    est cochée (repères du montage réel), sinon ce que l'option changerait. "" sans objet."""
    att = res.attenuateur()
    if att is None:
        return ""
    nom, _alpha, Ra, Rb = att
    R1 = next(m for m in res.montages if m.cellule.nom == nom and m.structure == "SK_PB").composants["R1"]
    gain = fmt_nombre(20 * math.log10(res.gain_montage()), 3)
    if pont:
        e = next(e for e in etages_reels(res, choix, True) if e.pont)
        r1, r2, rb = e.designation("R1"), e.designation("R2"), e.designation("Rb")
        # Résistances normalisées : le pont ne divise plus exactement par le gain de la cascade
        reel = res.pont_reel(replace(choix, pont=True)) if choix is not None else None
        ecart = ""
        if reel is not None:
            a, b = reel[1].valeur, reel[2].valeur
            dB = 20 * math.log10((b / (a + b)) / _alpha)
            if abs(dB) >= 0.005:
                ecart = f" ({'+' if dB > 0 else ''}{fmt_decimales(dB, 2)} dB avec ses résistances normalisées)"
        return (f"Pont diviseur d'entrée (option cochée) : dans la cellule {nom}, {r1} = {e.valeur('R1')} "
                f"(côté entrée) remplace la résistance d'entrée de {fmt_si(R1, 'Ω', 4)}, et {rb} = "
                f"{e.valeur('Rb')} relie à la masse le nœud entre {r1} et {r2}. Le gain du montage à f0 "
                f"passe de {gain} dB à 0 dB{ecart}.")
    return (f"L'option « pont diviseur d'entrée » ramènerait ce gain à 0 dB : dans la cellule {nom}, la "
            f"résistance d'entrée passerait de {fmt_si(R1, 'Ω', 4)} à {fmt_si(Ra, 'Ω', 4)}, et une "
            f"résistance de {fmt_si(Rb, 'Ω', 4)} serait ajoutée vers la masse.")


def phrase_ecart_serie(res: Resultat, choix: "ChoixSeries", pont: bool = False) -> str:
    """Écart le plus grand entre les valeurs normalisées et les valeurs calculées, en une phrase
    (composants désignés comme dans le montage réel)."""
    ecart, nom, cellule = ecart_etages(etages_reels(res, choix, pont))
    if ecart < 5e-5 or not nom:
        return ("Les valeurs calculées figurent déjà dans la série choisie : la normalisation ne les change "
                "pas (écart nul).")
    return (f"L'écart le plus grand avec les valeurs calculées est de {fmt_compact(100 * ecart, 3)} % "
            f"({nom}, cellule {cellule}).")


def resume_gabarit(g: Gabarit) -> str:
    """Valeurs saisies sur une ligne : « fp = 2,4 kHz ; fa = 6,24 kHz ; Gp = −3 dB… »."""
    gab = [f"{LIBELLES[x]} = {fmt_si(getattr(g, x), 'Hz', compact=True)}" for x in FREQUENCES[g.type]]
    gab += [f"Gp = {fmt_compact(g.Gp)} dB", f"Ga = {fmt_compact(g.Ga)} dB"]
    if g.type in ("PB", "PM"):
        gab.append(f"R0 = {fmt_si(g.R0, 'Ω', compact=True)}")
    if g.type in ("PH", "PM"):
        gab.append(f"C0 = {fmt_si(g.C0, 'F', compact=True)}")
    return " ; ".join(gab)


def lignes_montage_reel(res: Resultat, choix: Optional[ChoixSeries] = None, pont: bool = False) -> List[str]:
    """Montage réel en texte : amplificateurs, nomenclature (repères du montage réel) et notes
    de câblage. Liste vide pour le coupe-bande."""
    if not res.montages:
        return []
    etages = etages_reels(res, choix, pont)
    aops = amplificateurs(etages)
    L = [f"Montage réel : {len(aops)} {AOP_NOM} ({_plage(aops)}), alimentation {ALIMENTATION}"
         + ((", avec pont diviseur d'entrée" if pont else ", sans pont diviseur d'entrée")
            if res.attenuateur() else ""),
         "  Nomenclature (repères du montage réel) :"]
    for ligne in nomenclature(etages, choix):
        L.append(f"    {ligne.categorie:<18}{ligne.valeur:>10}  × {ligne.quantite:<3}  {ligne.reperes}")
    L.append("  Notes de câblage :")
    L += [f"    - {note}" for note in notes_cablage(res, etages, choix)]
    return L


def rapport(res: Resultat, choix: Optional[ChoixSeries] = None, pont: bool = False) -> str:
    """Rapport complet en texte (console, copie, enregistrement).

    Avec un choix de séries actif, le rapport ajoute la réalisation des composants
    en valeurs normalisées et le contrôle du gabarit avec ces valeurs. `pont` :
    montage réel du passe-bande avec le pont diviseur d'entrée (gain 0 dB).
    """
    g, nm = res.gabarit, res.norm
    L: List[str] = []
    titre = f"Synthèse d'un filtre de Butterworth ({NOMS_TYPES[g.type].lower()})"
    L += [titre, "=" * len(titre), ""]

    L += ["Gabarit : " + resume_gabarit(g), ""]

    L.append("Étape 1 : normalisation du gabarit")
    if nm.B is not None:
        L.append(f"  f0 = √(fp+·fp−) = {fmt_si(nm.f_ref, 'Hz')}    B = (fp+ − fp−)/f0 = {fmt_nombre(nm.B)}")
    L.append(f"  {nm.formule_k} = {fmt_nombre(nm.k)}    (1/k = {fmt_nombre(1 / nm.k)})")
    L.append("")

    L.append("Étapes 2 et 3 : approximation de Butterworth, ordre minimal")
    L.append(f"  n ≥ {fmt_nombre(res.n_exact)}   ⇒   n = {res.n}")
    if res.eps_convention:
        L.append("  ε = 1 (Gp = −3 dB)")
    else:
        L.append(f"  ε = √(10^(−Gp/10) − 1) = {fmt_nombre(res.eps)}   ⇒   Ωc = ε^(−1/n) = {fmt_nombre(res.omega_c)}")
    L.append("")

    L.append("Étape 4 : fonction de transfert normalisée (prototype passe-bas)")
    facteurs = facteurs_prototype(res)
    if len(facteurs) == 1:
        L.append(f"  H(p) = 1 / ({facteurs[0]})")
    else:
        L.append("  H(p) = 1 / [" + "·".join(f"({x})" for x in facteurs) + "]")
    L.append("")

    L.append("Étape 5 : fonction de transfert réelle (transposition de fréquence)")
    L.append("  " + texte_transposition(res))
    for ligne in lignes_fonction_reelle(res):
        L.append("  " + ligne)
    L.append("")

    if res.montages:
        L.append("Étape 6 : composants (cellules de Sallen & Key à gain unité, K = 1)")
        w = "ω0" if g.type == "PM" else "ωp"
        if res.ref_pb:
            L.append(f"  Cellules passe-bas  : R0 = {fmt_si(res.ref_pb[0], 'Ω')}, "
                     f"C0 = 1/(R0·{w}) = {fmt_si(res.ref_pb[1], 'F')}")
        if res.ref_ph:
            L.append(f"  Cellules passe-haut : C0 = {fmt_si(res.ref_ph[1], 'F')}, "
                     f"R0 = 1/(C0·{w}) = {fmt_si(res.ref_ph[0], 'Ω')}")
        L.append("")
        L.append("  Repères du montage réel : R1, R2, R3… et C1, C2, C3… (dans chaque cellule : éléments en "
                 "série, contre-réaction, puis masse).")
        L.append(f"  {'Cellule':<9}{'Montage':<26}{'m':>10}{'q':>10}   Composants")
        for e in etages_reels(res, None, pont):
            m = e.montage
            comp = "   ".join(f"{e.designation(k)} = {e.valeur(k)}" for k in e.ordre)     # pont compris
            q = fmt_decimales(m.q) if m.q is not None else "—"
            L.append(f"  {m.cellule.nom:<9}{m.libelle:<26}{fmt_decimales(m.m):>10}{q:>10}   {comp}")
        L.append("")
        ecart = res.ecart_verification()
        L.append(f"  Vérification (transmittance recalculée à partir des composants) : écart relatif "
                 f"maximal {ecart:.1e}")
        att = res.attenuateur()
        if g.type == "PM":
            L.append(f"  Gain du montage à f0 : {fmt_nombre(20 * math.log10(res.gain_montage()), 3)} dB")
        if att:
            L.append("  " + phrase_pont(res, pont))
        L.append("")
        if choix is not None and choix.actif:
            L.append(f"Valeurs normalisées : {choix.libelle()}")
            if choix.associations:
                L.append("  (« a + b » : deux résistances en série, ou deux condensateurs en parallèle, "
                         "numérotés chacun)")
            for e in etages_reels(res, choix, pont):
                comp = "   ".join(f"{e.designation(k)} = {e.valeur(k)}" for k in e.ordre)
                L.append(f"  {e.montage.cellule.nom:<9}{e.montage.libelle:<26}{comp}")
            ajustees = phrase_ajustements(res, choix, pont)
            if ajustees:
                L.append("  " + ajustees)
            L.append("  " + phrase_ecart_serie(res, choix, pont))
            for p in res.points_controle_serie(choix):
                signe = "≥" if p.passante else "≤"
                L.append(f"  G({p.nom}) = {fmt_nombre(p.G, 4)} dB   ({signe} {fmt_compact(p.limite)} dB)   "
                         + ("respecté" if p.ok else "NON RESPECTÉ"))
            L.append("")

    if res.montages:
        L += lignes_montage_reel(res, choix, pont) + [""]

    L.append("Contrôle du gabarit")
    for p in res.points_controle():
        signe = "≥" if p.passante else "≤"
        L.append(f"  G({p.nom}) = {fmt_nombre(p.G, 4)} dB   ({signe} {fmt_compact(p.limite)} dB)   "
                 + ("respecté" if p.ok else "NON RESPECTÉ"))

    remarques = res.avertissements + res.remarques_montage
    if remarques:
        L += ["", "Remarques"] + [f"  - {a}" for a in remarques]
    return "\n".join(L)


# =============================================================================
# 11. Exemples de vérification et essai en console
# =============================================================================

# Exemples de vérification : servent seulement à contrôler les calculs (« python moteur.py »).
# La fenêtre ne les propose pas : un filtre neuf part d'un gabarit vide.
EXEMPLES = {
    # Passe-bas : n = 5 et C0 ≈ 6,63 nF
    "PB": {"fp": "2,4k", "fa": "6,24k", "Gp": "-3", "Ga": "-40", "R0": "10k"},
    "PH": {"fa": "2,4k", "fp": "6,24k", "Gp": "-3", "Ga": "-40", "C0": "10n"},
    # Passe-bande : k = 0,127 et n = 2
    "PM": {"fa_moins": "500", "fp_moins": "909", "fp_plus": "1100", "fa_plus": "2000",
           "Gp": "-3", "Ga": "-25", "R0": "10k", "C0": "10n"},
    "CB": {"fp_moins": "500", "fa_moins": "909", "fa_plus": "1100", "fp_plus": "2000",
           "Gp": "-3", "Ga": "-25"},
}


def gabarit_depuis_textes(type_: str, textes: Dict[str, str]) -> Gabarit:
    """Construit un Gabarit à partir des champs saisis (chaînes de caractères)."""
    valeurs = {}
    champs = list(FREQUENCES[type_]) + ["Gp", "Ga"]
    if type_ in ("PB", "PM"):
        champs.append("R0")
    if type_ in ("PH", "PM"):
        champs.append("C0")
    for champ in champs:
        valeurs[champ] = lire_valeur(textes.get(champ, ""), champ)
    return Gabarit(type_, **valeurs)


if __name__ == "__main__":
    # Exemples de vérification : résistances E12, condensateurs E6, associations permises
    choix = ChoixSeries(resistances="E12", condensateurs="E6", associations=True)
    for t in ("PB", "PM"):
        print(rapport(synthese(gabarit_depuis_textes(t, EXEMPLES[t])), choix, pont=(t == "PM")))
        print("\n")
