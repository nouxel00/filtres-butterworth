"""Faux GitHub local (essai de bout en bout sous Windows) : la dernière Release est v<version>,
avec l'installateur construit (dist) et son fichier .sha256. Usage :
    python essais/faux_github.py <port> <version> <installateur>"""
import hashlib, http.server, os, sys

PORT, VERSION, INSTALLATEUR = int(sys.argv[1]), sys.argv[2], sys.argv[3]
CONTENU = open(INSTALLATEUR, "rb").read()
NOM = os.path.basename(INSTALLATEUR)
EMPREINTE = hashlib.sha256(CONTENU).hexdigest()


class Gestion(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        sys.stderr.write("faux GitHub : " + (a[0] % a[1:]) + "\n")

    def do_HEAD(self):
        self.repondre(False)

    def do_GET(self):
        self.repondre(True)

    def repondre(self, corps):
        if self.path == "/depot/releases/latest":
            self.send_response(302)
            self.send_header("Location", f"/depot/releases/tag/v{VERSION}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        donnees = {f"/depot/releases/tag/v{VERSION}": b"<html>Release</html>",
                   f"/depot/releases/download/v{VERSION}/{NOM}": CONTENU,
                   f"/depot/releases/download/v{VERSION}/{NOM}.sha256": f"{EMPREINTE}  {NOM}\n".encode()}.get(self.path)
        self.send_response(200 if donnees is not None else 404)
        self.send_header("Content-Length", str(len(donnees or b"")))
        self.end_headers()
        if corps and donnees:
            self.wfile.write(donnees)


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Gestion).serve_forever()
