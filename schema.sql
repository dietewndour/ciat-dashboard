-- Schéma de la base du tableau de bord décisionnel du CIAT (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin','coordinateur','lecteur')),
    created_at    TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS domains (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cohorts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    owner_name   TEXT NOT NULL,
    owner_gender TEXT NOT NULL CHECK (owner_gender IN ('F','M')),
    domain_id    INTEGER NOT NULL REFERENCES domains(id),
    cohort_id    INTEGER NOT NULL REFERENCES cohorts(id),
    status       TEXT NOT NULL CHECK (status IN
                 ('idee','selectionne','incube','prototype','termine','abandonne')),
    submitted_on TEXT NOT NULL,
    selected_on  TEXT,
    prototype_on TEXT,
    progress_pct INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    description  TEXT
);

CREATE TABLE IF NOT EXISTS milestones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label      TEXT NOT NULL,
    due_on     TEXT NOT NULL,
    done_on    TEXT
);

CREATE TABLE IF NOT EXISTS partnerships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    partner_name TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('technique','financier','institutionnel','commercial')),
    status       TEXT NOT NULL CHECK (status IN ('en_discussion','signe','termine')),
    signed_on    TEXT
);

CREATE TABLE IF NOT EXISTS fundings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    amount_fcfa INTEGER NOT NULL CHECK (amount_fcfa >= 0),
    status      TEXT NOT NULL CHECK (status IN ('demande','accorde','verse')),
    decided_on  TEXT
);

CREATE TABLE IF NOT EXISTS query_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id),
    question   TEXT NOT NULL,
    mode       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_cohort ON projects(cohort_id);
CREATE INDEX IF NOT EXISTS idx_projects_domain ON projects(domain_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_fundings_project ON fundings(project_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_project ON partnerships(project_id);
