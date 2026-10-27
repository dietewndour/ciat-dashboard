"""Indicateurs et agrégations du tableau de bord.

Toutes les requêtes sont paramétrées. Les noms de colonnes ou de tables ne viennent
jamais de l'utilisateur : ils sont choisis dans les listes blanches ci-dessous.
"""
from datetime import date, datetime

TODAY = date(2026, 10, 27)  # date de référence des retards ; remplacée par date.today() en production
USE_REAL_TODAY = False


def today():
    return date.today() if USE_REAL_TODAY else TODAY


STATUS_LABELS = {
    "idee": "Idée reçue", "selectionne": "Sélectionné", "incube": "En incubation",
    "prototype": "Prototype", "termine": "Terminé", "abandonne": "Abandonné",
}
GENDER_LABELS = {"F": "Femmes", "M": "Hommes"}

# Expressions SQL par indicateur (calculées par projet, puis agrégées)
DELAYED = ("EXISTS (SELECT 1 FROM milestones m WHERE m.project_id = p.id "
           "AND m.done_on IS NULL AND m.due_on < :today)")
METRICS = {
    "projects": ("Idées reçues", "COUNT(*)", "nombre"),
    "selected": ("Projets sélectionnés", "COALESCE(SUM(p.selected_on IS NOT NULL),0)", "nombre"),
    "prototypes": ("Prototypes réalisés", "COALESCE(SUM(p.prototype_on IS NOT NULL),0)", "nombre"),
    "delayed": ("Projets en retard", f"COALESCE(SUM({DELAYED}),0)", "nombre"),
    "avg_progress": ("Progression moyenne des projets sélectionnés",
                     "ROUND(AVG(CASE WHEN p.selected_on IS NOT NULL THEN p.progress_pct END),1)", "pct"),
    "funding": ("Financements accordés ou versés",
                "COALESCE(SUM((SELECT COALESCE(SUM(f.amount_fcfa),0) FROM fundings f "
                "WHERE f.project_id = p.id AND f.status IN ('accorde','verse'))),0)", "fcfa"),
    "partnerships": ("Partenariats signés",
                     "COALESCE(SUM((SELECT COUNT(*) FROM partnerships s "
                     "WHERE s.project_id = p.id AND s.status = 'signe')),0)", "nombre"),
}
GROUPS = {
    "domain": ("Domaine", "d.name"),
    "cohort": ("Cohorte", "c.name"),
    "gender": ("Genre", "p.owner_gender"),
    "status": ("Statut", "p.status"),
}
FROM = "FROM projects p JOIN domains d ON d.id = p.domain_id JOIN cohorts c ON c.id = p.cohort_id"


def _iso(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def clean_filters(args):
    """Valide les filtres reçus (dict-like) et renvoie un dict propre."""
    f = {}
    for key in ("cohort_id", "domain_id"):
        v = args.get(key)
        if v and str(v).isdigit():
            f[key] = int(v)
    if args.get("status") in STATUS_LABELS:
        f["status"] = args["status"]
    if args.get("gender") in GENDER_LABELS:
        f["gender"] = args["gender"]
    for key in ("date_from", "date_to"):
        v = _iso(args.get(key))
        if v:
            f[key] = v
    owner = (args.get("owner") or "").strip()[:60]
    if owner:
        f["owner"] = owner
    return f


def where(f):
    clauses, params = ["1=1"], {"today": today().isoformat()}
    if "cohort_id" in f:
        clauses.append("p.cohort_id = :cohort_id"); params["cohort_id"] = f["cohort_id"]
    if "domain_id" in f:
        clauses.append("p.domain_id = :domain_id"); params["domain_id"] = f["domain_id"]
    if "status" in f:
        clauses.append("p.status = :status"); params["status"] = f["status"]
    if "gender" in f:
        clauses.append("p.owner_gender = :gender"); params["gender"] = f["gender"]
    if "date_from" in f:
        clauses.append("p.submitted_on >= :date_from"); params["date_from"] = f["date_from"]
    if "date_to" in f:
        clauses.append("p.submitted_on <= :date_to"); params["date_to"] = f["date_to"]
    if "owner" in f:
        clauses.append("p.owner_name LIKE :owner ESCAPE '\\'")
        esc = f["owner"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["owner"] = f"%{esc}%"
    return " AND ".join(clauses), params


def kpis(db, f):
    w, params = where(f)
    out = {}
    for key, (label, expr, unit) in METRICS.items():
        val = db.execute(f"SELECT {expr} {FROM} WHERE {w}", params).fetchone()[0]
        out[key] = {"label": label, "value": val, "unit": unit}
    total = out["projects"]["value"]
    sel = out["selected"]["value"]
    out["selection_rate"] = {"label": "Taux de sélection",
                             "value": round(100 * sel / total, 1) if total else None, "unit": "pct"}
    return out


def aggregate(db, f, metric, group_by=None):
    """Renvoie une liste de (libellé, valeur). metric et group_by sont validés par liste blanche."""
    if metric not in METRICS:
        raise ValueError("indicateur inconnu")
    w, params = where(f)
    expr = METRICS[metric][1]
    if group_by is None:
        val = db.execute(f"SELECT {expr} {FROM} WHERE {w}", params).fetchone()[0]
        return [("Total", val)]
    if group_by not in GROUPS:
        raise ValueError("regroupement inconnu")
    col = GROUPS[group_by][1]
    order = {"cohort": "MIN(c.id)", "status": "MIN(p.id)"}.get(group_by, "2 DESC")
    rows = db.execute(f"SELECT {col} AS k, {expr} AS v {FROM} WHERE {w} GROUP BY {col} ORDER BY {order}",
                      params).fetchall()
    out = []
    for k, v in rows:
        if group_by == "gender":
            k = GENDER_LABELS.get(k, k)
        elif group_by == "status":
            k = STATUS_LABELS.get(k, k)
        out.append((k, v))
    if group_by == "status":
        rank = list(STATUS_LABELS.values())
        out.sort(key=lambda r: rank.index(r[0]) if r[0] in rank else 99)
    return out


def monthly_ideas(db, f):
    w, params = where(f)
    return db.execute(
        f"SELECT strftime('%Y-%m', p.submitted_on) AS m, COUNT(*) {FROM} WHERE {w} GROUP BY m ORDER BY m",
        params).fetchall()


def cohort_comparison(db, f):
    labels = [r[0] for r in aggregate(db, f, "projects", "cohort")]
    series = {}
    for key in ("projects", "selected", "prototypes"):
        d = dict(aggregate(db, f, key, "cohort"))
        series[METRICS[key][0]] = [d.get(l, 0) for l in labels]
    return {"labels": labels, "series": series}


def delayed_projects(db, f, limit=10):
    w, params = where(f)
    return db.execute(
        f"""SELECT p.id, p.title, p.owner_name, c.name AS cohort,
                   (SELECT COUNT(*) FROM milestones m WHERE m.project_id = p.id
                    AND m.done_on IS NULL AND m.due_on < :today) AS late_count,
                   (SELECT MIN(m.due_on) FROM milestones m WHERE m.project_id = p.id
                    AND m.done_on IS NULL AND m.due_on < :today) AS oldest_due
            {FROM} WHERE {w} AND {DELAYED} ORDER BY oldest_due LIMIT {int(limit)}""", params).fetchall()


def list_projects(db, f, limit=200):
    w, params = where(f)
    return db.execute(
        f"""SELECT p.id, p.title, p.owner_name, p.owner_gender, d.name AS domain, c.name AS cohort,
                   p.status, p.submitted_on, p.progress_pct,
                   COALESCE((SELECT SUM(amount_fcfa) FROM fundings f WHERE f.project_id=p.id
                             AND f.status IN ('accorde','verse')),0) AS funding,
                   {DELAYED} AS delayed
            {FROM} WHERE {w} ORDER BY p.submitted_on DESC, p.id DESC LIMIT {int(limit)}""", params).fetchall()


def fmt(value, unit):
    if value is None:
        return "n.d."
    if unit == "pct":
        return f"{value:.1f} %".replace(".", ",")
    if unit == "fcfa":
        return f"{int(value):,} FCFA".replace(",", " ")
    return f"{int(value):,}".replace(",", " ")
