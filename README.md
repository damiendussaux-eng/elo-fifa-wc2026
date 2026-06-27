# elo_fifa_wc2026 — Bracket WC2026 (Elo + Monte-Carlo)

**Arbre du tableau final** (style Google) de la Coupe du Monde FIFA 2026 : 31
cases-matchs sur 5 colonnes (Seizièmes 16 → Huitièmes 8 → Quarts 4 → Demies 2 →
Finale 1). Chaque case = un match avec sa **date**, ses **deux équipes** (drapeau,
nom) et la **probabilité Elo de gagner ce match**. Aucune cote de bookmaker,
aucun LLM dans le calcul : tout est déterministe et reproductible.

- **Mesure de force** : ratings Elo recalculés *from scratch* (réplique
  eloratings.net) en rejouant tout l'historique des matchs internationaux.
- **Proba par match** : `elo.win_expectancy` entre les deux équipes d'une case.
- **Arbre vivant** : les qualifiés confirmés sont déjà placés ; « à déterminer »
  ailleurs. Dès qu'un résultat est enregistré, le vainqueur avance dans la case
  suivante (déduit, aucune ressaisie).
- **Garde-fous** affichés en permanence dans l'UI (l'Elo est un indicateur, pas
  une vérité).

## Architecture (3 couches)

```
[Ingestion]  scripts -> SQLite : ratings Elo + affiches/dates + résultats
[Moteur]     elo.py + ratings_engine.py + bracket_sim.py  (DÉJÀ FAIT, testé)
[UI]         app/streamlit_app.py : lit SQLite, construit l'arbre, affiche
```

> **Stockage = SQLite** (fichier `data/wc2026.sqlite`, module `sqlite3` de la stdlib,
> aucun serveur) — compatible **Streamlit Community Cloud** (gratuit). La base est
> reconstruite à chaque lancement à partir du dataset + ESPN, donc rien à persister.

| Couche | Fichiers |
|---|---|
| Moteur | `elo.py`, `ratings_engine.py`, `bracket_sim.py`, `goals_model.py` (couche buts) |
| Tests moteur | `test_engine.py`, `test_ratings.py`, `test_goals.py` |
| Base (SQLite) | `db/schema.sql`, `db/connection.py`, `db/migrate.py` |
| Ingestion | `ingestion/load_history.py`, `load_ratings.py`, `validate_ratings.py`, `source_fixtures.py`, `source_results.py`, `teams_ref.py` |
| Glue + UI | `app/glue.py` (arbre), `app/streamlit_app.py` |
| Calibration | `backtest.py` |
| Docs | `docs/VALIDATION_RATINGS.md`, `docs/CALIBRATION.md` |

> `bracket_sim.py` (Monte-Carlo du tableau) reste disponible et testé, mais l'UI
> « arbre » affiche des probas **par match** (`win_expectancy`), pas des probas
> d'atteindre un tour. Le moteur MC est prêt si l'on veut rajouter `P(titre)`.

## Prérequis

- Python 3.12+ et [uv](https://docs.astral.sh/uv/)
- Accès réseau (téléchargement du dataset martj42 + API ESPN). Aucun serveur de
  base de données : SQLite est intégré à Python.
- Windows : les scripts forcent la sortie UTF-8 (cf. `config.py`). Hors scripts,
  exporter `PYTHONIOENCODING=utf-8` si besoin.

## Mise en route (local)

```bash
uv sync                                       # environnement + dépendances
uv run streamlit run app/streamlit_app.py     # lance l'app
```

C'est tout : au lancement, l'app **reconstruit tout automatiquement** (bootstrap) —
téléchargement du dataset, complétion par ESPN, calcul de l'Elo, schéma SQLite,
ingestion des affiches/poules, placement des 1ers/2es de groupe. Rien à préparer.

Les étapes d'ingestion restent lançables individuellement (debug / CLI) :

```bash
uv run python -m db.migrate                  # schéma SQLite (data/wc2026.sqlite)
uv run python -m ingestion.load_ratings      # historique -> ratings -> base
uv run python -m ingestion.live_results      # complète via ESPN (concordance)
uv run python -m ingestion.source_fixtures   # affiches + dates officielles
uv run python -m ingestion.source_groups     # poules + matchs + prédictions figées
uv run python -m ingestion.validate_ratings  # valider vs eloratings.net
uv run python backtest.py                    # calibration (à lire avant de publier)
```

## Déploiement sur Streamlit Community Cloud (gratuit)

1. Pousser le dépôt sur GitHub (le `requirements.txt` à la racine suffit ; pas de
   `uv`, pas de Docker, pas de base externe).
2. Sur [share.streamlit.io](https://share.streamlit.io), « New app » -> choisir le
   repo, branche, et **Main file path = `app/streamlit_app.py`**.
3. Déployer. Au premier accès, le bootstrap télécharge les données et construit la
   base SQLite dans le système de fichiers (éphémère) du conteneur — reconstruite à
   chaque redémarrage. Aucune configuration ni secret requis.

Le `pyproject.toml`/`uv` servent au dev local ; Streamlit Cloud installe via
`requirements.txt`.

### Mise à jour au fil des matchs

Enregistrer un résultat dans `results` (round_idx, match_idx, vainqueur) fait
avancer automatiquement le vainqueur dans la case suivante de l'arbre :

```bash
# voie simple : RESULTS_SOURCE=csv + data/results_knockout.csv
#   round_idx,match_idx,winner_team,played_at
uv run python -m ingestion.source_results
```

Compléter les affiches encore inconnues : éditer `ingestion/source_fixtures.py`
(remplacer un libellé « Vainqueur F » / « 2e H » par l'équipe réelle) puis
relancer `python -m ingestion.source_fixtures`.

## Tests (non-régression du moteur)

```bash
PYTHONIOENCODING=utf-8 uv run python test_ratings.py
PYTHONIOENCODING=utf-8 uv run python test_engine.py
```

## Données & sources (vérifiées)

- **Historique des matchs** : dataset Mart Jürisoo (miroir GitHub
  `martj42/international_results`), colonnes `date, home_team, away_team,
  home_score, away_score, tournament, neutral`. Couvre jusqu'aux matchs récents.
- **Référence de validation** : `eloratings.net/World.tsv` + `en.teams.tsv`.
  Écart médian observé ≈ **−121** (offset systématique, ordre conservé) — voir
  `docs/VALIDATION_RATINGS.md`.
- **Affiches, dates et arbre** : calendrier officiel FIFA WC2026 (matchs 73→104,
  dates, lieux) + qualifiés confirmés — voir `ingestion/source_fixtures.py`.
- **Phases de groupes** : composition officielle des 12 poules (tirage 05/12/2025)
  dans `ingestion/source_groups.py` ; classements (Pts, DB, forme) calculés depuis
  les matchs de poule du dataset par `app/glue.py:group_standings`.
- **Résultats live** : adaptateur isolé `ingestion/source_results.py`
  (`RESULTS_SOURCE` = `none` | `csv` | `football_data`). football-data.org reste
  à VÉRIFIER pour la WC2026 (couverture, libellés de stage).

## Notes méthodologiques

- CRS des probabilités = code déterministe ; le LLM ne sert (éventuellement) qu'à
  l'ingestion sale (parsing/résolution de noms).
- **Couche buts** (`goals_model.py`) : λ (buts attendus) = polynôme de degré 4 de
  l'espérance de gain Elo, coefficients exacts de Csató &amp; Gyimesi (2025),
  arXiv:2502.08565v3 §3.2 (repris de Football rankings 2020). Deux lois de Poisson
  **indépendantes** → distribution des scores, score le plus probable, et
  `P(se qualifier) = P(victoire) + 0.5·P(nul)`. C'est ce que l'arbre affiche
  (score jaune + % de qualification). `bracket_sim.simulate(outcome_model="goals")`
  tire les buts par Poisson pour le Monte-Carlo.
  - Limites assumées (affichées dans l'UI) : modèle de buts **étendu aux
    knockouts** (au-delà de l'usage des auteurs, réservé aux groupes) ; Poisson
    indépendantes (sous-estime les nuls serrés ; **pas de Dixon-Coles**, par
    fidélité) ; **λ borné [0.05, 6]** car la régression explose hors [~0.07, ~0.93]
    et est peu fiable pour les outsiders ; tirs au but ≈ pile-ou-face.
- Matchs supposés en terrain neutre par défaut (curseur « avantage hôte » dans
  l'UI : +Elo pour une nation hôte ★ face à une non-hôte).
