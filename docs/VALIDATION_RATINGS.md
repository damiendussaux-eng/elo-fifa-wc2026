# Validation des ratings Elo (§6a)

Reproductible : `uv run python -m ingestion.validate_ratings`

## 1. Écart vs eloratings.net — au 2026-06-24

Comparaison de NOS 30 meilleures notes (calcul maison, rejeu de l'historique
martj42) aux valeurs publiées par eloratings.net (`World.tsv` + `en.teams.tsv`),
29 nations appariées.

| Mesure | Valeur |
|---|---|
| Écart **médian** (maison − eloratings) | **−121.2** |
| Écart moyen | −122.9 |
| Écart absolu médian | 121.2 |
| Plage des écarts | −58 à −156 |

**Lecture.** L'écart est NÉGATIF et quasi constant (≈ −120) sur toutes les
nations. C'est un décalage **systématique**, pas du bruit ni une erreur de
formule :

- Les probabilités du bracket dépendent des **différences** de ratings, pas des
  niveaux absolus. Un offset commun de −120 s'annule dans chaque match → impact
  quasi nul sur les `win_expectancy` et donc sur les % affichés.
- L'**ordre** des nations concorde fortement avec eloratings.net (Argentine,
  Espagne, France, Brésil, Angleterre… en tête des deux côtés).

**Origines connues de l'offset** (attendues, cf. en-tête de `ratings_engine.py`) :
1. **Initialisation** différente (eloratings backfill depuis 1872 avec sa propre
   amorce ; ici `init_rating=1300`).
2. **Classification des tournois** légèrement différente (→ K).
3. **Cas limites** (matchs abandonnés, forfaits, drapeaux terrain-neutre par
   match) non répliqués à l'identique.

Conforme à l'attendu de la spec : « même ordre de grandeur, écart faible, PAS
l'égalité à l'unité ».

## 2. Revue de `TOURNAMENT_TO_TIER` vs eloratings.net/about

Les **paliers de K** (`K_BY_TIER`) correspondent au barème publié et stable
d'eloratings.net :

| K | Type de match | Tier interne |
|---|---|---|
| 60 | Phase finale de Coupe du Monde | `world_cup_finals` |
| 50 | Finales continentales + tournois intercontinentaux majeurs (Confederations Cup) | `continental_finals` |
| 40 | Éliminatoires (CM + continentaux) + tournois majeurs | `qualifiers` |
| 30 | Tous les autres tournois | `other_tournament` (= `DEFAULT_TIER`) |
| 20 | Matchs amicaux | `friendly` |

Vérification sur les 30 tournois les plus fréquents du dataset (8 confédérations,
49 459 matchs) : tous tombent dans le bon palier. Points contrôlés :

- **Ordre des clés** correct : `fifa world cup qualification` est testé AVANT
  `fifa world cup` (sous-chaîne) → les éliminatoires ne sont pas classées en
  phase finale. Idem `uefa euro qualification` avant `uefa euro`.
- **Longue traîne** (170 tournois mineurs : CECAFA, Merdeka, Gulf Cup, Island
  Games…) → `DEFAULT_TIER` = 30 = « all other tournaments » d'eloratings. ✔
- **Confederations Cup** → `continental_finals` (50) = « major intercontinental
  tournament ». ✔

### Décisions ouvertes (documentées, non fabriquées)

- **UEFA / CONCACAF Nations League** → actuellement `other_tournament` (K=30).
  eloratings.net pourrait les compter comme « tournoi majeur » (K=40). Page
  `/about` rendue en JS, non vérifiable de façon machine ; choix conservateur
  conservé. Impact marginal (compétitions récentes, peu de matchs vs 49 k).
- **Olympic Games** présents dans le dataset. Le football olympique moderne est
  U-23 (depuis 1992) et n'entre normalement pas dans l'Elo senior d'eloratings ;
  ici classé en `DEFAULT_TIER` (30). À trancher si fidélité fine requise.

Ces deux points n'affectent pas l'ordre du top-30 ni la conclusion du §1.

## 3. Initialisation des nouvelles équipes

`init_rating = 1300` (défaut `compute_ratings`). Vu la longueur de l'historique
(depuis 1872), l'amorce n'influence que marginalement les notes courantes des
nations établies. Valeur à confirmer contre eloratings si fidélité fine requise.
