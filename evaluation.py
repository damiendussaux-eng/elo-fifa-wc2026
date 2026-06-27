"""
Évaluation des prédictions — métrique principale = Ranked Probability Score (RPS)
sur les 3 issues ORDONNÉES {victoire i, nul, victoire j}.

Réf : Epstein (1969) ; pour le football Constantinou & Fenton (2012),
J. Quantitative Analysis in Sports. Plus le RPS est BAS, mieux c'est.

    RPS = (1/(r−1)) · Σ_{i=1..r−1} ( Σ_{j=1..i} (p_j − e_j) )²

avec r=3, p = probas prédites (ordonnées), e = one-hot de l'issue réalisée.

NB : le « score exact » plafonne bas (~13–15 %) même pour un bon modèle — métrique
SECONDAIRE seulement. C'est le RPS qui décide.
"""
from __future__ import annotations

import math

# Indices d'issue (ordre imposé) : 0 = victoire i, 1 = nul, 2 = victoire j.
WIN_I, DRAW, WIN_J = 0, 1, 2


def outcome_index(goals_i: int, goals_j: int) -> int:
    if goals_i > goals_j:
        return WIN_I
    if goals_i < goals_j:
        return WIN_J
    return DRAW


def rps_single(probs: list[float], outcome: int) -> float:
    """RPS d'une prédiction (probs ordonnées) contre l'issue réalisée (index)."""
    r = len(probs)
    e = [0.0] * r
    e[outcome] = 1.0
    cum_p = cum_e = 0.0
    total = 0.0
    for i in range(r - 1):
        cum_p += probs[i]
        cum_e += e[i]
        total += (cum_p - cum_e) ** 2
    return total / (r - 1)


def rps_mean(list_probs: list[list[float]], outcomes: list[int]) -> float:
    if not list_probs:
        return float("nan")
    return sum(rps_single(p, o) for p, o in zip(list_probs, outcomes)) / len(list_probs)


# --- Métriques SECONDAIRES (informatives, pas critère de sélection) -----------
def pct_correct_outcome(pred_outcomes: list[int], real_outcomes: list[int]) -> float:
    if not pred_outcomes:
        return float("nan")
    ok = sum(1 for p, r in zip(pred_outcomes, real_outcomes) if p == r)
    return ok / len(pred_outcomes)


def pct_exact_score(pred_scores: list[tuple[int, int]],
                    real_scores: list[tuple[int, int]]) -> float:
    if not pred_scores:
        return float("nan")
    ok = sum(1 for p, r in zip(pred_scores, real_scores) if tuple(p) == tuple(r))
    return ok / len(pred_scores)


def log_loss_scores(matrices, real_scores, max_goals: int = 10) -> float:
    """Log-loss moyen sur la distribution COMPLÈTE des scores (secondaire)."""
    if not matrices:
        return float("nan")
    s = 0.0
    for m, (x, y) in zip(matrices, real_scores):
        p = m[x, y] if x <= max_goals and y <= max_goals else 0.0
        s -= math.log(max(float(p), 1e-12))
    return s / len(matrices)


if __name__ == "__main__":
    # Vérifs de la spec §5 (valeurs mathématiquement exactes).
    print("Pronostic PARFAIT (proba 1 sur l'issue réalisée) :")
    print(f"  rps = {rps_single([1, 0, 0], WIN_I):.4f}  (attendu 0)")
    assert rps_single([1, 0, 0], WIN_I) == 0.0

    u = [1/3, 1/3, 1/3]
    print("Pronostic UNIFORME (1/3,1/3,1/3) :")
    print(f"  sur victoire i (issue extrême) rps = {rps_single(u, WIN_I):.4f}  (= 5/18 ≈ 0.2778)")
    print(f"  sur nul       (issue médiane) rps = {rps_single(u, DRAW):.4f}  (= 1/9 ≈ 0.1111)")
    assert abs(rps_single(u, WIN_I) - 5/18) < 1e-9
    assert abs(rps_single(u, DRAW) - 1/9) < 1e-9
    print("\nNB : la spec annonçait ≈0.1667 pour l'uniforme sur 'victoire i' ; la valeur")
    print("    correcte du RPS standard est 5/18 ≈ 0.2778 (0.1667 ne correspond à aucune")
    print("    issue d'un pronostic uniforme — voir commentaire).")
    print("\nOK.")
