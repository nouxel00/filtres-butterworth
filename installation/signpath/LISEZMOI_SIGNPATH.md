# Signature du programme avec SignPath (gratuite pour les logiciels libres)

La SignPath Foundation signe gratuitement les logiciels libres dont les fichiers sont
construits automatiquement à partir de leur dépôt public. Pour ce projet :

- les fichiers sont construits par le workflow GitHub Actions `.github/workflows/windows.yml`,
  sur les machines de GitHub ;
- deux fichiers sont signés : `FiltresButterworth.exe` (le programme), puis
  `Installer_FiltresButterworth_<version>.exe` (l'installateur, construit avec le programme
  déjà signé) ;
- chaque demande de signature doit être approuvée à la main, dans SignPath, par
  l'approbateur du projet.

Ce que verront les utilisateurs : l'éditeur affiché est « SignPath Foundation ». L'avertissement
« Windows a protégé votre ordinateur » peut rester un temps : Windows attend que le programme
signé ait été téléchargé assez souvent.

## 1. Avant la demande

1. Activer l'authentification à deux facteurs sur le compte GitHub (et plus tard sur
   SignPath) : SignPath l'exige de chaque membre de l'équipe.
2. Vérifier que le workflow « Windows » réussit (onglet Actions du dépôt).
3. Publier la version 2.0 : onglet Releases du dépôt, « Draft a new release », nouvelle
   étiquette `v2.0` sur la branche `main`, puis « Publish release ». Le workflow construit
   l'installateur et le joint à la Release, encore sans signature.

## 2. La demande

Formulaire : <https://signpath.org/apply>. Texte prêt à copier (en anglais, comme le
formulaire) :

- **Project name:** Filtres de Butterworth
- **Repository:** https://github.com/nouxel00/filtres-butterworth
- **License:** MIT
- **Download page:** https://github.com/nouxel00/filtres-butterworth/releases
- **Description:** Filtres de Butterworth is a free Windows desktop application (Python and
  Tkinter, packaged with PyInstaller and Inno Setup) that designs analog Butterworth filters
  built with unity-gain Sallen-Key cells. From a frequency template, it computes the minimal
  order, the normalized and real transfer functions with step-by-step calculations, the
  component values (exact or E6/E12/E24 series, with an automatic correction when rounded
  values break the template), the wiring diagram with µA741 op-amps, SPICE netlists for
  LTspice and PSpice, and a PDF report. It also includes a ten-chapter beginner course on
  Sallen-Key filters. The user interface is in French. Binaries are built by GitHub Actions
  on GitHub-hosted runners from this repository and published as GitHub Releases. The code
  signing policy is in the README.
- **Contact:** une adresse e-mail que tu consultes : SignPath répond par e-mail.

SignPath demande aussi une « réputation vérifiable » : un projet tout neuf peut être mis
en attente. Une Release publiée, un README clair et quelques utilisateurs aident.

## 3. Après l'acceptation

Dans SignPath (le projet créé pour toi) :

1. Relier le « Trusted Build System » **GitHub.com** au projet, et installer l'application
   GitHub de SignPath sur le dépôt.
2. Créer deux configurations d'artefact, avec ces identifiants (slugs) et ces fichiers :
   - `programme` : contenu de `installation/signpath/programme.xml` ;
   - `installateur` : contenu de `installation/signpath/installateur.xml`.
3. Dans la politique de signature (signing policy) : cocher « Verify origin » et limiter les
   branches autorisées à `main` (et aux étiquettes `v*` si SignPath le propose, pour les
   Releases).
4. Créer un jeton d'API (API token) pour un utilisateur qui peut soumettre des demandes.

Dans GitHub (Settings > Secrets and variables > Actions) :

| Nom | Type | Valeur |
| --- | --- | --- |
| `SIGNPATH_API_TOKEN` | secret | le jeton d'API SignPath |
| `SIGNPATH_ORGANIZATION_ID` | variable | l'identifiant de l'organisation SignPath |
| `SIGNPATH_PROJECT_SLUG` | variable | l'identifiant (slug) du projet SignPath |
| `SIGNPATH_SIGNING_POLICY_SLUG` | variable | l'identifiant de la politique de signature |

Dès que ces variables existent, le workflow envoie les deux fichiers à SignPath et attend
la signature (à approuver dans SignPath). Sans elles, il construit sans signer.

Enfin, dans le README, remplacer la phrase « demande en cours » de la politique de
signature par la phrase demandée par SignPath :

> Free code signing provided by [SignPath.io](https://signpath.io), certificate by
> [SignPath Foundation](https://signpath.org)

puis publier une nouvelle Release (par exemple l'étiquette `v2.0.1`, après avoir mis le
même numéro dans `interface.py` et `installation/installateur.iss`).
