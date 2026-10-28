"""Réécrit requirements.txt, render.yaml et Procfile pour le déploiement. Lancer : python patch_render.py"""
START = "gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60 --access-logfile - --error-logfile - --log-level info"

FILES = {
"requirements.txt": "Flask>=3.0\nopenpyxl>=3.1\nreportlab>=4.0\ngunicorn==23.0.0\n",
"Procfile": "web: " + START + "\n",
"render.yaml": f"""# Déploiement Render (plan gratuit).
services:
  - type: web
    name: ciat-dashboard
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: {START}
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.7
      - key: PYTHONUNBUFFERED
        value: "1"
      - key: SECRET_KEY
        generateValue: true
      - key: COOKIE_SECURE
        value: "1"
      - key: ADMIN_PASSWORD
        sync: false
      - key: COORDO_PASSWORD
        sync: false
      - key: LECTEUR_PASSWORD
        sync: false
""",
}
for name, content in FILES.items():
    with open(name, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(name, "réécrit")
