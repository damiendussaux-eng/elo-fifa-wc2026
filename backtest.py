"""
Calibration / backtest (§9) — à faire AVANT de faire confiance aux %.

Question centrale : « sur les matchs prédits à ~70 %, en gagne-t-on ~70 % ? »
On rejoue l'historique chronologiquement, on capture le rating Elo PRÉ-match des
deux équipes, on calcule la prédiction, puis on la compare au résultat réel sur
un échantillon de grands tournois (Coupes du Monde, Euros, Copa América).

Deux mesures complémentaires :
  A) Calibration « score » (tous les matchs des tournois ciblés) :
     W_e (espérance de gain, nul=0,5) vs résultat réel w∈{0, 0.5, 1}.
     -> courbe de fiabilité + score de Brier généralisé mean((p−w)²).
  B) Calibration « élimination directe » (matchs DÉCISIFS : non-nuls + nuls
     tranchés aux tirs au but) : p ≈ P(se qualifier) vs issue binaire (0/1).
     -> courbe de fiabilité + Brier binaire + table de BIAIS SUR LES FAVORIS
        (dans les tranches p élevées, gagne-t-on au taux prédit ?).

Le biais attendu (cf. garde-fous UI) : en élimination directe, compter le nul
comme 0,5 et les tirs au but proches du hasard tend à SURESTIMER les favoris.
Ce script le quantifie.

Usage : python backtest.py
"""
from __future__ import annotations

from collections import defaultdict

import config  # noqa: F401  (UTF-8 + .env)
from elo import win_expectancy
from ingestion import load_history
from ratings_engine import k_factor, update_match

# Tournois retenus pour l'échantillon de test (phases finales à forte intensité).
TARGET_SUBSTRINGS = ("fifa world cup", "uefa euro", "copa américa", "copa america")
# On exclut les éliminatoires (« qualification ») : on veut les phases finales.
EXCLUDE_SUBSTRINGS = ("qualification",)
MIN_YEAR = 2006  # assez d'historique en amont pour des ratings stables


def _is_target(tournament: str) -> bool:
    t = (tournament or "").lower()
    if any(x in t for x in EXCLUDE_SUBSTRINGS):
        return False
    return any(x in t for x in TARGET_SUBSTRINGS)


def collect_samples() -> list[dict]:
    """Rejoue l'historique, renvoie un échantillon de matchs de tournois ciblés."""
    matches = load_history.load()
    shootouts = load_history.load_shootouts()

    ratings: dict[str, float] = defaultdict(lambda: 1300.0)
    samples: list[dict] = []

    for row in matches.itertuples(index=False):
        home, away = row.home_team, row.away_team
        rh, ra = ratings[home], ratings[away]
        neutral = bool(row.neutral)
        ha = 0.0 if neutral else 100.0

        if _is_target(row.tournament) and row.date.year >= MIN_YEAR:
            p_home = win_expectancy(rh, ra, ha)  # prédiction PRÉ-match
            hs, as_ = int(row.home_score), int(row.away_score)
            if hs > as_:
                w, decisive, home_adv = 1.0, True, 1
            elif hs < as_:
                w, decisive, home_adv = 0.0, True, 0
            else:
                # Nul : tranché aux tirs au but ? (=> match à élimination directe)
                key = (row.date.strftime("%Y-%m-%d"), home, away)
                winner = shootouts.get(key)
                if winner is not None:
                    decisive = True
                    home_adv = 1 if winner == home else 0
                    w = 0.5  # côté Elo, le match reste un nul (W=0,5)
                else:
                    decisive, home_adv, w = False, None, 0.5
            samples.append({
                "date": row.date, "home": home, "away": away,
                "p_home": p_home, "w": w,
                "decisive": decisive, "home_adv": home_adv,
            })

        # Mise à jour des ratings (sur TOUS les matchs, pour rester fidèle).
        k = k_factor(row.tournament)
        rh_new, ra_new, _ = update_match(rh, ra, int(row.home_score),
                                         int(row.away_score), k, neutral=neutral)
        ratings[home], ratings[away] = rh_new, ra_new

    return samples


def reliability(pairs: list[tuple[float, float]], n_bins: int = 10) -> list[dict]:
    """pairs = [(p_prédit, y_observé)]. Renvoie une table par tranche de p."""
    bins = [[] for _ in range(n_bins)]
    for p, y in pairs:
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))
    table = []
    for i, b in enumerate(bins):
        if not b:
            continue
        n = len(b)
        mp = sum(p for p, _ in b) / n
        my = sum(y for _, y in b) / n
        table.append({"bin": f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}",
                      "n": n, "pred": mp, "obs": my})
    return table


def brier(pairs: list[tuple[float, float]]) -> float:
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else float("nan")


def _print_reliability(title: str, pairs: list[tuple[float, float]]) -> None:
    print(f"\n{title}")
    print(f"  Brier = {brier(pairs):.4f}   (n={len(pairs)})")
    print(f"  {'tranche':10s} {'n':>5s} {'prédit':>8s} {'observé':>8s} {'écart':>8s}")
    print("  " + "-" * 43)
    for r in reliability(pairs):
        gap = r["obs"] - r["pred"]
        print(f"  {r['bin']:10s} {r['n']:5d} {r['pred']*100:7.1f}% "
              f"{r['obs']*100:7.1f}% {gap*100:+7.1f}%")


def main() -> None:
    samples = collect_samples()
    print(f"Échantillon : {len(samples)} matchs de phases finales "
          f"(WC/Euro/Copa, ≥ {MIN_YEAR}).")

    # A) Calibration "score" : p_home vs w∈{0,0.5,1} (tous les matchs).
    score_pairs = [(s["p_home"], s["w"]) for s in samples]
    _print_reliability("A) Calibration SCORE — W_e (nul=0,5) vs résultat réel",
                       score_pairs)

    # B) Calibration "élimination directe" : matchs décisifs, issue binaire.
    dec = [s for s in samples if s["decisive"]]
    ko_pairs = [(s["p_home"], float(s["home_adv"])) for s in dec]
    _print_reliability("B) Calibration ÉLIMINATION DIRECTE — p ≈ P(se qualifier) "
                       "vs issue binaire", ko_pairs)

    # Biais favoris : côté du FAVORI (p>=0.5), prédit vs observé.
    fav = []
    for s in dec:
        if s["p_home"] >= 0.5:
            fav.append((s["p_home"], float(s["home_adv"])))
        else:
            fav.append((1 - s["p_home"], 1.0 - float(s["home_adv"])))
    print("\nBIAIS SUR LES FAVORIS (point de vue du mieux noté de chaque match) :")
    table = reliability(fav)
    over = 0.0
    for r in table:
        if r["pred"] >= 0.6:
            over += (r["pred"] - r["obs"]) * r["n"]
    print(f"  {'tranche':10s} {'n':>5s} {'prédit':>8s} {'observé':>8s} {'écart':>8s}")
    print("  " + "-" * 43)
    for r in table:
        gap = r["obs"] - r["pred"]
        flag = "  <- favoris" if r["pred"] >= 0.7 else ""
        print(f"  {r['bin']:10s} {r['n']:5d} {r['pred']*100:7.1f}% "
              f"{r['obs']*100:7.1f}% {gap*100:+7.1f}%{flag}")

    n_fav_strong = sum(r["n"] for r in table if r["pred"] >= 0.6)
    if n_fav_strong:
        print(f"\nConclusion : sur les favoris marqués (p≥60 %), écart moyen "
              f"prédit−observé = {over / n_fav_strong*100:+.1f} pts.")
        print("Un écart POSITIF = favoris SURESTIMÉS (cf. garde-fou tirs au but). "
              "Interpréter avec la taille d'échantillon par tranche.")


if __name__ == "__main__":
    main()
