# Tableau de bord décisionnel du CIAT (Projet 3)

Application web Flask + SQLite pour suivre les idées reçues, sélections, prototypes, retards,
partenariats et financements du CIAT et de son incubateur (ISEP Amadou Trawaré).
Toutes les données fournies sont **fictives** (générées par `seed.py`, graine 42).

## Installation
```bash
python -m venv .venv && source .venv/bin/activate     # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python -c "from wsgi import app; app.run()"            # http://127.0.0.1:5000
```
La base `instance/ciat.db` est créée et remplie au premier lancement. Pour la régénérer : `python seed.py`.

## Comptes de démonstration
| Identifiant | Mot de passe | Rôle | Droits |
|---|---|---|---|
| admin | Admin#2026 | admin | tout, y compris suppression et journal de l'assistant |
| coordo | Coordo#2026 | coordinateur | consulter, créer, modifier, marquer les jalons |
| lecteur | Lecteur#2026 | lecteur | consulter, exporter, interroger l'assistant |

**À changer avant toute mise en ligne publique** (voir `seed.py`, liste `users`).

## Variables d'environnement
| Variable | Rôle |
|---|---|
| SECRET_KEY | Clé de session. Obligatoire en production (`python -c "import secrets;print(secrets.token_hex(32))"`). |
| COOKIE_SECURE=1 | Cookie de session réservé à HTTPS (à activer en ligne). |
| ANTHROPIC_API_KEY | Active la compréhension libre des questions par IA générative. Sans clé, analyse par mots-clés. |
| ANTHROPIC_MODEL | Modèle utilisé (défaut `claude-haiku-5-5`). |
| DATABASE_PATH | Chemin de la base SQLite. |
| USE_REAL_TODAY=1 | Calcule les retards avec la date du jour. Par défaut, date de référence fixe du 27/10/2026 pour que la démo reste stable. |

## Déploiement (exemple Render, gratuit)
1. Pousser le dossier sur GitHub.
2. Render > New Web Service. Build : `pip install -r requirements.txt`. Start : `gunicorn wsgi:app`.
3. Ajouter `SECRET_KEY`, `COOKIE_SECURE=1`, éventuellement `ANTHROPIC_API_KEY`.
4. Limite connue : le disque gratuit est éphémère, la base fictive est recréée à chaque redémarrage. Pour garder des données réelles, utiliser un disque persistant ou PostgreSQL.

## Tests
`python -m unittest discover -s tests -v` (23 tests : authentification, rôles, CSRF, validation, indicateurs, assistant, exports).

## Organisation du code
- `app.py` routes, authentification, rôles, sécurité. `wsgi.py` point d'entrée.
- `analytics.py` indicateurs et agrégations (requêtes paramétrées, listes blanches).
- `assistant.py` question en langage naturel vers spécification JSON validée, puis calcul.
- `exports.py` Excel et PDF. L'image se télécharge par graphique (navigateur).
- `schema.sql`, `seed.py` base et jeu de données. `docs/` documentation.

## Conception de l'assistant IA
L'IA ne produit jamais de SQL ni de chiffres. Elle traduit la question en `{metric, group_by, filters}`,
le code valide ces valeurs contre des listes blanches et exécute la requête. La réponse est écrite par le code.
Une question hors périmètre reçoit « Je ne sais pas ».

## Limites connues
- Couleurs et logo provisoires : à remplacer par la charte officielle de l'ISEP (variables en tête de `static/style.css`).
- Pas de gestion des utilisateurs dans l'interface (comptes créés dans `seed.py`).
- Pas de saisie des jalons, financements et partenariats dans l'interface (lecture, et bouton « terminé » sur les jalons).
- Limitation de tentatives de connexion en mémoire, valable pour un seul processus.
- Le mode IA n'a pas été testé avec une vraie clé dans cet environnement : seul le mode mots-clés est couvert par les tests.
