# Calibration / backtest (§9)

Reproductible : `uv run python backtest.py`
Échantillon : **785 matchs** de phases finales (Coupe du Monde, Euro, Copa
América), saisons **≥ 2006**, ratings Elo PRÉ-match recalculés from scratch.

> ⚠️ Ne pas publier de probabilités sans avoir lu cette page.

## A) Calibration « score » — W_e vs résultat réel (nul = 0,5)

**Score de Brier = 0,147** (n=785). Bien calibré sur tout le cœur de
distribution (40–80 %, écarts < 4 pts). Un seul biais net :

| tranche prédite | n | prédit | observé | écart |
|---|---|---|---|---|
| 0.8–0.9 | 117 | 84.7 % | 79.1 % | −5.7 |
| **0.9–1.0** | 37 | **92.8 %** | **82.4 %** | **−10.3** |

→ Les **très gros favoris sont surestimés** quand on compte le nul comme 0,5 :
même une nation dominante concède des nuls (et des « upsets ») plus souvent que
ne le dit l'Elo. C'est exactement le garde-fou affiché dans l'UI.

## B) Calibration « élimination directe » — p ≈ P(se qualifier)

Matchs **décisifs** (non-nuls + nuls tranchés aux tirs au but via `shootouts.csv`),
issue binaire. **Brier = 0,185** (n=639).

| tranche | n | prédit | observé | écart |
|---|---|---|---|---|
| 0.6–0.7 | 100 | 65.0 % | 68.0 % | +3.0 |
| 0.7–0.8 | 98 | 75.2 % | 78.6 % | +3.3 |
| 0.8–0.9 | 91 | 84.7 % | 87.9 % | +3.2 |
| 0.9–1.0 | 29 | 92.7 % | 93.1 % | +0.4 |

## Biais sur les favoris (point de vue du mieux noté)

| tranche | n | prédit | observé | écart |
|---|---|---|---|---|
| 0.6–0.7 | 163 | 65.0 % | 70.6 % | +5.5 |
| 0.7–0.8 | 152 | 75.6 % | 79.6 % | +4.0 |
| 0.8–0.9 | 117 | 84.3 % | 87.2 % | +2.8 |
| 0.9–1.0 | 37 | 92.5 % | 89.2 % | −3.3 |

**Écart moyen prédit−observé sur les favoris marqués (p≥60 %) = −3,7 pts.**

## Lecture honnête (les deux vues divergent — c'est instructif)

- **En termes de SCORE** (nul = 0,5), les **favoris extrêmes sont surestimés**
  (top décile −10 pts). C'est le biais que mentionne le bandeau de l'UI.
- **En termes d'AVANCEMENT binaire** (qui passe réellement le tour), sur ce
  même échantillon, les favoris marqués ne sont **pas** surestimés (plutôt
  légèrement sous-estimés, −3,7 pts) : un favori qui fait nul finit souvent par
  passer (prolongation / tirs au but). Les deux ne se contredisent pas : ils
  mesurent deux choses différentes.

**Implication pour le bracket.** `bracket_sim` utilise `win_expectancy` (vue
SCORE) comme approximation de P(se qualifier). Le biais à surveiller est donc
celui du **haut de distribution** : les % de titre des tout meilleurs favoris
sont probablement un peu **optimistes**. À prendre comme ordre de grandeur, pas
comme vérité — d'où le bandeau de garde-fous non négociable.

## Limites

- Le dataset martj42 **ne libelle pas le tour** (groupe vs élimination directe).
  La vue B mélange donc des matchs de groupe « décisifs » et de vrais matchs à
  élimination directe (seuls les matchs avec tirs au but sont garantis knockout).
  C'est une calibration de la **probabilité de victoire de match**, lue comme
  proxy de P(se qualifier).
- Avantage de terrain : `neutral=False` → +100 (cas des nations hôtes) ; sinon 0.
- Tranches extrêmes (0.0–0.1) : faibles effectifs → bruit, à ignorer.
