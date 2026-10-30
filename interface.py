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

Les calculs sont faits par moteur.py et les dessins par graphes.py : l'interface
ne s'occupe que de l'affichage et des interactions. Elle est répartie en six fichiers :
    interface.py  la fenêtre principale (classe Application) : elle assemble la saisie
                  et les résultats, lance le calcul, ouvre et enregistre les fichiers,
                  garde la séance, construit les menus Fichier et Affichage
    commun.py     couleurs et polices (Theme), numéro de version, préférences, petits
                  éléments réutilisés partout (boutons, liens, infobulles, dialogues…)
    saisie.py     colonne de saisie : types de filtre, gabarit, croquis, séries
    panneaux.py   résultats : bandeau, onglets (Bode, étapes, composants, câblage), accueil
    aide.py       menu Aide : mode d'emploi, nouveautés, raccourcis, à propos, visite
                  guidée et fenêtre du cours « Comprendre Sallen & Key »
    mise_a_jour.py  nouvelles versions : recherche (avec l'accord de l'utilisateur),
                  téléchargement vérifié, installation ; carte et entrées du menu Aide
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("TkAgg")

import graphes as gr                                              # noqa: E402
import moteur as mt                                               # noqa: E402
from commun import (
    activer_haute_resolution, BoutonPlat, CadreDefilant, chemin_ressource, DEPOT, Dialogue,
    enregistrer_preferences, fichier_preferences, identifier_application, Infobulle,
    lire_preferences, ouvrir_document, SectionRepliable, TAILLES_TEXTE, texte_souple, Theme, UI,
    VERSION)
from saisie import (
    AIDE, AIDE_DEFAUT, BULLE_SERIES, BULLES_CHAMPS, BULLES_TYPES, champs_du_type, ChampUnite,
    croquis_complet, CroquisGabarit, EtatCalcul, ListeChoix, OPTIONS_SERIES, REFERENCES_DEPART,
    TuileType, UNITES, valeurs_de_depart)
from panneaux import (
    Accueil, BarreOnglets, BULLES_ONGLETS, Fait, PanneauBode, PanneauCablage, PanneauComposants,
    PanneauEtapes)
from aide import AideMixin, lire_lisezmoi, VisiteGuidee
from mise_a_jour import MiseAJourMixin

# Noms repris par main.py et par les programmes d'essai qui pilotent la fenêtre
__all__ = ["Application", "lancer", "VERSION", "DEPOT", "UI", "lire_preferences", "enregistrer_preferences",
           "fichier_preferences", "ouvrir_document", "lire_lisezmoi", "VisiteGuidee", "tk", "tkfont"]


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


# =============================================================================
# Fenêtre principale
# =============================================================================

class Application(AideMixin, MiseAJourMixin, tk.Tk):
    """Fenêtre principale : saisie du gabarit à gauche, résultats à droite.

    annoncer_nouveautes et mises_a_jour (lancement réel, par lancer()) : nouveautés d'une
    nouvelle version, une fois ; question puis vérification des mises à jour au démarrage."""
    ONGLETS = ["Bode normalisé", "Bode réel", "Étapes du calcul", "Composants", "Câblage"]

    def __init__(self, fichier: Optional[str] = None, annoncer_nouveautes: bool = False,
                 mises_a_jour: bool = False):
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
        self._etat_initial()
        onglet = self._reprendre_session()
        # Tant qu'aucun filtre n'est calculé, la zone des résultats montre l'accueil.
        self._accueil_actif = False
        self.visite: Optional[VisiteGuidee] = None   # visite guidée en cours
        self._init_mises_a_jour()

        self._construire()
        self._menu()
        self._dimensionner_fenetre()
        self.choisir_type(self.type_courant, calculer=False)
        self.choisir_onglet(onglet)
        self._maj_titre()
        self.protocol("WM_DELETE_WINDOW", self.quitter)
        self._premiers_pas(fichier, annoncer_nouveautes, mises_a_jour)

    def _etat_initial(self) -> None:
        """Saisie, options et état du calcul d'une fenêtre neuve (avant la reprise de séance)."""
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

    def _reprendre_session(self) -> int:
        """Reprise de la séance précédente : type, valeurs saisies, séries, options, filtre
        ouvert. Renvoie l'onglet à afficher."""
        onglet = 0
        session = self.preferences.get("session")
        if isinstance(session, dict) and self._appliquer_etat(self._sans_exemples(session)):
            if session.get("onglet") in range(len(self.ONGLETS)):
                onglet = session["onglet"]
            if isinstance(session.get("fichier"), str) and os.path.isfile(session["fichier"]):
                self.fichier = session["fichier"]
                if isinstance(session.get("enregistre"), dict):
                    self._enregistre = session["enregistre"]
        return onglet

    def _premiers_pas(self, fichier: Optional[str], annoncer_nouveautes: bool, mises_a_jour: bool = False) -> None:
        """Juste après l'ouverture : filtre à ouvrir ou séance à recalculer, puis visite guidée
        (tout premier lancement) ou nouveautés (premier lancement d'une nouvelle version), et
        mises à jour (question posée une fois, ou vérification discrète si elle est acceptée)."""
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
        if mises_a_jour:
            self.after(1500, self._mises_a_jour_au_demarrage)

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
        """Barre de menus (Fichier, Affichage, Aide) et raccourcis clavier."""
        barre = tk.Menu(self)
        self._menu_fichier(barre)
        self._menu_affichage(barre)
        self._menu_aide(barre)                       # aide.py
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

    def _menu_fichier(self, barre: tk.Menu) -> None:
        """Menu Fichier : filtres (.filtre), exports du résultat, Quitter."""
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

    def _menu_affichage(self, barre: tk.Menu) -> None:
        """Menu Affichage : taille du texte (toute la fenêtre suit, gardée d'une séance à
        l'autre), onglets, options du Bode réel."""
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
        self._reafficher_carte()                      # carte des mises à jour, à la nouvelle échelle
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
        """Avant de quitter, de commencer un nouveau filtre, d'en ouvrir un autre ou d'installer
        une mise à jour : propose d'enregistrer un filtre qui ne l'est pas ; pour quitter, demande
        toujours confirmation. Renvoie True si l'action peut continuer."""
        if self._dialogue is not None:                 # une question est déjà posée
            return False
        if self.travail_non_enregistre():
            question = {"quitter": "Enregistrer le filtre avant de quitter ?",
                        "nouveau": "Enregistrer le filtre avant d'en commencer un nouveau ?",
                        "ouvrir": "Enregistrer le filtre avant d'en ouvrir un autre ?",
                        "mise_a_jour": "Enregistrer le filtre avant la mise à jour ?"}[action]
            if self.fichier and self._enregistre is not None:
                explication = f"« {os.path.basename(self.fichier)} » a été modifié depuis son dernier enregistrement."
            else:
                explication = "Ce filtre n'a pas encore été enregistré."
            explication += (" Sans enregistrement, seule la dernière saisie sera reprise au prochain lancement."
                            if action in ("quitter", "mise_a_jour")
                            else " Sans enregistrement, la saisie actuelle sera perdue.")
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
    app = Application(fichier, annoncer_nouveautes=True, mises_a_jour=True)
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
