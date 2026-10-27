"""Assistant d'interrogation en langage naturel.

Principe de sécurité et d'honnêteté :
- L'IA (si une clé API est configurée) ne fait QUE traduire la question en une spécification
  JSON (indicateur, regroupement, filtres). Elle n'écrit jamais de SQL.
- La spécification est validée contre des listes blanches, puis exécutée par analytics.py.
- La réponse affichée est construite par le code à partir des chiffres réels de la base.
  Le modèle ne rédige aucun chiffre.
- Si la question ne peut pas être traduite, l'assistant répond qu'il ne sait pas.
Sans clé API, un analyseur à règles (mots-clés) prend le relais.
"""
import json
import os
import re
import unicodedata
import urllib.request

import analytics as an

API_URL = "https://api.anthropic.com/v1/messages"


def _norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _context(db):
    cohorts = {r["id"]: r["name"] for r in db.execute("SELECT id,name FROM cohorts ORDER BY id")}
    domains = {r["id"]: r["name"] for r in db.execute("SELECT id,name FROM domains ORDER BY id")}
    return cohorts, domains


# ---------- Analyse à règles ----------
METRIC_KW = [
    ("funding", ["financ", "fcfa", "budget", "montant", "argent"]),
    ("delayed", ["retard"]),
    ("partnerships", ["partenar"]),
    ("prototypes", ["prototype"]),
    ("selected", ["selectionn", "retenu"]),
    ("avg_progress", ["progress", "avancement"]),
    ("projects", ["idee", "projet", "candidat", "combien", "nombre"]),
]
DOMAIN_KW = {
    1: ["tic", "numerique", "intelligence artificielle", " ia ", "donnees"],
    2: ["mecanique", "fabrication", "maintenance"],
    3: ["agricult", "transformation", "environnement"],
    4: ["energie", "solaire"],
    5: ["pharma", "biomedical"],
    6: ["education", "formation", "insertion"],
    7: ["collectivite", "entrepreneuriat", "incubation"],
}
STATUS_KW = {"abandonne": "abandon", "termine": "termine", "incube": "en incubation"}


def parse_rules(question, db):
    q = " " + _norm(question) + " "
    cohorts, domains = _context(db)
    spec = {"metric": None, "group_by": None, "filters": {}}
    for metric, kws in METRIC_KW:
        if any(k in q for k in kws):
            spec["metric"] = metric
            break
    if spec["metric"] is None:
        return None
    if re.search(r"par domaine|selon (le )?domaine|chaque domaine", q):
        spec["group_by"] = "domain"
    elif re.search(r"par cohorte|chaque cohorte|compar|evolution", q):
        spec["group_by"] = "cohort"
    elif re.search(r"par genre|par sexe|repartition (par )?(genre|sexe)", q):
        spec["group_by"] = "gender"
    elif re.search(r"par statut|par etape", q):
        spec["group_by"] = "status"
    for cid, name in cohorts.items():
        year = re.search(r"\d{4}", name)
        if year and year.group() in q:
            spec["filters"]["cohort_id"] = cid
    for did, kws in DOMAIN_KW.items():
        if "par domaine" not in q and any(k in q for k in kws):
            spec["filters"]["domain_id"] = did
            break
    if re.search(r"\bfemmes?\b|porteuses?", q) and spec["group_by"] != "gender":
        spec["filters"]["gender"] = "F"
    elif re.search(r"\bhommes?\b", q) and spec["group_by"] != "gender":
        spec["filters"]["gender"] = "M"
    for st, kw in STATUS_KW.items():
        if kw in q and spec["metric"] == "projects":
            spec["filters"]["status"] = st
    return spec


# ---------- Analyse par IA générative ----------
def _llm_spec(question, db):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    cohorts, domains = _context(db)
    system = (
        "Tu traduis une question en français sur le suivi du CIAT en une spécification JSON. "
        "Réponds uniquement par un objet JSON, sans texte autour.\n"
        'Format : {"metric": ..., "group_by": ..., "filters": {...}} ou {"unsupported": true}.\n'
        f"metric parmi : {list(an.METRICS)} (projects=idées reçues, selected=sélectionnés, "
        "prototypes, delayed=en retard, avg_progress, funding=FCFA, partnerships=signés).\n"
        f"group_by : null ou parmi {list(an.GROUPS)}.\n"
        f"filters, clés facultatives : cohort_id parmi {cohorts}; domain_id parmi {domains}; "
        f"status parmi {list(an.STATUS_LABELS)}; gender parmi F, M.\n"
        'Si la question ne se ramène pas à ces champs, réponds {"unsupported": true}. N\'invente rien.'
    )
    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        "max_tokens": 300,
        "system": system,
        "messages": [{"role": "user", "content": question[:500]}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group()) if m else None


def validate(spec, db):
    """Ne garde que des valeurs de la liste blanche. Renvoie None si inutilisable."""
    if not isinstance(spec, dict) or spec.get("unsupported"):
        return None
    metric = spec.get("metric")
    group = spec.get("group_by")
    if metric not in an.METRICS or group not in (None, *an.GROUPS):
        return None
    cohorts, domains = _context(db)
    f = {}
    raw = spec.get("filters") or {}
    if isinstance(raw, dict):
        if raw.get("cohort_id") in cohorts:
            f["cohort_id"] = raw["cohort_id"]
        if raw.get("domain_id") in domains:
            f["domain_id"] = raw["domain_id"]
        if raw.get("status") in an.STATUS_LABELS:
            f["status"] = raw["status"]
        if raw.get("gender") in an.GENDER_LABELS:
            f["gender"] = raw["gender"]
    return {"metric": metric, "group_by": group, "filters": f}


def describe(spec, db):
    cohorts, domains = _context(db)
    label = an.METRICS[spec["metric"]][0]
    parts = [label]
    if spec["group_by"]:
        parts.append(f"par {an.GROUPS[spec['group_by']][0].lower()}")
    f = spec["filters"]
    if "cohort_id" in f: parts.append(f"cohorte : {cohorts[f['cohort_id']]}")
    if "domain_id" in f: parts.append(f"domaine : {domains[f['domain_id']]}")
    if "status" in f: parts.append(f"statut : {an.STATUS_LABELS[f['status']]}")
    if "gender" in f: parts.append(f"genre : {an.GENDER_LABELS[f['gender']]}")
    return " | ".join(parts)


def answer(question, db, base_filters=None):
    """Retourne un dict : ok, mode, interpretation, text, rows, unit."""
    question = (question or "").strip()
    if len(question) < 3:
        return {"ok": False, "mode": "aucun", "text": "Posez une question plus complète."}
    spec, mode = None, "regles"
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            spec = validate(_llm_spec(question, db), db)
            mode = "ia"
        except Exception:  # réseau, quota, JSON invalide : on retombe sur les règles
            spec = None
    if spec is None:
        mode = "regles"
        spec = validate(parse_rules(question, db), db)
    if spec is None:
        return {"ok": False, "mode": mode,
                "text": "Je ne sais pas répondre à cette question avec les données disponibles. "
                        "Je peux compter les idées, sélections, prototypes, retards, partenariats "
                        "et financements, par domaine, cohorte, genre ou statut."}
    filters = dict(base_filters or {})
    filters.update(spec["filters"])
    rows = an.aggregate(db, filters, spec["metric"], spec["group_by"])
    unit = an.METRICS[spec["metric"]][2]
    if spec["group_by"] is None:
        text = f"{an.METRICS[spec['metric']][0]} : {an.fmt(rows[0][1], unit)}."
    elif not rows:
        text = "Aucune donnée ne correspond à cette question."
    else:
        text = "; ".join(f"{k} : {an.fmt(v, unit)}" for k, v in rows) + "."
    return {"ok": True, "mode": mode, "interpretation": describe(spec, db), "text": text,
            "rows": [list(r) for r in rows], "unit": unit}
