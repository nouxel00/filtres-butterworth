"""Essai de bout en bout sous Windows : avec le code de mise_a_jour.py, la version installée
(2.0) trouve la 2.1 sur le faux GitHub, la télécharge, la vérifie, puis lance l'installateur
comme le fait le programme (variables d'un programme PyInstaller comprises), et le programme
2.0 en cours se ferme aussitôt, comme après « Installer ». Usage :
    python essais/mise_a_jour_windows.py <dépôt> <programme installé> <pid du programme 2.0>"""
import os, subprocess, sys, time
sys.path.insert(0, os.getcwd())
import mise_a_jour as maj

DEPOT, PROGRAMME, PID = sys.argv[1], sys.argv[2], int(sys.argv[3])
nouvelle = maj.chercher("2.0", DEPOT)
print("trouvée :", nouvelle, flush=True)
assert nouvelle is not None and nouvelle.version == "2.1", nouvelle
suivi = []
chemin = maj.telecharger(nouvelle, lambda fait, total: suivi.append((fait, total)))
print("téléchargé :", chemin, os.path.getsize(chemin), "octets ;", len(suivi), "étapes", flush=True)
commande = maj.commande_installation(chemin, PROGRAMME)
print("commande :", commande, flush=True)
attendu = "/ALLUSERS" if maj.installe_pour_tous(PROGRAMME) else "/CURRENTUSER"
assert attendu in commande
# Variables qu'un programme PyInstaller transmet à ce qu'il lance : retirées pour l'installateur
os.environ.update({"_PYI_APPLICATION_HOME_DIR": os.path.dirname(PROGRAMME), "_PYI_PARENT_PROCESS_LEVEL": "1",
                   "_MEIPASS2": os.path.dirname(PROGRAMME), "TCL_LIBRARY": r"C:\nulle\part\tcl",
                   "TK_LIBRARY": r"C:\nulle\part\tk"})
debut = time.time()
installation = maj.lancer_installation(chemin, PROGRAMME)
time.sleep(0.5)
subprocess.run(["taskkill", "/PID", str(PID), "/F"], capture_output=True)   # le programme se ferme
code = installation.wait(timeout=900)
print(f"installateur terminé : code {code} en {time.time() - debut:.0f} s", flush=True)
sys.exit(code)
