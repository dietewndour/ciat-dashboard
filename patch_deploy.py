"""Applique les changements de déploiement à seed.py et app.py. Lancer : python patch_deploy.py"""
import io

def patch(path, pairs):
    with io.open(path, encoding="utf-8", newline="") as f:
        txt = f.read()
    changed = False
    for old, new in pairs:
        if new in txt:
            continue
        if old not in txt:
            raise SystemExit(f"ERREUR : motif introuvable dans {path}. Envoyez ce message à Claude.")
        txt = txt.replace(old, new, 1)
        changed = True
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt)
    print(path, "modifié" if changed else "déjà à jour")

patch("seed.py", [
    ('"Admin#2026"),', 'os.environ.get("ADMIN_PASSWORD", "Admin#2026")),'),
    ('"Coordo#2026"),', 'os.environ.get("COORDO_PASSWORD", "Coordo#2026")),'),
    ('"Lecteur#2026"),', 'os.environ.get("LECTEUR_PASSWORD", "Lecteur#2026")),'),
])
patch("app.py", [
    ('        app.config.update(config)\n',
     '        app.config.update(config)\n'
     '    if app.config["SESSION_COOKIE_SECURE"] and app.config["SECRET_KEY"] == "dev-only-change-me":\n'
     '        raise RuntimeError("SECRET_KEY doit être défini en production (COOKIE_SECURE=1).")\n'),
])
