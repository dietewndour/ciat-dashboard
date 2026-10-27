"""Génère un jeu de données FICTIF et reproductible (graine fixe).

Les noms, projets, partenaires et montants sont inventés pour la démonstration.
Ils ne représentent aucune donnée réelle du CIAT. Voir docs/DICTIONNAIRE_DONNEES.md.
"""
import os
import random
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from db import init_db

TODAY = date(2026, 10, 27)

DOMAINS = [
    "TIC, numérique, IA et données",
    "Mécanique, fabrication et maintenance",
    "Agriculture, transformation et environnement",
    "Énergie et énergies renouvelables",
    "Pharmaceutique et biomédical",
    "Éducation, formation et insertion",
    "Services aux collectivités et entrepreneuriat",
]
# (nom, début, fin)
COHORTS = [
    ("Cohorte 2023", "2023-02-01", "2023-12-15"),
    ("Cohorte 2024", "2024-02-01", "2024-12-15"),
    ("Cohorte 2025", "2025-02-01", "2025-12-15"),
    ("Cohorte 2026", "2026-02-01", "2026-12-15"),
]
FIRST_F = ["Aminata", "Fatou", "Awa", "Khady", "Mariama", "Ndeye", "Coumba", "Astou", "Rokhaya", "Sokhna"]
FIRST_M = ["Ousmane", "Mamadou", "Cheikh", "Ibrahima", "Moussa", "Abdoulaye", "Modou", "Pape", "Alioune", "Samba"]
LAST = ["Diop", "Ndiaye", "Fall", "Sow", "Ba", "Sarr", "Faye", "Gueye", "Diallo", "Mbaye", "Cissé", "Thiam"]
TITLES = {
    0: ["Application de suivi des stocks", "Plateforme de télémédecine", "Chatbot de services communaux", "Capteurs IoT pour serres"],
    1: ["Presse à briques recyclées", "Atelier de maintenance mobile", "Imprimante 3D locale", "Décortiqueuse à arachide"],
    2: ["Séchoir solaire pour mangues", "Compost de déchets de marché", "Irrigation goutte à goutte", "Transformation du fonio"],
    3: ["Kit solaire domestique", "Biodigesteur familial", "Lampadaire solaire autonome", "Pompe solaire villageoise"],
    4: ["Pommade à base de plantes", "Diagnostic rapide du paludisme", "Gestion des ordonnances", "Savon antiseptique local"],
    5: ["Plateforme de cours en ligne", "Atelier de soudure pour jeunes", "Jeu éducatif en wolof", "Orientation professionnelle"],
    6: ["Collecte de déchets par application", "Coopérative de transport", "Marché en ligne de quartier", "Gestion des cantines"],
}
PARTNERS = ["Mairie de Diamniadio", "Orange Digital Center", "SONATEL", "ADEPME", "DER/FJ", "GIZ Sénégal",
            "Université de Thiès", "CCIAD", "Banque Agricole", "Expertise France"]
FUND_SOURCES = ["DER/FJ", "ADEPME", "GIZ Sénégal", "Fonds propres", "Banque Agricole", "Mécénat privé"]
MILESTONES = ["Cahier des charges validé", "Maquette validée", "Premier prototype", "Test utilisateurs", "Plan d'affaires final"]


def _d(d):
    return d.isoformat() if d else None


def build(path, seed=42, n_projects=96):
    rnd = random.Random(seed)
    if os.path.exists(path):
        os.remove(path)
    init_db(path)
    con = sqlite3.connect(path)
    cur = con.cursor()

    cur.executemany("INSERT INTO domains(name) VALUES (?)", [(d,) for d in DOMAINS])
    cur.executemany("INSERT INTO cohorts(name,start_date,end_date) VALUES (?,?,?)", COHORTS)

    users = [
        ("admin", "Administrateur CIAT", "admin", os.environ.get("ADMIN_PASSWORD", "Admin#2026")),
        ("coordo", "Coordonnateur de l'incubateur", "coordinateur", os.environ.get("COORDO_PASSWORD", "Coordo#2026")),
        ("lecteur", "Membre du comité", "lecteur", os.environ.get("LECTEUR_PASSWORD", "Lecteur#2026")),
    ]
    for u, n, r, p in users:
        cur.execute("INSERT INTO users(username,full_name,password_hash,role) VALUES (?,?,?,?)",
                    (u, n, generate_password_hash(p), r))

    # Pondération : TIC et agriculture plus fréquents ; femmes ~40 %
    dom_weights = [28, 10, 18, 14, 8, 12, 10]
    for i in range(n_projects):
        cohort_idx = rnd.choices([0, 1, 2, 3], weights=[18, 24, 28, 30])[0]
        c_name, c_start, c_end = COHORTS[cohort_idx]
        c_start_d = date.fromisoformat(c_start)
        dom = rnd.choices(range(7), weights=dom_weights)[0]
        gender = "F" if rnd.random() < 0.40 else "M"
        first = rnd.choice(FIRST_F if gender == "F" else FIRST_M)
        owner = f"{first} {rnd.choice(LAST)}"
        title = rnd.choice(TITLES[dom])
        submitted = c_start_d - timedelta(days=rnd.randint(10, 80))
        old = cohort_idx <= 1
        roll = rnd.random()
        # Les anciennes cohortes avancent plus loin dans le parcours
        if roll < (0.25 if old else 0.40):
            status = "idee"
        elif roll < (0.32 if old else 0.52):
            status = "abandonne"
        elif roll < (0.45 if old else 0.70):
            status = "selectionne"
        elif roll < (0.62 if old else 0.84):
            status = "incube"
        elif roll < (0.82 if old else 0.95):
            status = "prototype"
        else:
            status = "termine"
        selected = prototype = None
        progress = 0
        if status in ("selectionne", "incube", "prototype", "termine"):
            selected = c_start_d + timedelta(days=rnd.randint(5, 40))
            progress = {"selectionne": rnd.randint(5, 25), "incube": rnd.randint(25, 65),
                        "prototype": rnd.randint(60, 90), "termine": 100}[status]
        if status in ("prototype", "termine"):
            prototype = selected + timedelta(days=rnd.randint(60, 200))
            if prototype > TODAY:
                prototype = TODAY - timedelta(days=rnd.randint(1, 30))
        if status == "abandonne":
            progress = rnd.randint(0, 20)
        desc = f"Projet fictif de démonstration dans le domaine « {DOMAINS[dom]} »."
        cur.execute(
            """INSERT INTO projects(title,owner_name,owner_gender,domain_id,cohort_id,status,
               submitted_on,selected_on,prototype_on,progress_pct,description)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (title, owner, gender, dom + 1, cohort_idx + 1, status, _d(submitted),
             _d(selected), _d(prototype), progress, desc))
        pid = cur.lastrowid

        if selected and status != "abandonne":
            n_ms = rnd.randint(3, 5)
            for k in range(n_ms):
                due = selected + timedelta(days=45 * (k + 1))
                done = None
                # Un jalon passé est le plus souvent terminé ; ~20 % en retard
                if due <= TODAY and rnd.random() < 0.80 or status == "termine":
                    done = due + timedelta(days=rnd.randint(-10, 15))
                    if done > TODAY:
                        done = TODAY
                cur.execute("INSERT INTO milestones(project_id,label,due_on,done_on) VALUES (?,?,?,?)",
                            (pid, MILESTONES[k], _d(due), _d(done)))
            if rnd.random() < 0.55:
                for _ in range(rnd.randint(1, 2)):
                    st = rnd.choices(["en_discussion", "signe", "termine"], weights=[3, 5, 1])[0]
                    signed = _d(selected + timedelta(days=rnd.randint(20, 150))) if st != "en_discussion" else None
                    cur.execute("INSERT INTO partnerships(project_id,partner_name,kind,status,signed_on) VALUES (?,?,?,?,?)",
                                (pid, rnd.choice(PARTNERS),
                                 rnd.choice(["technique", "financier", "institutionnel", "commercial"]), st, signed))
            if rnd.random() < 0.50:
                amount = rnd.choice([500_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000, 5_000_000])
                fs = rnd.choices(["demande", "accorde", "verse"], weights=[2, 3, 4])[0]
                cur.execute("INSERT INTO fundings(project_id,source,amount_fcfa,status,decided_on) VALUES (?,?,?,?,?)",
                            (pid, rnd.choice(FUND_SOURCES), amount, fs,
                             _d(selected + timedelta(days=rnd.randint(30, 200))) if fs != "demande" else None))
    con.commit()
    con.close()


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "instance/ciat.db"
    build(target)
    print(f"Base créée : {target}")
