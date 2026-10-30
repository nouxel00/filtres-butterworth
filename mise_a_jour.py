# -*- coding: utf-8 -*-
"""
mise_a_jour.py
==============
Nouvelles versions du programme : recherche, téléchargement et installation, puis ce qu'en
montre la fenêtre principale (carte en bas à droite, entrées du menu Aide).

Les versions sont les Releases du dépôt GitHub. Le programme n'utilise Internet qu'avec
l'accord de l'utilisateur (question posée une fois, modifiable dans le menu Aide) ou à sa
demande (Aide > Rechercher une mise à jour), et seulement pour ceci :

1. Dernière version : la page « releases/latest » du dépôt renvoie vers la dernière Release
   (…/releases/tag/v2.2), dont l'étiquette donne le numéro. Une seule requête, sans l'API de
   GitHub, limitée à 60 requêtes par heure et par adresse : toute une salle de classe, derrière
   la même adresse, la dépasserait.
2. Si elle est plus récente que la version installée : l'empreinte SHA-256 de son installateur
   (fichier .sha256 joint à la Release par la construction automatique, après l'installateur :
   tant qu'il manque, la version n'est pas encore prête et rien n'est proposé).
3. Sur « Installer » : téléchargement de l'installateur dans le dossier temporaire, vérification
   de son empreinte, fermeture du programme (avec proposition d'enregistrer le filtre), puis
   installation silencieuse : l'installateur remplace le programme, garde les préférences et
   la dernière saisie, puis rouvre le programme.

Aucun identifiant ni aucune donnée de l'utilisateur n'est envoyé.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Tuple

from commun import BoutonPlat, DEPOT, enregistrer_preferences, insecable, Lien, ouvrir_document, Theme, UI, VERSION

if TYPE_CHECKING:                     # annotations seulement : interface.py importe ce module
    from interface import Application


DELAI = 10                  # secondes d'attente au plus pour une réponse du serveur
BLOC = 64 * 1024            # taille des morceaux téléchargés (octets)


class ErreurMiseAJour(Exception):
    """Recherche ou téléchargement impossible ; le message s'affiche tel quel."""


@dataclass
class NouvelleVersion:
    """Version publiée plus récente que celle du programme, prête à être installée."""
    version: str            # « 2.2 »
    page: str               # page de la Release (ses nouveautés)
    installateur: str       # adresse de téléchargement de l'installateur
    empreinte: str          # SHA-256 attendu de l'installateur (64 chiffres hexadécimaux)

    @property
    def fichier(self) -> str:
        return nom_installateur(self.version)


def nom_installateur(version: str) -> str:
    """Nom de l'installateur joint à chaque Release (voir installation/installateur.iss)."""
    return f"Installer_FiltresButterworth_{version}.exe"


def numero(texte: str) -> Optional[Tuple[int, ...]]:
    """« v2.1 », « 2.1 » ou « 2.0.1 » : nombres à comparer ((2, 1)…), les zéros de fin en
    moins (2.1.0 vaut 2.1) ; None si le texte n'est pas un numéro de version."""
    trouve = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})", texte.strip())
    if trouve is None:
        return None
    nombres = [int(x) for x in trouve.group(1).split(".")]
    while len(nombres) > 1 and nombres[-1] == 0:
        nombres.pop()
    return tuple(nombres)


def plus_recente(version: str, actuelle: str = VERSION) -> bool:
    """Vrai si `version` est postérieure à `actuelle`."""
    a, b = numero(version), numero(actuelle)
    return a is not None and b is not None and a > b


def _ouvrir(adresse: str, methode: str = "GET"):
    """Requête HTTPS (réglages de proxy du système compris) ; les redirections sont suivies."""
    requete = urllib.request.Request(adresse, method=methode, headers={"User-Agent": "FiltresButterworth"})
    return urllib.request.urlopen(requete, timeout=DELAI)


def _erreur_reseau(e: BaseException) -> ErreurMiseAJour:
    if isinstance(e, urllib.error.HTTPError):
        return ErreurMiseAJour(f"GitHub a répondu par une erreur ({e.code}). Réessayez plus tard.")
    return ErreurMiseAJour("GitHub ne répond pas : vérifiez la connexion à Internet.")


def derniere_release(depot: str = DEPOT) -> Optional[Tuple[str, str]]:
    """(version, étiquette) de la dernière Release publiée, par exemple ("2.2", "v2.2") ; None
    s'il n'y en a aucune, ou si son étiquette n'est pas un numéro de version."""
    try:
        with _ouvrir(depot + "/releases/latest", "HEAD") as reponse:
            adresse = reponse.geturl()
    except urllib.error.HTTPError as e:
        if e.code == 404:                       # dépôt sans Release
            return None
        raise _erreur_reseau(e) from e
    except Exception as e:
        raise _erreur_reseau(e) from e
    trouve = re.search(r"/releases/tag/([^/?#]+)/?$", adresse)
    if trouve is None:                          # aucune Release : renvoi vers la liste
        return None
    etiquette = urllib.parse.unquote(trouve.group(1))
    if numero(etiquette) is None:
        return None
    return etiquette[1:] if etiquette.startswith("v") else etiquette, etiquette


def chercher(actuelle: str = VERSION, depot: str = DEPOT) -> Optional[NouvelleVersion]:
    """Nouvelle version prête à installer, ou None (programme à jour, ou installateur de la
    dernière Release pas encore joint). Lève ErreurMiseAJour si GitHub ne répond pas."""
    release = derniere_release(depot)
    if release is None or not plus_recente(release[0], actuelle):
        return None
    version, etiquette = release
    installateur = f"{depot}/releases/download/{etiquette}/{nom_installateur(version)}"
    try:
        with _ouvrir(installateur + ".sha256") as reponse:
            contenu = reponse.read(4096).decode("ascii", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:                       # construction de la Release encore en cours
            return None
        raise _erreur_reseau(e) from e
    except Exception as e:
        raise _erreur_reseau(e) from e
    empreinte = re.search(r"\b[0-9a-fA-F]{64}\b", contenu)
    if empreinte is None:
        return None
    return NouvelleVersion(version, f"{depot}/releases/tag/{etiquette}", installateur, empreinte.group(0).lower())


def empreinte_fichier(chemin: str) -> str:
    """SHA-256 d'un fichier, en hexadécimal."""
    somme = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(BLOC), b""):
            somme.update(bloc)
    return somme.hexdigest()


def dossier_telechargement() -> str:
    return os.path.join(tempfile.gettempdir(), "FiltresButterworth")


def nettoyer_telechargements(actuelle: str = VERSION, dossier: Optional[str] = None) -> None:
    """Efface du dossier temporaire les installateurs déjà installés (version égale ou antérieure
    à celle du programme) et les téléchargements interrompus depuis plus d'un jour."""
    dossier = dossier or dossier_telechargement()
    try:
        noms = os.listdir(dossier)
    except OSError:
        return
    for nom in noms:
        trouve = re.fullmatch(r"Installer_FiltresButterworth_(.+)\.exe(\.partiel)?", nom)
        chemin = os.path.join(dossier, nom)
        try:
            if trouve is None:
                continue
            if trouve.group(2) and time.time() - os.path.getmtime(chemin) < 86400:
                continue                                  # téléchargement peut-être en cours
            if trouve.group(2) or not plus_recente(trouve.group(1), actuelle):
                os.remove(chemin)
        except OSError:
            pass


def telecharger(nouvelle: NouvelleVersion, avancement: Callable[[int, int], None] = lambda fait, total: None,
                annulee: Optional[threading.Event] = None, dossier: Optional[str] = None) -> str:
    """Télécharge l'installateur, vérifie son empreinte et renvoie son chemin. avancement(fait,
    total) suit le téléchargement (octets ; total 0 s'il est inconnu). Un installateur déjà
    téléchargé et intact est repris tel quel. Lève ErreurMiseAJour en cas d'échec ou
    d'annulation ; un fichier incomplet ou abîmé est effacé."""
    dossier = dossier or dossier_telechargement()
    chemin = os.path.join(dossier, nouvelle.fichier)
    if os.path.isfile(chemin) and empreinte_fichier(chemin) == nouvelle.empreinte:
        return chemin
    partiel = chemin + ".partiel"
    try:
        os.makedirs(dossier, exist_ok=True)
        empreinte = _copier(nouvelle.installateur, partiel, avancement, annulee)
        if empreinte != nouvelle.empreinte:
            raise ErreurMiseAJour("L'installateur téléchargé est abîmé (son empreinte ne correspond pas) : "
                                  "il n'a pas été lancé. Réessayez.")
        os.replace(partiel, chemin)
    except Exception as e:
        try:
            os.remove(partiel)
        except OSError:
            pass
        if isinstance(e, ErreurMiseAJour):
            raise
        if isinstance(e, OSError) and not isinstance(e, urllib.error.URLError) and e.filename:
            raise ErreurMiseAJour(f"Le dossier temporaire n'accepte pas l'installateur ({e.strerror}).") from e
        raise ErreurMiseAJour("Le téléchargement a échoué : vérifiez la connexion à Internet, "
                              "puis réessayez.") from e
    return chemin


def _copier(adresse: str, chemin: str, avancement: Callable[[int, int], None],
            annulee: Optional[threading.Event]) -> str:
    """Copie le fichier distant par morceaux ; renvoie son empreinte SHA-256."""
    somme = hashlib.sha256()
    with _ouvrir(adresse) as reponse, open(chemin, "wb") as fichier:
        total = int(reponse.headers.get("Content-Length") or 0)
        fait = 0
        while True:
            if annulee is not None and annulee.is_set():
                raise ErreurMiseAJour("Téléchargement annulé.")
            bloc = reponse.read(BLOC)
            if not bloc:
                break
            fichier.write(bloc)
            somme.update(bloc)
            fait += len(bloc)
            avancement(fait, total)
    if total and fait != total:
        raise ErreurMiseAJour("Le téléchargement a été interrompu : réessayez.")
    return somme.hexdigest()


def installe_pour_tous(programme: str) -> bool:
    """Vrai si le programme est installé pour tous les utilisateurs (dossier Program Files) :
    la mise à jour se fait alors au même endroit, avec les droits d'administrateur."""
    chemin = os.path.normcase(os.path.abspath(programme))
    for nom in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        dossier = os.environ.get(nom)
        if dossier and chemin.startswith(os.path.normcase(os.path.abspath(dossier)) + os.sep):
            return True
    return False


def commande_installation(installateur: str, programme: str = sys.executable) -> List[str]:
    """Installation silencieuse (fenêtre de progression seulement) au même endroit que le
    programme actuel ; /MISEAJOUR=1 demande à l'installateur de rouvrir le programme
    (installation/installateur.iss). Journal dans le dossier temporaire."""
    journal = os.path.join(tempfile.gettempdir(), "FiltresButterworth_mise_a_jour.log")
    return [installateur, "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
            "/ALLUSERS" if installe_pour_tous(programme) else "/CURRENTUSER", f"/LOG={journal}", "/MISEAJOUR=1"]


def environnement_installation() -> dict:
    """Environnement de l'installateur, puis du programme qu'il rouvre : sans les variables
    propres au programme en cours (PyInstaller, Tcl/Tk), pour que la nouvelle version démarre
    comme après un double-clic (PYINSTALLER_RESET_ENVIRONMENT : nouveau programme)."""
    environnement = {cle: valeur for cle, valeur in os.environ.items()
                     if not cle.upper().startswith(("_PYI", "_MEI"))
                     and cle.upper() not in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH")}
    environnement["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return environnement


def lancer_installation(installateur: str, programme: str = sys.executable) -> subprocess.Popen:
    """Lance l'installateur, qui continue seul une fois le programme fermé."""
    return subprocess.Popen(commande_installation(installateur, programme), env=environnement_installation(),
                            close_fds=True)


class Tache:
    """Travail réseau dans un fil d'exécution à part : la fenêtre reste réactive. Tk n'étant
    utilisable que depuis son propre fil, la fenêtre consulte régulièrement `fini`, puis
    `resultat` ou `erreur` ; `avancement` et `annulee` servent au téléchargement."""

    def __init__(self, travail: Callable[["Tache"], object]):
        self.fini = False
        self.resultat: object = None
        self.erreur: Optional[BaseException] = None
        self.avancement: Tuple[int, int] = (0, 0)
        self.annulee = threading.Event()
        threading.Thread(target=self._executer, args=(travail,), daemon=True).start()

    def _executer(self, travail: Callable[["Tache"], object]) -> None:
        try:
            self.resultat = travail(self)
        except BaseException as e:              # toute erreur est rapportée à la fenêtre
            self.erreur = e
        finally:
            self.fini = True


# =============================================================================
# Dans la fenêtre
# =============================================================================

class CarteInfo(tk.Frame):
    """Carte posée en bas à droite de la fenêtre, par-dessus son contenu (rien ne bouge) :
    titre, texte, boutons et lien facultatif."""

    def __init__(self, app: tk.Tk, theme: Theme):
        super().__init__(app, bg=UI["surface"], highlightthickness=1, highlightbackground=UI["trait_fort"])
        self.theme = theme
        px, P = theme.px, theme.polices
        tk.Frame(self, bg=UI["accent"], width=px(4)).pack(side="left", fill="y")
        corps = tk.Frame(self, bg=UI["surface"])
        corps.pack(side="left", fill="both", expand=True, padx=(px(16), px(18)), pady=(px(12), px(14)))
        self.titre = tk.Label(corps, text="", font=P["champ"], fg=UI["encre"], bg=UI["surface"], anchor="w",
                              justify="left")
        self.titre.pack(fill="x")
        self.texte = tk.Label(corps, text="", font=P["petit"], fg=UI["encre2"], bg=UI["surface"], anchor="w",
                              justify="left", wraplength=px(330))
        self.texte.pack(fill="x", pady=(px(4), 0))
        self.boutons = tk.Frame(corps, bg=UI["surface"])
        self.boutons.pack(fill="x", pady=(px(12), 0))
        self._actions: tuple = ()

    def montrer(self, titre: str, texte: str, boutons: Sequence[Tuple[str, Callable[[], None], str]],
                lien: Optional[Tuple[str, Callable[[], None]]] = None) -> None:
        """boutons : [(libellé, action, "principal" ou "secondaire")] ; lien : (libellé, action)."""
        px, P = self.theme.px, self.theme.polices
        self.titre.configure(text=insecable(titre))
        self.texte.configure(text=insecable(texte))
        actions = (tuple(boutons), lien)
        if actions != self._actions:            # mêmes boutons et actions : seul le texte change
            self._actions = actions
            for widget in self.boutons.winfo_children():
                widget.destroy()
            for libelle, action, style in boutons:
                bouton = BoutonPlat(self.boutons, self.theme, libelle, action, style)
                bouton.configure(font=P["petit"], pady=px(5))
                bouton.pack(side="left", padx=(0, px(8)), ipadx=px(10))
            if lien is not None:
                Lien(self.boutons, self.theme, lien[0], lien[1], UI["surface"]).pack(side="right")
        self.boutons.pack_configure(pady=(px(12), 0) if boutons or lien else 0)
        self.place(relx=1.0, rely=1.0, x=-px(18), y=-px(18), anchor="se")
        self.lift()


class MiseAJourMixin:
    """Nouvelles versions dans la fenêtre principale : question posée une fois (vérifier au
    démarrage ?), carte « Version x disponible », téléchargement puis installation, entrées du
    menu Aide. Classe de base de Application (interface.py)."""

    def _init_mises_a_jour(self: "Application") -> None:
        self._carte: Optional[CarteInfo] = None
        self._carte_etat: Optional[tuple] = None        # ce que montre la carte (refait après un zoom)
        self._tache_maj: Optional[Tache] = None
        self._nouvelle: Optional[NouvelleVersion] = None

    def _menu_mises_a_jour(self: "Application", menu: tk.Menu) -> None:
        """Entrées du menu Aide : vérifier tout de suite, ou à chaque démarrage."""
        self.var_maj_auto = tk.BooleanVar(value=self.preferences.get("mises_a_jour") is True)
        menu.add_command(label="Rechercher une mise à jour", command=self.rechercher_mise_a_jour)
        menu.add_checkbutton(label="Vérifier les mises à jour au démarrage", variable=self.var_maj_auto,
                             command=self._basculer_maj_auto)

    # ------------------------------------------------------------------ carte
    def _montrer_carte(self: "Application", titre: str, texte: str,
                       boutons: Sequence[Tuple[str, Callable[[], None], str]] = (),
                       lien: Optional[Tuple[str, Callable[[], None]]] = None) -> None:
        self._carte_etat = (titre, texte, tuple(boutons), lien)
        if self._carte is None or not self._carte.winfo_exists():
            self._carte = CarteInfo(self, self.theme)
        self._carte.montrer(titre, texte, boutons, lien)

    def _cacher_carte(self: "Application") -> None:
        self._carte_etat = None
        if self._carte is not None and self._carte.winfo_exists():
            self._carte.place_forget()

    def _reafficher_carte(self: "Application") -> None:
        """Après la reconstruction de la fenêtre (taille du texte) : la carte, à la nouvelle échelle."""
        self._carte = None
        if self._carte_etat is not None:
            self._montrer_carte(*self._carte_etat)

    def _quand_libre(self: "Application", action: Callable[[], None]) -> None:
        """Lance `action` (une carte) quand la fenêtre est affichée, sans visite guidée ni
        question en cours : la carte ne gêne ni la visite ni une réponse attendue."""
        occupee = (not self.winfo_viewable() or self._dialogue is not None
                   or (self.visite is not None and self.visite.active))
        if occupee:
            self.after(1500, lambda: self._quand_libre(action))
        else:
            action()

    # ------------------------------------------------------------------ accord
    def _mises_a_jour_au_demarrage(self: "Application") -> None:
        """Lancement du programme : question (une fois) ou vérification discrète ; les installateurs
        des mises à jour déjà faites sont effacés du dossier temporaire."""
        nettoyer_telechargements()
        choix = self.preferences.get("mises_a_jour")
        if choix is None:
            self._quand_libre(self._proposer_mises_a_jour)
        elif choix is True:
            self._rechercher(discret=True)

    def _proposer_mises_a_jour(self: "Application") -> None:
        if self.preferences.get("mises_a_jour") is not None:     # réponse donnée entre-temps (menu)
            return
        self._montrer_carte(
            "Nouvelles versions",
            "Le programme peut vérifier à chaque démarrage si une nouvelle version est publiée, et vous "
            "proposer de l'installer. Il demande seulement à GitHub le numéro de la dernière version : "
            "rien d'autre n'est envoyé. Vous pourrez changer d'avis dans le menu Aide.",
            [("Oui, vérifier", lambda: self._choisir_maj_auto(True), "principal"),
             ("Non merci", lambda: self._choisir_maj_auto(False), "secondaire")])

    def _choisir_maj_auto(self: "Application", oui: bool) -> None:
        self.preferences["mises_a_jour"] = oui
        enregistrer_preferences(self.preferences)
        self.var_maj_auto.set(oui)
        self._cacher_carte()
        if oui:
            self._rechercher(discret=True)

    def _basculer_maj_auto(self: "Application") -> None:
        """Aide > Vérifier les mises à jour au démarrage (pris en compte au prochain lancement)."""
        self.preferences["mises_a_jour"] = bool(self.var_maj_auto.get())
        enregistrer_preferences(self.preferences)
        if self._carte_etat is not None and self._carte_etat[0] == "Nouvelles versions":
            self._cacher_carte()                                  # la question a trouvé sa réponse

    # ------------------------------------------------------------------ recherche
    def rechercher_mise_a_jour(self: "Application") -> None:
        """Aide > Rechercher une mise à jour : à la demande, même sans vérification au démarrage."""
        self._rechercher(discret=False)

    def _rechercher(self: "Application", discret: bool) -> None:
        """Recherche en arrière-plan. Discrète (démarrage) : rien ne s'affiche, sauf une nouvelle
        version ; à la demande : la carte dit aussi « à jour » ou ce qui empêche la recherche."""
        if self._tache_maj is not None and not self._tache_maj.fini:
            return
        if not discret:
            self._montrer_carte("Mises à jour", "Recherche d'une nouvelle version…")
        tache = self._tache_maj = Tache(lambda _t: chercher())
        self._suivre(tache, lambda: self._fin_recherche(tache, discret))

    def _suivre(self: "Application", tache: Tache, suite: Callable[[], None],
                avancement: Optional[Callable[[], None]] = None) -> None:
        """Attend la fin d'une tâche de fond sans bloquer la fenêtre."""
        def verifier() -> None:
            if not tache.fini:
                if avancement is not None:
                    avancement()
                self.after(150, verifier)
            else:
                suite()
        self.after(150, verifier)

    def _fin_recherche(self: "Application", tache: Tache, discret: bool) -> None:
        if tache.erreur is not None:
            if not isinstance(tache.erreur, ErreurMiseAJour):
                traceback.print_exception(type(tache.erreur), tache.erreur, tache.erreur.__traceback__)
            if not discret:
                self._montrer_carte("Mises à jour", str(tache.erreur) if isinstance(tache.erreur, ErreurMiseAJour)
                                    else "La recherche a échoué.", [("Fermer", self._cacher_carte, "secondaire")],
                                    ("Page des versions", lambda: ouvrir_document(DEPOT + "/releases")))
            return
        if tache.resultat is None:
            if not discret:
                self._montrer_carte("Mises à jour", f"Vous avez la dernière version ({VERSION}).",
                                    [("OK", self._cacher_carte, "secondaire")])
            return
        self._nouvelle = tache.resultat
        self._quand_libre(self._annoncer_version)

    def _annoncer_version(self: "Application") -> None:
        nouvelle = self._nouvelle
        page = (lambda: ouvrir_document(nouvelle.page))
        if getattr(sys, "frozen", False):                         # programme installé
            texte = ("Une nouvelle version de Filtres de Butterworth est publiée. L'installation ferme le "
                     "programme, puis le rouvre ; vos préférences et votre saisie sont gardées.")
            boutons = [("Installer", self._installer, "principal"), ("Plus tard", self._cacher_carte, "secondaire")]
        else:                                                     # lancé depuis Python (main.py)
            texte = ("Une nouvelle version est publiée. Ce programme est lancé depuis Python : prenez son code "
                     "ou son installateur sur la page de la version.")
            boutons = [("Voir la version", page, "principal"), ("Plus tard", self._cacher_carte, "secondaire")]
        self._montrer_carte(f"Version {nouvelle.version} disponible", texte, boutons, ("Nouveautés", page))

    # ------------------------------------------------------------------ installation
    def _installer(self: "Application") -> None:
        """Téléchargement de l'installateur (avec progression et Annuler), puis installation."""
        nouvelle = self._nouvelle
        if nouvelle is None or (self._tache_maj is not None and not self._tache_maj.fini):
            return
        self._montrer_carte(f"Version {nouvelle.version}", "Téléchargement…",
                            [("Annuler", lambda: tache.annulee.set(), "secondaire")])

        def travail(t: Tache) -> str:
            return telecharger(nouvelle, lambda fait, total: setattr(t, "avancement", (fait, total)), t.annulee)
        tache = self._tache_maj = Tache(travail)
        self._suivre(tache, lambda: self._fin_telechargement(tache), lambda: self._avancement(tache))

    def _avancement(self: "Application", tache: Tache) -> None:
        if self._carte_etat is None or tache.annulee.is_set():
            return
        fait, total = tache.avancement
        texte = (f"Téléchargement… {100 * fait // total} % ({fait / 1e6:.0f} Mo sur {total / 1e6:.0f} Mo)"
                 if total else f"Téléchargement… {fait / 1e6:.1f} Mo")
        titre, _texte, boutons, lien = self._carte_etat
        self._montrer_carte(titre, texte, boutons, lien)

    def _fin_telechargement(self: "Application", tache: Tache) -> None:
        if tache.annulee.is_set():
            self._cacher_carte()
            return
        if tache.erreur is not None:
            if not isinstance(tache.erreur, ErreurMiseAJour):
                traceback.print_exception(type(tache.erreur), tache.erreur, tache.erreur.__traceback__)
            message = str(tache.erreur) if isinstance(tache.erreur, ErreurMiseAJour) else "Le téléchargement a échoué."
            self._montrer_carte(f"Version {self._nouvelle.version}", message,
                                [("Réessayer", self._installer, "principal"), ("Fermer", self._cacher_carte, "secondaire")],
                                ("Page de la version", lambda: ouvrir_document(self._nouvelle.page)))
            return
        self._installer_et_fermer(tache.resultat)

    def _installer_et_fermer(self: "Application", installateur: str) -> None:
        """Ferme le programme (en proposant d'enregistrer le filtre) et lance l'installateur, qui
        rouvre le programme une fois la nouvelle version en place."""
        version = self._nouvelle.version
        if not self._confirmer_abandon("mise_a_jour"):
            self._montrer_carte(f"Version {version} prête", "L'installation attend votre feu vert : elle "
                                "fermera le programme, puis le rouvrira.",
                                [("Installer", lambda: self._installer_et_fermer(installateur), "principal"),
                                 ("Plus tard", self._cacher_carte, "secondaire")])
            return
        try:
            self._garder_session()
        except Exception:
            traceback.print_exc()
        try:
            lancer_installation(installateur)
        except OSError:
            traceback.print_exc()
            self._montrer_carte(f"Version {version}", "L'installateur n'a pas pu être lancé. Vous pouvez le lancer "
                                f"vous-même : {installateur}", [("Fermer", self._cacher_carte, "secondaire")],
                                ("Page de la version", lambda: ouvrir_document(self._nouvelle.page)))
            return
        self.destroy()
