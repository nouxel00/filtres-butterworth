# -*- coding: utf-8 -*-
"""
Export du montage réel en netlist SPICE, pour LTspice ou PSpice.

La netlist reprend exactement le montage affiché : mêmes repères (R1, R2, C1…,
U1, U2…), valeurs calculées ou normalisées (associations comprises : deux
résistances en série, deux condensateurs en parallèle), pont diviseur d'entrée
s'il est coché, suiveurs après les cellules RC ou CR.

Les amplificateurs sont décrits par un modèle linéaire à un pôle, sans
transistor (gain statique A0 = 2·10⁵, produit gain-bande 1 MHz, comme la courbe
« µA741 réel » du Bode réel) : le fichier reste ainsi dans les limites des
versions étudiantes de PSpice (Lite : 64 nœuds, 10 transistors, 2 amplificateurs
de bibliothèque). Un modèle idéal (gain de 10⁹) est fourni aussi.

Les commentaires sont écrits sans accents (texte ASCII) : certains simulateurs
lisent mal les autres caractères.
"""

from __future__ import annotations

import math
import textwrap
import time
import unicodedata
from typing import List, Optional, Tuple

import moteur as mt

LIMITE_NOEUDS_PSPICE = 64        # version étudiante (Lite) de PSpice
MODELES = ("1pole", "ideal")
SIMULATEURS = {"ltspice": "LTspice", "pspice": "PSpice"}

_SUFFIXES = [(1e9, "G"), (1e6, "MEG"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"),
             (1e-12, "p"), (1e-15, "f")]


def valeur_spice(x: float, chiffres: int = 6) -> str:
    """Valeur en notation SPICE : 4700 -> « 4.7k », 2.2e-07 -> « 220n », 3.3e6 -> « 3.3MEG ».

    « MEG » et non « M » : pour SPICE, M veut dire milli."""
    if x == 0:
        return "0"
    for facteur, suffixe in _SUFFIXES:
        if abs(x) >= facteur * 0.9999995:
            break
    mantisse = f"{x / facteur:.{chiffres}g}"
    if "e" in mantisse:                                   # garde-fou (valeurs extrêmes)
        return f"{x:.{chiffres}g}"
    return mantisse + suffixe


def ascii(texte: str) -> str:
    """Texte sans accents ni signes typographiques (commentaires de la netlist)."""
    texte = (texte.replace("−", "-").replace("µ", "u").replace("Ω", "ohms").replace("·", ".")
             .replace("«\u00a0", '"').replace("\u00a0»", '"').replace("« ", '"').replace(" »", '"')
             .replace("«", '"').replace("»", '"').replace(" ", " ").replace(" ", " ")
             .replace("’", "'").replace("…", "...").replace("≥", ">=").replace("≤", "<=").replace("√", "racine"))
    sans = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    return sans


class _Netlist:
    """Lignes de la netlist et nœuds utilisés (pour les compter)."""

    def __init__(self):
        self.lignes: List[str] = []
        self.noeuds = {"0"}
        self._internes = 0

    def composant(self, nom: str, a: str, b: str, valeur: float) -> None:
        self.lignes.append(f"{nom} {a} {b} {valeur_spice(valeur)}")
        self.noeuds.update((a, b))

    def interne(self, base: str) -> str:
        self._internes += 1
        return f"{base}_{self._internes}"

    def realisation(self, noms: List[str], r: mt.Realisation, a: str, b: str, genre: str) -> None:
        """Un composant, ou une association : résistances en série (nœud intermédiaire),
        condensateurs en parallèle."""
        if len(r.elements) == 1:
            self.composant(noms[0], a, b, r.elements[0])
        elif genre == "R":
            milieu = self.interne(f"{a}_{noms[0]}")
            self.composant(noms[0], a, milieu, r.elements[0])
            self.composant(noms[1], milieu, b, r.elements[1])
        else:
            for nom, v in zip(noms, r.elements):
                self.composant(nom, a, b, v)

    def aop(self, nom: str, plus: str, moins: str, sortie: str, modele: str) -> None:
        self.lignes.append(f"X{nom} {plus} {moins} {sortie} {'AOP_1POLE' if modele == '1pole' else 'AOP_IDEAL'}")
        self.noeuds.update((plus, moins, sortie))


def _etage(n: _Netlist, e: mt.Etage, entree: str, numero: int, sortie: str, modele: str) -> None:
    """Composants d'un étage, de `entree` à `sortie` (nœuds A, B… de l'étage : N<numéro>A…)."""
    s = e.montage.structure
    c = e.composants

    def poser(cle: str, a: str, b: str) -> None:
        n.realisation(e.noms[cle], c[cle], a, b, cle[0])

    a, b = f"N{numero}A", f"N{numero}B"
    if s in ("SK_PB", "SK_PH"):
        # Sallen & Key à gain unité : entrée -> A, A -> B (série), A -> sortie (contre-réaction),
        # B -> masse ; suiveur : + sur B, - et sortie reliés
        if s == "SK_PB":
            entree_cle, serie, reaction, masse = "R1", "R2", "C2", "C1"
        else:
            entree_cle, serie, reaction, masse = "C1", "C2", "R2", "R1"
        poser(entree_cle, entree, a)
        if e.pont:                                    # pont diviseur : Rb du nœud A à la masse
            poser("Rb", a, "0")
        poser(serie, a, b)
        poser(reaction, a, sortie)
        poser(masse, b, "0")
        n.aop(e.aop, b, sortie, sortie, modele)
    elif s in ("RC", "CR"):
        serie, masse = ("R1", "C1") if s == "RC" else ("C1", "R1")
        point = a if e.suiveur else sortie
        poser(serie, entree, point)
        poser(masse, point, "0")
        if e.suiveur:                                 # suiveur d'isolation
            n.aop(e.suiveur, point, sortie, sortie, modele)
    else:
        # Rauch (passe-bande inverseur) : R1 entrée -> X ; R2 X -> masse ; C2 X -> N (entrée -) ;
        # C1 X -> sortie ; R3 N -> sortie ; entrée + à la masse
        poser("R1", entree, a)
        poser("R2", a, "0")
        poser("C2", a, b)
        poser("C1", a, sortie)
        poser("R3", b, sortie)
        n.aop(e.aop, "0", b, sortie, modele)


def _bornes(res: mt.Resultat) -> Tuple[float, float]:
    """Plage de l'analyse AC : une décade de part et d'autre des fréquences du gabarit."""
    g = res.gabarit
    f = [getattr(g, nom) for nom in mt.FREQUENCES[g.type]]
    debut = 10 ** math.floor(math.log10(min(f)) - 1)
    fin = 10 ** math.ceil(math.log10(max(f)) + 1)
    return debut, fin


def netlist(res: mt.Resultat, choix: Optional[mt.ChoixSeries] = None, pont: bool = False,
            simulateur: str = "ltspice", modele: str = "1pole", fichier: str = "",
            version: str = "") -> Tuple[str, int]:
    """Netlist du montage réel pour `simulateur` (« ltspice » ou « pspice »).

    Renvoie (texte, nombre de nœuds, masse comprise et nœuds internes des amplificateurs
    comptés) : au-delà de LIMITE_NOEUDS_PSPICE, la version étudiante de PSpice refuse
    la simulation."""
    if not res.montages:
        raise ValueError("Le coupe-bande n'est pas réalisable en Sallen & Key : aucune netlist.")
    if simulateur not in SIMULATEURS or modele not in MODELES:
        raise ValueError("Simulateur ou modèle inconnu.")
    etages = mt.etages_reels(res, choix, pont)
    amplis = mt.amplificateurs(etages)
    n = _composants(etages, modele)
    # Nœuds : ceux du montage, plus un nœud interne par amplificateur à un pôle
    nb_noeuds = len(n.noeuds) + (len(amplis) if modele == "1pole" else 0)
    entete = _entete(res, choix, pont, simulateur, modele, fichier, version, len(etages), amplis, nb_noeuds)
    return "\n".join(_couper(entete) + n.lignes + _fin(res, simulateur)) + "\n", nb_noeuds


def _composants(etages: List[mt.Etage], modele: str) -> _Netlist:
    """La source, puis les composants étage par étage, chacun précédé d'un commentaire qui
    décrit sa cellule."""
    n = _Netlist()
    n.lignes.append("* Source")
    n.lignes.append("V1 E 0 AC 1")
    n.noeuds.add("E")
    entree = "E"
    for k, e in enumerate(etages, start=1):
        sortie = "S" if k == len(etages) else f"S{k}"
        m = e.montage
        f = mt.fmt_si(m.cellule.wn / (2 * math.pi), "Hz")
        cellule = f"Cellule {m.cellule.nom} : {m.libelle}, " + (
            f"f0 = {f}, Q = {mt.fmt_nombre(m.cellule.Q)}" if m.cellule.ordre == 2 else f"fc = {f}")
        if e.pont:
            cellule += ", pont diviseur d'entrée"
        n.lignes += ["", "* " + ascii(cellule)]
        _etage(n, e, entree, k, sortie, modele)
        entree = sortie
    return n


def _entete(res: mt.Resultat, choix: Optional[mt.ChoixSeries], pont: bool, simulateur: str, modele: str,
            fichier: str, version: str, nb_etages: int, amplis: List[str], nb_noeuds: int) -> List[str]:
    """Commentaires du début : filtre, valeurs, origine, gabarit, montage, nœuds."""
    g = res.gabarit
    if choix is not None and choix.actif:
        valeurs = f"valeurs normalisées ({choix.court()})"
        if choix.ajustements:
            valeurs += ", ajustées pour respecter le gabarit"
    else:
        valeurs = "valeurs calculées"
    ordre = res.n * (2 if g.type in ("PM", "CB") else 1)
    return [
        ascii(f"Filtre {mt.NOMS_TYPES[g.type].lower()} de Butterworth d'ordre {ordre} ({nb_etages} "
              f"cellule{'s' if nb_etages > 1 else ''})"),
        "* " + ascii(valeurs[0].upper() + valeurs[1:]),
        "* " + ascii(f"Netlist {SIMULATEURS[simulateur]} créée par Filtres de Butterworth"
                     + (f" {version}" if version else "") + time.strftime(" le %d/%m/%Y à %H:%M")
                     + (f", filtre {fichier}" if fichier else "")),
        "* " + ascii("Gabarit : " + mt.resume_gabarit(g)),
        "* " + ascii(f"Montage réel : {len(amplis)} amplificateur{'s' if len(amplis) > 1 else ''} "
                     f"({', '.join(amplis)}), repères de l'onglet Câblage"
                     + (", avec le pont diviseur d'entrée" if pont and res.attenuateur() else "")),
        "* Entree : noeud E (source V1, amplitude 1 V). Sortie : noeud S.",
        ("* " + ascii("Amplificateurs : modèle linéaire à un pôle, sans transistor (A0 = 2e5, produit "
                      "gain-bande 1 MHz, comme la courbe « µA741 réel ») ; pour des amplificateurs "
                      "idéaux, remplacer AOP_1POLE par AOP_IDEAL.") if modele == "1pole" else
         "* Amplificateurs ideaux (gain 1e9) ; modele a un pole : remplacer AOP_IDEAL par AOP_1POLE."),
        f"* Noeuds : {nb_noeuds} (masse et noeuds internes des amplificateurs compris)"
        + (f" ; la version etudiante de PSpice en accepte {LIMITE_NOEUDS_PSPICE}." if simulateur == "pspice"
           else "."),
        "",
    ]


def _fin(res: mt.Resultat, simulateur: str) -> List[str]:
    """Modèles des amplificateurs, puis l'analyse en fréquence propre à chaque simulateur."""
    debut, fin = _bornes(res)
    lignes = [
        "",
        "* Amplificateur a un pole : gain statique 2e5, pole a 5 Hz (produit gain-bande 1 MHz).",
        "* G1 injecte 1 A/V x (V+ - V-) dans R1 // C1 ; E1 recopie la tension du noeud interne.",
        ".SUBCKT AOP_1POLE PLUS MOINS SORTIE",
        "G1 0 INT PLUS MOINS 1",
        "R1 INT 0 200k",
        f"C1 INT 0 {valeur_spice(1 / (2 * math.pi * 200e3 * 5))}",
        "E1 SORTIE 0 INT 0 1",
        ".ENDS AOP_1POLE",
        "",
        "* Amplificateur ideal : gain 1e9, sans limite de frequence.",
        ".SUBCKT AOP_IDEAL PLUS MOINS SORTIE",
        "E1 SORTIE 0 PLUS MOINS 1e9",
        ".ENDS AOP_IDEAL",
        "",
        "* Analyse : diagramme de Bode de V(S)",
    ]
    if simulateur == "ltspice":
        lignes.append(f".ac dec 100 {valeur_spice(debut)} {valeur_spice(fin)}")
        lignes.append("* Gain aux frequences du gabarit : menu View > SPICE Error Log apres la simulation")
        for p in res.points_controle():
            nom = "G_" + ascii(p.nom).replace("-", "moins").replace("+", "plus")
            lignes.append(f".meas AC {nom} FIND V(S) AT={valeur_spice(p.f)}")
        lignes.append(".end")
    else:
        lignes.append(f".AC DEC 100 {valeur_spice(debut)} {valeur_spice(fin)}")
        lignes.append("* Courbes : Trace > Add Trace, puis DB(V(S)) et P(V(S))")
        lignes.append(".PROBE V(S) V(E)")
        lignes.append(".END")
    return lignes


def _couper(lignes: List[str], largeur: int = 100) -> List[str]:
    """Commentaires longs coupés en plusieurs lignes « * … » (certains simulateurs n'aiment
    pas les lignes trop longues)."""
    resultat = []
    for ligne in lignes:
        if ligne.startswith("* ") and len(ligne) > largeur:
            resultat += textwrap.wrap(ligne[2:], largeur - 2, initial_indent="* ", subsequent_indent="*   ",
                                      break_on_hyphens=False)
        else:
            resultat.append(ligne)
    return resultat


def frequences_controle(res: mt.Resultat) -> List[Tuple[str, float]]:
    """(nom, fréquence) des points du gabarit, comme dans les mesures .meas de LTspice."""
    return [(p.nom, p.f) for p in res.points_controle()]


def resume(res: mt.Resultat, nb_noeuds: int, simulateur: str) -> str:
    """Phrase après l'export : nombre de nœuds et, pour PSpice, la limite de la version étudiante."""
    if simulateur == "pspice" and nb_noeuds > LIMITE_NOEUDS_PSPICE:
        return (f"Attention : ce montage compte {nb_noeuds} nœuds ; la version étudiante de PSpice (Lite) en "
                f"accepte {LIMITE_NOEUDS_PSPICE} au plus et refusera la simulation. Avec LTspice, aucune limite.")
    return f"{nb_noeuds} nœuds" + (f" (version étudiante de PSpice : {LIMITE_NOEUDS_PSPICE} au plus)."
                                   if simulateur == "pspice" else ".")

