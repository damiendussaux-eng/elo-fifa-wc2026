"""
Harnais de comparaison MÉTHODE A vs MÉTHODE B, en WALK-FORWARD strict (§4, §6).

Un seul rejeu chronologique de tout l'historique. Pour chaque match de poule WC2026
(échantillon), on prédit AVANT de connaître le résultat, avec uniquement le passé :
  - Elo réinjecté (jusqu'à m−1), Elo d'avant-tournoi (snapshot),
  - résidus de forme xG agrégés sur les matchs WC antérieurs de chaque équipe.
ρ (Dixon-Coles) est estimé par MLE sur les Coupes du Monde PASSÉES (< 2026) — donc
sans fuite. On évalue chaque configuration au RPS :

  cfg0  A, Elo d'AVANT-TOURNOI (référence §6.0)
  cfg1  A, Elo RÉINJECTÉ            (+ réinjection)         == méthode A telle qu'utilisée
  cfg2  cfg1 + Dixon-Coles          (+ DC)
  cfg3  cfg2 + résidus de forme xG  (+ résidus)             == méthode B complète

On garde une composante seulement si elle BAISSE le RPS moyen.

Usage : python compare.py
"""
from __future__ import annotations

from collections import defaultdict

import config  # noqa: F401  (UTF-8 + .env)
import evaluation
import goals_model
import goals_model_v2 as v2
from elo import win_expectancy
from goals_model_v2 import TeamForm, V2Config
from ingestion import load_history, xg_source
from ingestion.source_groups import GROUP_END, GROUP_START, _group_of
from ratings_engine import k_factor, update_match

CLIP = goals_model.DEFAULT_CLIP


def _clip(x: float) -> float:
    return min(max(x, CLIP[0]), CLIP[1])


def _aggregate(resids: list[tuple[float, float]]) -> TeamForm:
    if not resids:
        return TeamForm()
    offs = [o for o, _ in resids]
    defs = [d for _, d in resids]
    return TeamForm(sum(offs) / len(offs), sum(defs) / len(defs), len(resids))


def run() -> dict:
    df = load_history.load().sort_values("date", kind="stable")
    xg_src = xg_source.get_source("auto")

    ratings: dict[str, float] = defaultdict(lambda: 1300.0)
    pre_tournament: dict[str, float] | None = None
    rho_samples: list[tuple[float, float, int, int]] = []
    team_resid: dict[str, list[tuple[float, float]]] = defaultdict(list)
    rho: float | None = None
    n_fallback = 0
    records: list[dict] = []

    for row in df.itertuples(index=False):
        h, a = row.home_team, row.away_team
        rh, ra = ratings[h], ratings[a]
        tour = (row.tournament or "")
        is_wc_finals = tour.lower() == "fifa world cup"
        in_group_window = GROUP_START <= row.date <= GROUP_END
        is_wc2026_group = (is_wc_finals and in_group_window
                           and _group_of(h) is not None and _group_of(h) == _group_of(a))

        # Snapshot Elo d'avant-tournoi + estimation de ρ sur le passé, au 1er match WC2026.
        if pre_tournament is None and is_wc_finals and row.date >= GROUP_START:
            pre_tournament = dict(ratings)
            rho = v2.estimate_rho(rho_samples)

        # Échantillon d'entraînement de ρ : Coupes du Monde PASSÉES (< 2026).
        if is_wc_finals and row.date.year < 2026:
            w = win_expectancy(rh, ra, 0.0)
            rho_samples.append((_clip(goals_model.lambda_neutral(w)),
                                _clip(goals_model.lambda_neutral(1 - w)),
                                int(row.home_score), int(row.away_score)))

        if is_wc2026_group:
            r = rho if rho is not None else -0.05
            fi, fj = _aggregate(team_resid[h]), _aggregate(team_resid[a])
            epi = pre_tournament.get(h, 1300.0) if pre_tournament else 1300.0
            epj = pre_tournament.get(a, 1300.0) if pre_tournament else 1300.0

            preds = {
                "cfg0": v2.predict_v2(epi, epj, fi, fj, V2Config(
                    use_elo_reinjection=False, use_form_residuals=False,
                    use_dixon_coles=False)),
                "cfg1": v2.predict_v2(rh, ra, fi, fj, V2Config(
                    use_form_residuals=False, use_dixon_coles=False)),
                "cfg2": v2.predict_v2(rh, ra, fi, fj, V2Config(
                    use_form_residuals=False, use_dixon_coles=True, rho=r)),
                "cfg3": v2.predict_v2(rh, ra, fi, fj, V2Config(
                    use_form_residuals=True, use_dixon_coles=True, rho=r)),
            }
            outcome = evaluation.outcome_index(int(row.home_score), int(row.away_score))
            records.append({
                "date": row.date.date(), "home": h, "away": a,
                "real": (int(row.home_score), int(row.away_score)),
                "outcome": outcome, "preds": preds,
                "form_n": (fi.n, fj.n),   # pour le test anti-fuite (walk-forward)
            })

            # Résidus de CE match (après prédiction) -> mémoire de forme (walk-forward).
            w = win_expectancy(rh, ra, 0.0)
            base_i = _clip(goals_model.lambda_neutral(w))
            base_j = _clip(goals_model.lambda_neutral(1 - w))
            xg = xg_source.get_match_xg(h, a, row.date.strftime("%Y-%m-%d"), xg_src)
            if xg is None:
                xgh, xga = float(row.home_score), float(row.away_score)
                n_fallback += 1
            else:
                xgh, xga = xg
            team_resid[h].append((xgh - base_i, xga - base_j))
            team_resid[a].append((xga - base_j, xgh - base_i))

        # MAJ des ratings avec le VRAI résultat (tous les matchs).
        k = k_factor(tour)
        rh_new, ra_new, _ = update_match(rh, ra, int(row.home_score),
                                         int(row.away_score), k, neutral=bool(row.neutral))
        ratings[h], ratings[a] = rh_new, ra_new

    return {"records": records, "rho": rho, "n_fallback": n_fallback,
            "n_rho_samples": len(rho_samples)}


CFG_LABELS = {
    "cfg0": "A · Elo avant-tournoi (réf.)",
    "cfg1": "A · Elo réinjecté",
    "cfg2": "+ Dixon-Coles",
    "cfg3": "+ résidus xG (= B)",
}


def summarize(res: dict) -> dict:
    records = res["records"]
    out = {}
    for cfg in ("cfg0", "cfg1", "cfg2", "cfg3"):
        probs = [r["preds"][cfg]["probs"] for r in records]
        outs = [r["outcome"] for r in records]
        pred_out = [evaluation.outcome_index(*r["preds"][cfg]["consistent_score"])
                    for r in records]
        pred_sc = [r["preds"][cfg]["consistent_score"] for r in records]
        real_sc = [r["real"] for r in records]
        out[cfg] = {
            "rps": evaluation.rps_mean(probs, outs),
            "pct_outcome": evaluation.pct_correct_outcome(pred_out, outs),
            "pct_exact": evaluation.pct_exact_score(pred_sc, real_sc),
        }
    return out


def main() -> None:
    res = run()
    n = len(res["records"])
    print(f"Échantillon : {n} matchs de poule WC2026 (walk-forward).")
    print(f"ρ (Dixon-Coles) estimé par MLE sur {res['n_rho_samples']} matchs de "
          f"Coupes du Monde < 2026 = {res['rho']:+.4f}")
    print(f"xG indisponible -> repli buts réels sur {res['n_fallback']}/{n} matchs "
          f"(aucun fournisseur xG branché).\n")

    s = summarize(res)
    print(f"{'configuration':32s} {'RPS':>8s} {'ΔRPS':>8s}  {'%V/N/D':>7s} {'%exact':>7s}")
    print("-" * 70)
    ref = s["cfg0"]["rps"]
    prev = None
    for cfg in ("cfg0", "cfg1", "cfg2", "cfg3"):
        m = s[cfg]
        d = "" if prev is None else f"{m['rps'] - prev:+.4f}"
        print(f"{CFG_LABELS[cfg]:32s} {m['rps']:8.4f} {d:>8s}  "
              f"{m['pct_outcome']*100:6.1f}% {m['pct_exact']*100:6.1f}%")
        prev = m["rps"]
    print("-" * 70)
    print(f"RPS plus BAS = meilleur. Méthode A (réinjectée) = cfg1 ; méthode B = cfg3.")
    da = s["cfg3"]["rps"] - s["cfg1"]["rps"]
    verdict = ("B AMÉLIORE A" if da < 0 else
               "B N'AMÉLIORE PAS A (garder A, plus simple)")
    print(f"ΔRPS(B − A) = {da:+.4f}  ->  {verdict}")
    print("\nDécision (§6) : garder une composante seulement si elle baisse le RPS.")
    print("Rappel : échantillon d'une seule Coupe du Monde -> écarts bruités (§7).")


if __name__ == "__main__":
    main()
