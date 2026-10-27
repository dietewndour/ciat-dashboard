"""Tests des fonctions essentielles. Lancer : python -m unittest discover -s tests -v"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("ANTHROPIC_API_KEY", None)

import app as appmod  # noqa: E402
import analytics as an  # noqa: E402
import assistant  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = appmod.create_app({"DATABASE": os.path.join(self.tmp.name, "t.db"), "TESTING": True})
        self.c = self.app.test_client()
        appmod._attempts.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def csrf(self):
        self.c.get("/login")
        with self.c.session_transaction() as s:
            return s["csrf"]

    def login(self, user="admin", pw="Admin#2026"):
        return self.c.post("/login", data={"username": user, "password": pw, "csrf": self.csrf()})

    def with_db(self):
        import sqlite3
        con = sqlite3.connect(self.app.config["DATABASE"]); con.row_factory = sqlite3.Row
        return con


class TestAuth(Base):
    def test_redirect_when_anonymous(self):
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_login_ok_and_bad(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_bad_password(self):
        r = self.login(pw="mauvais")
        self.assertEqual(r.status_code, 200)
        self.assertIn("incorrect", r.get_data(as_text=True))

    def test_throttle(self):
        for _ in range(5):
            self.login(pw="x")
        self.assertEqual(self.login().status_code, 429)

    def test_csrf_required(self):
        self.assertEqual(self.c.post("/login", data={"username": "admin", "password": "x"}).status_code, 400)

    def test_open_redirect_blocked(self):
        r = self.c.post("/login?next=//evil.com", data={"username": "admin", "password": "Admin#2026", "csrf": self.csrf()})
        self.assertNotIn("evil.com", r.headers["Location"])


class TestRoles(Base):
    def test_reader_cannot_write(self):
        self.login("lecteur", "Lecteur#2026")
        self.assertEqual(self.c.get("/projects/new").status_code, 403)
        self.assertEqual(self.c.get("/admin/log").status_code, 403)

    def test_coordo_cannot_delete(self):
        self.login("coordo", "Coordo#2026")
        self.assertEqual(self.c.get("/projects/new").status_code, 200)
        tok = self.csrf()
        self.assertEqual(self.c.post("/projects/1/delete", data={"csrf": tok}).status_code, 403)

    def test_admin_can_delete(self):
        self.login()
        r = self.c.post("/projects/1/delete", data={"csrf": self.csrf()})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/projects/1").status_code, 404)


class TestProjectCrud(Base):
    def form(self, **kw):
        d = dict(title="Projet test", owner_name="Awa Diop", owner_gender="F", domain_id="1", cohort_id="4",
                 status="idee", submitted_on="2026-09-01", selected_on="", prototype_on="", progress_pct="0",
                 description="", csrf=self.csrf())
        d.update(kw); return d

    def test_create_and_validation(self):
        self.login("coordo", "Coordo#2026")
        con = self.with_db(); n = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        self.assertEqual(self.c.post("/projects/new", data=self.form()).status_code, 302)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM projects").fetchone()[0], n + 1)
        bad = self.c.post("/projects/new", data=self.form(progress_pct="150", title="x"))
        self.assertEqual(bad.status_code, 200)  # formulaire réaffiché avec erreurs
        self.assertEqual(con.execute("SELECT COUNT(*) FROM projects").fetchone()[0], n + 1)

    def test_selected_requires_date(self):
        self.login("coordo", "Coordo#2026")
        r = self.c.post("/projects/new", data=self.form(status="incube"))
        self.assertIn("date de sélection", r.get_data(as_text=True))

    def test_xss_escaped(self):
        self.login("coordo", "Coordo#2026")
        r = self.c.post("/projects/new", data=self.form(title="<script>alert(1)</script>"), follow_redirects=True)
        self.assertNotIn("<script>alert(1)</script>", r.get_data(as_text=True))


class TestAnalytics(Base):
    def test_kpis_consistent(self):
        con = self.with_db()
        k = an.kpis(con, {})
        total = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        self.assertEqual(k["projects"]["value"], total)
        self.assertLessEqual(k["selected"]["value"], total)
        self.assertLessEqual(k["prototypes"]["value"], k["selected"]["value"])

    def test_group_sums_equal_total(self):
        con = self.with_db()
        for g in an.GROUPS:
            self.assertEqual(sum(v for _, v in an.aggregate(con, {}, "projects", g)), 96)

    def test_filter_and_injection(self):
        con = self.with_db()
        f = an.clean_filters({"owner": "'; DROP TABLE projects; --", "cohort_id": "1 OR 1=1"})
        self.assertNotIn("cohort_id", f)
        an.kpis(con, f)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 96)

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError):
            an.aggregate(self.with_db(), {}, "projects; DROP", None)


class TestAssistant(Base):
    def test_known_question(self):
        r = assistant.answer("Combien d'idées par domaine ?", self.with_db())
        self.assertTrue(r["ok"]); self.assertEqual(sum(v for _, v in r["rows"]), 96)

    def test_filters_from_text(self):
        r = assistant.answer("Combien de projets portés par des femmes en 2025 ?", self.with_db())
        self.assertIn("Cohorte 2025", r["interpretation"]); self.assertIn("Femmes", r["interpretation"])

    def test_refuses_unknown(self):
        r = assistant.answer("Quel temps fera-t-il demain ?", self.with_db())
        self.assertFalse(r["ok"]); self.assertIn("Je ne sais pas", r["text"])

    def test_validate_rejects_bad_spec(self):
        self.assertIsNone(assistant.validate({"metric": "x"}, self.with_db()))
        self.assertIsNone(assistant.validate({"metric": "projects", "group_by": "p.id; DROP"}, self.with_db()))

    def test_api_logs(self):
        self.login()
        r = self.c.post("/api/assistant", json={"question": "Financements par cohorte"},
                        headers={"X-CSRF-Token": self.csrf()})
        self.assertTrue(r.get_json()["ok"])
        self.assertIn("Financements", self.c.get("/admin/log").get_data(as_text=True))


class TestExports(Base):
    def test_exports(self):
        self.login()
        x = self.c.get("/export/excel?cohort_id=4")
        self.assertEqual(x.status_code, 200); self.assertTrue(x.data.startswith(b"PK"))
        p = self.c.get("/export/pdf"); self.assertTrue(p.data.startswith(b"%PDF"))
        f = self.c.get("/projects/2/fiche.pdf"); self.assertTrue(f.data.startswith(b"%PDF"))

    def test_pages_render(self):
        self.login()
        for url in ("/", "/projects", "/projects/3", "/assistant", "/admin/log", "/?domain_id=2&status=incube"):
            self.assertEqual(self.c.get(url).status_code, 200, url)


if __name__ == "__main__":
    unittest.main()
