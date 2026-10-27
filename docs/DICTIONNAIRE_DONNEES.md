# Dictionnaire des données

Source : jeu **fictif** généré par `seed.py` (graine 42, 96 projets, 4 cohortes, 7 domaines). Aucune donnée réelle du CIAT.

| Table | Champ | Type | Règle |
|---|---|---|---|
| users | username, full_name, password_hash, role | texte | role : admin, coordinateur, lecteur. Mot de passe haché (Werkzeug). |
| domains | name | texte | 7 domaines prioritaires du sujet |
| cohorts | name, start_date, end_date | texte, dates ISO | 2023 à 2026 |
| projects | title, owner_name | texte | 3 à 120 / 3 à 80 caractères |
| projects | owner_gender | F ou M | |
| projects | status | idee, selectionne, incube, prototype, termine, abandonne | |
| projects | submitted_on, selected_on, prototype_on | date ISO | selected_on obligatoire dès « sélectionné » ; prototype_on dès « prototype » |
| projects | progress_pct | entier 0-100 | |
| milestones | label, due_on, done_on | texte, dates | done_on vide = non terminé |
| partnerships | kind, status, signed_on | enum | kind : technique, financier, institutionnel, commercial |
| fundings | source, amount_fcfa, status | texte, entier ≥ 0, enum | status : demande, accorde, verse |
| query_log | user_id, question, mode | | traçabilité des questions à l'assistant |

## Définition des indicateurs
- **Idées reçues** : nombre de projets du périmètre filtré.
- **Sélectionnés** : projets avec `selected_on` renseignée.
- **Taux de sélection** : sélectionnés / idées reçues.
- **Prototypes** : projets avec `prototype_on` renseignée.
- **En retard** : projets ayant au moins un jalon sans `done_on` et dont `due_on` est dépassée (date de référence : 27/10/2026).
- **Progression moyenne** : moyenne de `progress_pct` sur les projets sélectionnés.
- **Financements** : somme des montants au statut « accordé » ou « versé » (les « demandés » sont exclus).
- **Partenariats signés** : nombre de partenariats au statut « signé ».

## Contrôles de qualité
Dates ISO validées, énumérations par contraintes CHECK, clés étrangères actives, montants positifs.
Cohérence testée : la somme des groupes égale le total (tests `test_group_sums_equal_total`).

## Limites
Données synthétiques : les écarts entre cohortes et domaines ne reflètent aucune réalité et ne doivent pas être interprétés comme des résultats.
Les cohortes récentes ont mécaniquement plus de jalons à venir. Le genre est binaire (F/M) par simplification du jeu fictif.
