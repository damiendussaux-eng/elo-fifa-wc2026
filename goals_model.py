"""
Couche « buts » : prédiction du nombre de buts (et de la distribution complète des
scores) à partir de l'espérance de gain Elo.

Approche : λ (buts attendus) = polynôme de degré 4 de l'espérance de gain W,
ajusté par moindres carrés sur ~40 000 matchs internationaux.

Source primaire respectée À LA LETTRE (coefficients NON re-dérivés) :
  Csató & Gyimesi (2025), « Increasing competitiveness by imbalanced groups »,
  arXiv:2502.08565v3, Section 3.2 — reprenant Football rankings (2020).

Deux scores = deux lois de Poisson INDÉPENDANTES (pas de correction Dixon-Coles,
par fidélité au modèle choisi). Voir la doc/§ limites pour les réserves.
"""
from __future__ import annotations

import math

import numpy as np

from elo import win_expectancy

DEFAULT_CLIP = (0.05, 6.0)   # λ borné : le polynôme explose hors [~0.07, ~0.93]


# --------------------------------------------------------------------------- #
# 2a. λ neutre
def lambda_neutral(W: float) -> float:
    """λ d'une équipe (terrain neutre), W = son espérance de gain."""
    if W <= 0.9:
        return (3.90388 * W**4 - 0.58486 * W**3 - 2.98315 * W**2
                + 3.13160 * W + 0.33193)
    d = W - 0.9
    return (308097.45501 * d**4 - 42803.04696 * d**3 + 2116.35304 * d**2
            - 9.61869 * d + 2.86899)


# 2b. λ de la nation hôte à domicile (W = espérance de gain de l'hôte, +100 inclus)
def lambda_host_home(W: float) -> float:
    if W <= 0.9:
        return (-5.42301 * W**4 + 15.49728 * W**3 - 12.6499 * W**2
                + 5.36198 * W + 0.22863)
    d = W - 0.9
    return (231098.16153 * d**4 - 30953.10199 * d**3 + 1347.51495 * d**2
            - 1.63074 * d + 2.54747)


# 2c. λ du visiteur chez l'hôte (PARAMÉTRÉ par W = W_Hj, l'espérance de gain de l'HÔTE)
def lambda_host_away(W: float) -> float:
    if W < 0.1:
        d = W - 0.1
        return (90173.57949 * d**4 + 10064.38612 * d**3 + 218.6628 * d**2
                - 11.06198 * d + 2.28291)
    return (-1.25010 * W**4 - 1.99984 * W**3 + 6.54946 * W**2
            - 5.83979 * W + 2.80352)


# Version vectorisée du λ neutre (pour le Monte-Carlo)
def lambda_neutral_vec(W: np.ndarray | float) -> np.ndarray:
    W = np.asarray(W, dtype=float)
    low = (3.90388 * W**4 - 0.58486 * W**3 - 2.98315 * W**2
           + 3.13160 * W + 0.33193)
    d = W - 0.9
    high = (308097.45501 * d**4 - 42803.04696 * d**3 + 2116.35304 * d**2
            - 9.61869 * d + 2.86899)
    return np.where(W <= 0.9, low, high)


def _clip(x: float, clip: tuple[float, float] | None) -> float:
    if clip is None:
        return x
    return min(max(x, clip[0]), clip[1])


def lambdas_for_match(
    elo_i: float, elo_j: float,
    i_host_home: bool = False, j_host_home: bool = False,
    clip: tuple[float, float] | None = DEFAULT_CLIP,
) -> tuple[float, float]:
    """
    (λ_i, λ_j) selon la logique de terrain :
      - neutre : λ_i = λ^(n)(W_ij), λ_j = λ^(n)(1 − W_ij).
      - hôte i à domicile : W = W_Hj de l'hôte (+100) ; λ_i = λ^(h)(W),
        λ_j = λ^(a)(W). (λ^(h) ET λ^(a) dépendent de W de l'HÔTE.)
    """
    if i_host_home and j_host_home:
        raise ValueError("Les deux équipes ne peuvent pas être hôtes à domicile.")
    if i_host_home:
        w_host = win_expectancy(elo_i, elo_j, 100.0)
        li, lj = lambda_host_home(w_host), lambda_host_away(w_host)
    elif j_host_home:
        w_host = win_expectancy(elo_j, elo_i, 100.0)
        lj, li = lambda_host_home(w_host), lambda_host_away(w_host)
    else:
        w_ij = win_expectancy(elo_i, elo_j, 0.0)
        li, lj = lambda_neutral(w_ij), lambda_neutral(1.0 - w_ij)
    return _clip(li, clip), _clip(lj, clip)


# --------------------------------------------------------------------------- #
# 3. Distribution des scores (deux Poisson indépendantes)
def _poisson_pmf(lam: float, kmax: int) -> np.ndarray:
    """[P(0), .., P(kmax)] par récurrence (stable, pas d'overflow)."""
    p = np.empty(kmax + 1)
    p[0] = math.exp(-lam)
    for k in range(1, kmax + 1):
        p[k] = p[k - 1] * lam / k
    return p


def scoreline_matrix(lam_i: float, lam_j: float, max_goals: int = 10) -> np.ndarray:
    """M[a, b] = P(i marque a) · P(j marque b)."""
    return np.outer(_poisson_pmf(lam_i, max_goals), _poisson_pmf(lam_j, max_goals))


def outcome_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    """(P(victoire i), P(nul), P(victoire j)) depuis la matrice des scores."""
    win_i = float(np.tril(matrix, -1).sum())   # a > b
    draw = float(np.trace(matrix))             # a == b
    win_j = float(np.triu(matrix, 1).sum())    # a < b
    return win_i, draw, win_j


def most_likely_score(matrix: np.ndarray) -> tuple[int, int]:
    a, b = np.unravel_index(int(np.argmax(matrix)), matrix.shape)
    return int(a), int(b)


def consistent_score(matrix: np.ndarray) -> tuple[int, int]:
    """
    Score le plus probable COHÉRENT avec l'issue la plus probable (victoire i /
    nul / victoire j) : on choisit d'abord l'issue dominante, puis l'argmax du
    score DANS cette issue. Réconcilie le score affiché avec le favori.

    ≠ `most_likely_score` (argmax absolu, souvent 1-1/0-0) : ici on accepte de
    ne plus montrer le score exact le plus probable, en échange d'une cohérence
    score ↔ favori. Match symétrique -> on retombe sur le nul modal.
    """
    win_i, draw, win_j = outcome_probabilities(matrix)
    region = max((("i", win_i), ("d", draw), ("j", win_j)), key=lambda x: x[1])[0]
    # match symétrique (victoires quasi à égalité) -> traiter comme un nul
    if region in ("i", "j") and abs(win_i - win_j) < 1e-9:
        region = "d"
    if region == "d":
        k = int(np.argmax(np.diagonal(matrix)))
        return k, k
    masked = np.tril(matrix, -1) if region == "i" else np.triu(matrix, 1)
    a, b = np.unravel_index(int(np.argmax(masked)), masked.shape)
    return int(a), int(b)


def advance_probability(matrix: np.ndarray) -> float:
    """P(i se qualifie) = P(victoire i) + 0.5 · P(nul) (tirs au but = pile-ou-face)."""
    win_i, draw, _ = outcome_probabilities(matrix)
    return win_i + 0.5 * draw


def predict_match(
    elo_i: float, elo_j: float,
    i_host_home: bool = False, j_host_home: bool = False,
    max_goals: int = 10, clip: tuple[float, float] | None = DEFAULT_CLIP,
) -> dict:
    """Synthèse pour l'affichage d'une affiche."""
    li, lj = lambdas_for_match(elo_i, elo_j, i_host_home, j_host_home, clip)
    m = scoreline_matrix(li, lj, max_goals)
    win_i, draw, win_j = outcome_probabilities(m)
    a, b = most_likely_score(m)
    return {
        "lambda_i": li, "lambda_j": lj,
        "most_likely_score": (a, b),
        "p": float(m[a, b]),            # proba du score le plus probable
        "win_i": win_i, "draw": draw, "win_j": win_j,
        "advance_i": win_i + 0.5 * draw,
    }
