# Goal v2 (méthode B) vs méthode A — comparaison par RPS

Reproductible : `uv run python compare.py`
(Tests : `test_eval.py`, `test_goals_v2.py`.)

Deux couches « buts » tournent EN PARALLÈLE. `goals_model.py` (méthode A) n'est PAS
modifié : c'est le témoin.

- **Méthode A** : λ = polynôme de Csató sur la win expectancy Elo, deux Poisson
  indépendantes.
- **Méthode B** (`goals_model_v2.py`) : A + (a) Elo réinjecté du tournoi (walk-forward,
  K=60) + (c) résidus de forme offensifs/défensifs en xG, corrigés de l'adversaire et
  shrinkés `n/(n+k)` + (d) correction Dixon-Coles (ρ par MLE). Chaque composante est
  activable par flag pour mesurer son apport isolément.

## Garde-fous respectés

1. **Walk-forward, zéro fuite** — un seul rejeu chronologique ; la prédiction du match
   m n'utilise que les matchs antérieurs (Elo ET résidus). Vérifié par un test
   anti-fuite explicite (`test_goals_v2.py` TEST 5 : `form_n == nb de matchs antérieurs`).
2. **Double comptage mesuré** — réinjecter les résultats dans l'Elo ET ajouter des
   résidus captent tous deux la forme : on mesure chaque composante au lieu de présumer.
3. **Un seul fournisseur d'xG** — `ingestion/xg_source.py`, interface stable
   `get_match_xg`. Aucun fournisseur branché pour l'instant (FBref/StatsBomb : CGU +
   dispo à valider, et résultats WC2026 issus d'un dataset) → **repli sur buts réels**,
   marqué.

## ρ (Dixon-Coles)

Estimé par **maximum de vraisemblance sur 964 matchs de Coupes du Monde < 2026**
(sans fuite) : **ρ ≈ −0.0055**. Petit et légèrement négatif, conforme à Dixon & Coles
(1997) : ρ<0 augmente légèrement les nuls 0-0/1-1. (Signes vérifiés en test.)

## Résultats — RPS en walk-forward (54 matchs de poule WC2026)

| Configuration | RPS | ΔRPS | %V/N/D | %score exact |
|---|---|---|---|---|
| (0) A · Elo avant-tournoi | 0.1838 | — | 61.1 % | 13.0 % |
| (1) A · Elo réinjecté | **0.1817** | −0.0022 | 61.1 % | 13.0 % |
| (2) + Dixon-Coles | 0.1818 | +0.0002 | 61.1 % | 13.0 % |
| (3) + résidus xG (= B) | 0.1821 | +0.0003 | 59.3 % | 14.8 % |

**ΔRPS(B − A) = +0.0005 → la méthode B n'améliore PAS la méthode A.**

## Lecture (protocole §6, ordre imposé)

- **Réinjecter l'Elo** du tournoi aide un peu (−0.0022) : c'est la seule composante
  utile, et elle est **déjà dans la méthode A telle qu'utilisée par l'appli** (Elo
  walk-forward).
- **Dixon-Coles** : apport nul ici (+0.0002). ρ est minuscule sur cet échantillon ;
  la correction ne change quasi rien.
- **Résidus xG** : aucun gain (+0.0003), et même légère dégradation. C'est le
  **double comptage** anticipé : une fois les résultats dans l'Elo, les résidus de
  forme n'ajoutent presque rien (et ici, sur repli buts réels, ils ajoutent du bruit).

**Décision** : conserver la **méthode A**. La méthode B reste disponible (flags) pour
ré-évaluation si un vrai flux xG est branché et/ou sur un échantillon plus grand.

## Limites (§7)

- Échantillon d'**une seule** Coupe du Monde (54 matchs de poule) → écarts de RPS
  **bruités** ; idéalement backtester B sur des Coupes du Monde passées (StatsBomb).
- xG actuellement en **repli buts réels** (pas de vrai xG) → les résidus sont plus
  bruités que ne le seraient de vrais xG. Brancher FBref/StatsBomb pourrait changer (3).
- `%score exact` plafonne (~13-15 %) : métrique secondaire, jamais critère de décision.
- Tirs au but ≈ pile-ou-face pour `P(se qualifier)` : approximation.
