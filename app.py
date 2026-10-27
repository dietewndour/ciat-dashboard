"""Tableau de bord décisionnel du CIAT - application Flask."""
import os
import re
import secrets
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

import analytics as an
import assistant
import db as database
import exports

ROLES_WRITE = ("admin", "coordinateur")
MAX_ATTEMPTS, WINDOW = 5, 300  # 5 échecs de connexion par IP et par 5 minutes
_attempts = {}


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(exist_ok=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "ciat.db")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)
    if os.environ.get("USE_REAL_TODAY") == "1":
        an.USE_REAL_TODAY = True
    if not os.path.exists(app.config["DATABASE"]):
        import seed
        seed.build(app.config["DATABASE"])
    app.teardown_appcontext(database.close_db)

    # ---------- Sécurité ----------
    @app.before_request
    def load_user_and_csrf():
        g.user = None
        uid = session.get("uid")
        if uid:
            g.user = database.get_db().execute(
                "SELECT id,username,full_name,role FROM users WHERE id=?", (uid,)).fetchone()
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method == "POST":
            sent = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
            if not sent or not secrets.compare_digest(sent, session["csrf"]):
                abort(400, "Jeton CSRF invalide. Rechargez la page.")

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'")
        return resp

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.user is None:
                return redirect(url_for("login", next=request.path))
            return fn(*a, **kw)
        return wrapper

    def role_required(*roles):
        def deco(fn):
            @wraps(fn)
            @login_required
            def wrapper(*a, **kw):
                if g.user["role"] not in roles:
                    abort(403)
                return fn(*a, **kw)
            return wrapper
        return deco

    app.jinja_env.globals.update(csrf=lambda: session.get("csrf", ""), STATUS=an.STATUS_LABELS,
                                 fmt=an.fmt, can_write=lambda: g.user and g.user["role"] in ROLES_WRITE)

    # ---------- Authentification ----------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            ip = request.remote_addr or "?"
            now = time.time()
            recent = [t for t in _attempts.get(ip, []) if now - t < WINDOW]
            _attempts[ip] = recent
            if len(recent) >= MAX_ATTEMPTS:
                flash("Trop de tentatives. Réessayez dans quelques minutes.", "error")
                return render_template("login.html"), 429
            u = database.get_db().execute("SELECT * FROM users WHERE username=?",
                                          (request.form.get("username", "").strip(),)).fetchone()
            if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
                _attempts.pop(ip, None)
                csrf = session.get("csrf")
                session.clear()
                session["uid"], session["csrf"] = u["id"], csrf
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("dashboard"))
            _attempts.setdefault(ip, []).append(now)
            flash("Identifiant ou mot de passe incorrect.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ---------- Tableau de bord ----------
    def options():
        db = database.get_db()
        return {"cohorts": db.execute("SELECT id,name FROM cohorts ORDER BY id").fetchall(),
                "domains": db.execute("SELECT id,name FROM domains ORDER BY id").fetchall()}

    @app.route("/")
    @login_required
    def dashboard():
        db = database.get_db()
        f = an.clean_filters(request.args)
        charts = {
            "domain": an.aggregate(db, f, "projects", "domain"),
            "gender": an.aggregate(db, f, "projects", "gender"),
            "status": an.aggregate(db, f, "projects", "status"),
            "monthly": [list(r) for r in an.monthly_ideas(db, f)],
            "cohorts": an.cohort_comparison(db, f),
            "funding": an.aggregate(db, f, "funding", "cohort"),
        }
        domain_ids = {r["name"]: r["id"] for r in options()["domains"]}
        return render_template("dashboard.html", f=f, kpis=an.kpis(db, f), late=an.delayed_projects(db, f),
                               charts=charts, domain_ids=domain_ids, **options(),
                               qs=request.query_string.decode())

    # ---------- Projets ----------
    @app.route("/projects")
    @login_required
    def projects():
        f = an.clean_filters(request.args)
        return render_template("projects.html", rows=an.list_projects(database.get_db(), f), f=f, **options())

    @app.route("/projects/<int:pid>")
    @login_required
    def project(pid):
        db = database.get_db()
        p = db.execute("""SELECT p.*, d.name AS domain, c.name AS cohort FROM projects p
                          JOIN domains d ON d.id=p.domain_id JOIN cohorts c ON c.id=p.cohort_id
                          WHERE p.id=?""", (pid,)).fetchone() or abort(404)
        return render_template(
            "project.html", p=p, today=an.today().isoformat(),
            ms=db.execute("SELECT * FROM milestones WHERE project_id=? ORDER BY due_on", (pid,)).fetchall(),
            fu=db.execute("SELECT * FROM fundings WHERE project_id=?", (pid,)).fetchall(),
            pa=db.execute("SELECT * FROM partnerships WHERE project_id=?", (pid,)).fetchall())

    def parse_project(form):
        errors, v = [], {}
        v["title"] = form.get("title", "").strip()
        v["owner_name"] = form.get("owner_name", "").strip()
        v["owner_gender"] = form.get("owner_gender", "")
        v["status"] = form.get("status", "")
        v["description"] = form.get("description", "").strip()[:1000]
        if not 3 <= len(v["title"]) <= 120: errors.append("Le titre doit faire entre 3 et 120 caractères.")
        if not 3 <= len(v["owner_name"]) <= 80: errors.append("Le nom du porteur doit faire entre 3 et 80 caractères.")
        if v["owner_gender"] not in an.GENDER_LABELS: errors.append("Genre invalide.")
        if v["status"] not in an.STATUS_LABELS: errors.append("Statut invalide.")
        db = database.get_db()
        for key, table in (("domain_id", "domains"), ("cohort_id", "cohorts")):
            raw = form.get(key, "")
            if raw.isdigit() and db.execute(f"SELECT 1 FROM {table} WHERE id=?", (int(raw),)).fetchone():
                v[key] = int(raw)
            else:
                errors.append(f"Champ invalide : {key}.")
        for key, required in (("submitted_on", True), ("selected_on", False), ("prototype_on", False)):
            raw = form.get(key, "").strip()
            if not raw and not required:
                v[key] = None
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                try:
                    date.fromisoformat(raw); v[key] = raw
                except ValueError:
                    errors.append(f"Date invalide : {key}.")
            else:
                errors.append(f"Date requise ou invalide : {key}.")
        raw = form.get("progress_pct", "")
        if raw.isdigit() and 0 <= int(raw) <= 100:
            v["progress_pct"] = int(raw)
        else:
            errors.append("La progression doit être un entier entre 0 et 100.")
        if v.get("status") in ("selectionne", "incube", "prototype", "termine") and not v.get("selected_on"):
            errors.append("Un projet sélectionné doit avoir une date de sélection.")
        if v.get("status") in ("prototype", "termine") and not v.get("prototype_on"):
            errors.append("Un projet au stade prototype doit avoir une date de prototype.")
        return v, errors

    def save_project(pid=None):
        v, errors = parse_project(request.form)
        if errors:
            for e in errors: flash(e, "error")
            return None, v
        db = database.get_db()
        cols = ["title", "owner_name", "owner_gender", "domain_id", "cohort_id", "status", "submitted_on",
                "selected_on", "prototype_on", "progress_pct", "description"]
        if pid is None:
            cur = db.execute(f"INSERT INTO projects({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                             [v[c] for c in cols])
            pid = cur.lastrowid
        else:
            db.execute(f"UPDATE projects SET {','.join(c + '=?' for c in cols)} WHERE id=?",
                       [v[c] for c in cols] + [pid])
        db.commit()
        return pid, v

    @app.route("/projects/new", methods=["GET", "POST"])
    @role_required(*ROLES_WRITE)
    def project_new():
        v = {"submitted_on": an.today().isoformat(), "progress_pct": 0, "status": "idee", "owner_gender": "F"}
        if request.method == "POST":
            pid, v = save_project()
            if pid:
                flash("Projet enregistré.", "ok")
                return redirect(url_for("project", pid=pid))
        return render_template("project_form.html", p=v, new=True, **options())

    @app.route("/projects/<int:pid>/edit", methods=["GET", "POST"])
    @role_required(*ROLES_WRITE)
    def project_edit(pid):
        db = database.get_db()
        p = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone() or abort(404)
        v = dict(p)
        if request.method == "POST":
            ok, v = save_project(pid)
            if ok:
                flash("Projet mis à jour.", "ok")
                return redirect(url_for("project", pid=pid))
        return render_template("project_form.html", p=v, new=False, pid=pid, **options())

    @app.post("/projects/<int:pid>/delete")
    @role_required("admin")
    def project_delete(pid):
        db = database.get_db()
        db.execute("DELETE FROM projects WHERE id=?", (pid,))
        db.commit()
        flash("Projet supprimé.", "ok")
        return redirect(url_for("projects"))

    @app.post("/milestones/<int:mid>/toggle")
    @role_required(*ROLES_WRITE)
    def milestone_toggle(mid):
        db = database.get_db()
        m = db.execute("SELECT * FROM milestones WHERE id=?", (mid,)).fetchone() or abort(404)
        new = None if m["done_on"] else an.today().isoformat()
        db.execute("UPDATE milestones SET done_on=? WHERE id=?", (new, mid))
        db.commit()
        return redirect(url_for("project", pid=m["project_id"]))

    # ---------- Assistant ----------
    @app.route("/assistant")
    @login_required
    def assistant_page():
        return render_template("assistant.html", ai_on=bool(os.environ.get("ANTHROPIC_API_KEY")))

    @app.post("/api/assistant")
    @login_required
    def assistant_api():
        data = request.get_json(silent=True) or {}
        db = database.get_db()
        res = assistant.answer(data.get("question", ""), db)
        db.execute("INSERT INTO query_log(user_id,question,mode) VALUES (?,?,?)",
                   (g.user["id"], str(data.get("question", ""))[:500], res.get("mode", "aucun")))
        db.commit()
        return jsonify(res)

    @app.route("/admin/log")
    @role_required("admin")
    def admin_log():
        rows = database.get_db().execute(
            """SELECT q.created_at, u.username, q.mode, q.question FROM query_log q
               LEFT JOIN users u ON u.id=q.user_id ORDER BY q.id DESC LIMIT 100""").fetchall()
        return render_template("log.html", rows=rows)

    # ---------- Exports ----------
    def stamp():
        return datetime.now().strftime("%Y%m%d")

    @app.route("/export/excel")
    @login_required
    def export_excel():
        data = exports.excel(database.get_db(), an.clean_filters(request.args))
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=ciat_synthese_{stamp()}.xlsx"})

    @app.route("/export/pdf")
    @login_required
    def export_pdf():
        data = exports.pdf(database.get_db(), an.clean_filters(request.args))
        return Response(data, mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=ciat_synthese_{stamp()}.pdf"})

    @app.route("/projects/<int:pid>/fiche.pdf")
    @login_required
    def project_fiche(pid):
        data = exports.project_fiche(database.get_db(), pid) or abort(404)
        return Response(data, mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=fiche_projet_{pid}.pdf"})

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(429)
    def http_error(e):
        return render_template("error.html", e=e), e.code

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", e=e), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
