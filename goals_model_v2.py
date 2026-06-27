"""
Couche « buts » MÉTHODE B (Goal v2) — tourne EN PARALLÈLE de la méthode A
(`goals_model.py`, NON modifiée, témoin de comparaison).

Pipeline (composantes activables par flags, pour mesurer leur apport RPS isolément) :
  (a) Elo RÉINJECTÉ (forme du tournoi) — choisi par l'appelant (walk-forward).
  (b) λ de base = polynôme de Csató (réutilisé de la méthode A) sur la win expectancy.
  (c) Résidus offensifs/défensifs en xG, corrigés de l'adversaire, shrinkés vers 0.
  (d) Correction Dixon-Coles (ρ estimé par MLE) sur les 4 cases de scores faibles.

RÈGLE D'OR : walk-forward, zéro fuite — toutes les entrées (Elo, résidus) ne
dépendent que des matchs antérieurs. Garanti par l'appelant (compare.py).

Réfs : Csató & Gyimesi (2025) ; Dixon & Coles (1997), Applied Statistics 46(2):265-280.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import goals_model  # méthode A (lecture seule)
from elo import win_expectancy

DEFAULT_CLIP = (0.05, 6.0)


@dataclass
class TeamForm:
    """Résidus de forme AGRÉGÉS d'une équipe (sur ses matchs WC antérieurs)."""
    mean_off: float = 0.0   # moyenne (xG marqués − λ attendu) — sur/sous-perf offensive
    mean_def: float = 0.0   # moyenne (xG encaissés − λ attendu) — défense
    n: int = 0              # nombre de matchs agrégés


@dataclass
class V2Config:
    use_elo_reinjection: bool = True   # (géré côté appelant : quel Elo est passé)
    use_form_residuals: bool = True
    use_dixon_coles: bool = True
    shrink_k: float = 4.5              # matchs "fictifs" du shrinkage (à régler par RPS)
    rho: float = -0.05                # Dixon-Coles (estimé par MLE, voir estimate_rho)
    clip: tuple[float, float] = DEFAULT_CLIP
    max_goals: int = 10


# --------------------------------------------------------------------------- #
# (d) Dixon-Coles
def dixon_coles_matrix(lam: float, mu: float, rho: float,
                       max_goals: int = 10) -> np.ndarray:
    """
    Matrice des scores Poisson indépendante puis correction Dixon-Coles des 4
    cases basses, RENORMALISÉE. lam = buts attendus i, mu = buts attendus j.

    τ(0,0)=1−λμρ ; τ(0,1)=1+λρ ; τ(1,0)=1+μρ ; τ(1,1)=1−ρ ; sinon 1.
    (Signes conformes à Dixon & Coles 1997 : ρ<0 augmente les nuls 0-0/1-1.)
    """
    m = goals_model.scoreline_matrix(lam, mu, max_goals)
    if rho != 0.0:
        m = m.copy()
        m[0, 0] *= 1.0 - lam * mu * rho
        m[0, 1] *= 1.0 + lam * rho
        m[1, 0] *= 1.0 + mu * rho
        m[1, 1] *= 1.0 - rho
        m = np.clip(m, 0.0, None)   # garde-fou si ρ hors zone de validité
        s = m.sum()
        if s > 0:
            m /= s
    return m


def estimate_rho(samples: list[tuple[float, float, int, int]],
                 lo: float = -0.10, hi: float = 0.03,
                 max_goals: int = 10) -> float:
    """
    ρ par maximum de vraisemblance : argmax Σ log P(x_obs, y_obs).
    `samples` = [(lam, mu, x_obs, y_obs)] d'un jeu d'ENTRAÎNEMENT (sans fuite).
    Recherche 1D (scan + raffinement). ρ attendu petit et légèrement négatif.
    """
    if not samples:
        return -0.05

    def loglik(rho: float) -> float:
        s = 0.0
        for lam, mu, x, y in samples:
            m = dixon_coles_matrix(lam, mu, rho, max_goals)
            p = m[x, y] if (x <= max_goals and y <= max_goals) else 1e-12
            s += math.log(max(float(p), 1e-12))
        return s

    grid = np.linspace(lo, hi, 27)
    best = max(grid, key=loglik)
    # raffinement autour du meilleur point
    step = (hi - lo) / 26
    fine = np.linspace(best - step, best + step, 21)
    best = max(fine, key=loglik)
    return float(best)


# --------------------------------------------------------------------------- #
# (b)+(c)+(d) prédiction complète
def _shrunk(form: TeamForm, k: float) -> tuple[float, float]:
    if form.n <= 0:
        return 0.0, 0.0
    w = form.n / (form.n + k)
    return w * form.mean_off, w * form.mean_def


def lambdas_v2(elo_i: float, elo_j: float, form_i: TeamForm, form_j: TeamForm,
               cfg: V2Config) -> tuple[float, float, float, float]:
    """
    Retourne (lambda_i, lambda_j, lambda_base_i, lambda_base_j).
    lambda_base_* = λ de base (méthode A) ; lambda_* = ajusté des résidus de forme.
    """
    w = win_expectancy(elo_i, elo_j, 0.0)               # terrain neutre
    base_i = goals_model.lambda_neutral(w)
    base_j = goals_model.lambda_neutral(1.0 - w)
    lam_i, lam_j = base_i, base_j
    if cfg.use_form_residuals:
        off_i, def_i = _shrunk(form_i, cfg.shrink_k)
        off_j, def_j = _shrunk(form_j, cfg.shrink_k)
        # attaque de i + (défense de j : ce que j concède en plus/moins)
        lam_i = base_i + off_i + def_j
        lam_j = base_j + off_j + def_i
    lo, hi = cfg.clip
    return (min(max(lam_i, lo), hi), min(max(lam_j, lo), hi), base_i, base_j)


def predict_v2(elo_i: float, elo_j: float,
               form_i: TeamForm | None = None, form_j: TeamForm | None = None,
               cfg: V2Config | None = None) -> dict:
    """
    Prédiction méthode B. `elo_i/elo_j` = Elo à utiliser (réinjecté ou non, choisi
    par l'appelant selon cfg.use_elo_reinjection). Même interface que la méthode A.
    """
    cfg = cfg or V2Config()
    form_i = form_i or TeamForm()
    form_j = form_j or TeamForm()
    lam_i, lam_j, base_i, base_j = lambdas_v2(elo_i, elo_j, form_i, form_j, cfg)
    rho = cfg.rho if cfg.use_dixon_coles else 0.0
    m = dixon_coles_matrix(lam_i, lam_j, rho, cfg.max_goals)
    win_i, draw, win_j = goals_model.outcome_probabilities(m)
    return {
        "lambda_i": lam_i, "lambda_j": lam_j,
        "lambda_base_i": base_i, "lambda_base_j": base_j,
        "matrix": m,
        "most_likely_score": goals_model.most_likely_score(m),
        "consistent_score": goals_model.consistent_score(m),
        "win_i": win_i, "draw": draw, "win_j": win_j,
        "advance_i": win_i + 0.5 * draw,
        "probs": [win_i, draw, win_j],   # ordonnées pour le RPS
    }
