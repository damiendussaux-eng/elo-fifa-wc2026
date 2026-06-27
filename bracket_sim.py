"""
Simulateur Monte-Carlo d'un tableau à élimination directe (bracket).

Principe : le bracket est un arbre binaire. À chaque tour, on apparie les
gagnants adjacents, on calcule P(A se qualifie) via Elo, on tire l'issue,
on fait avancer le vainqueur. On répète N fois et on agrège les fréquences.

Deux sorties complémentaires :
  - reach_prob[round][team]  : P(l'équipe atteigne ce tour)  -> colonnes du bracket
  - next_match_prob[team]    : P(gagner son match du PREMIER tour), calculé
                               ANALYTIQUEMENT (sans bruit MC) car l'adversaire
                               est connu. C'est le chiffre "à côté du pays".

Résultats déjà connus : on les "épingle" (pin) par (tour, match) pour figer un
vainqueur et ne simuler que le reste -> mise à jour live au fil des résultats.

Le bracket doit avoir une taille puissance de 2 (32 pour les seizièmes WC2026).
L'ordre des équipes dans `teams` EST l'ordre des affiches : (0 vs 1), (2 vs 3)...
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

from elo import win_expectancy, win_expectancy_vec
from goals_model import (
    lambda_neutral, lambda_neutral_vec, scoreline_matrix, advance_probability,
)

# Noms des tours WC2026 (taille de départ -> libellés français), du 1er tour à la finale
ROUND_LABELS_32 = ["Seizièmes", "Huitièmes", "Quarts", "Demies", "Finale", "Vainqueur"]


@dataclass
class Team:
    name: str
    code: str          # code ISO/drapeau, ex "FR"
    elo: float
    is_host: bool = False   # nation hôte (USA/CAN/MEX) — pour avantage éventuel


def _round_labels(n_teams: int) -> list[str]:
    # n_teams = 32 -> seizièmes ... ; on tronque la liste de référence
    import math
    n_rounds = int(math.log2(n_teams))
    # on aligne sur la fin (Vainqueur, Finale, Demies, ...) pour gérer 8, 16, 32
    full = ROUND_LABELS_32
    return full[len(full) - (n_rounds + 1):]


def simulate(
    teams: list[Team],
    n_sims: int = 50_000,
    pinned: dict[tuple[int, int], int] | None = None,
    home_adv_for_hosts: float = 0.0,
    seed: int | None = 42,
    outcome_model: str = "elo",
    clip: tuple[float, float] = (0.05, 6.0),
) -> dict:
    """
    pinned : {(round_idx, match_idx): winner_global_team_index}
             round_idx 0 = premier tour. winner_global_team_index = index dans `teams`.
    home_adv_for_hosts : avantage Elo accordé à une nation hôte (0 par défaut =
             terrain neutre, hypothèse honnête sur sites fixes ; mettre ~100 si
             tu veux tester l'avantage à domicile).
    outcome_model :
        "elo"   (défaut, inchangé) : vainqueur tiré directement de l'espérance Elo.
        "goals" : couche buts (goals_model) — knockouts traités en terrain NEUTRE.
                  On tire les buts de chaque équipe (Poisson de λ borné par `clip`),
                  vainqueur = plus de buts, égalité = pile-ou-face (tirs au but).
                  next_match_prob = advance_probability analytique du 1er tour.
    Retour : dict avec labels, reach_prob (n_rounds+1 x n_teams), next_match_prob,
             title_prob.
    """
    n = len(teams)
    assert n & (n - 1) == 0 and n >= 2, "Le nombre d'équipes doit être une puissance de 2."
    pinned = pinned or {}
    rng = np.random.default_rng(seed)

    elos = np.array([t.elo for t in teams], dtype=float)
    host = np.array([t.is_host for t in teams], dtype=bool)
    labels = _round_labels(n)
    n_rounds = len(labels) - 1  # nombre de tours joués (32 -> 5)

    # field : (n_sims, k) indices d'équipes encore en lice à l'ENTRÉE du tour courant
    field = np.tile(np.arange(n), (n_sims, 1))

    # reach_counts[r] : compteur d'apparitions par équipe à l'entrée du tour r
    reach_counts = [np.zeros(n, dtype=np.int64) for _ in range(n_rounds + 1)]
    # tour 0 : toutes les équipes sont présentes
    reach_counts[0] = np.full(n, n_sims, dtype=np.int64)

    for r in range(n_rounds):
        k = field.shape[1]
        pairs = field.reshape(n_sims, k // 2, 2)
        a = pairs[:, :, 0]
        b = pairs[:, :, 1]

        # Avantage de terrain : +home_adv si A hôte et B non (et inversement)
        ha = np.zeros_like(a, dtype=float)
        if home_adv_for_hosts:
            ha += np.where(host[a] & ~host[b], home_adv_for_hosts, 0.0)
            ha -= np.where(host[b] & ~host[a], home_adv_for_hosts, 0.0)

        if outcome_model == "goals":
            # Knockouts en terrain neutre : λ de chaque équipe via le polynôme,
            # puis tirage Poisson des buts. W inclut l'éventuel avantage hôte.
            W = win_expectancy_vec(elos[a], elos[b], ha)
            lam_a = np.clip(lambda_neutral_vec(W), clip[0], clip[1])
            lam_b = np.clip(lambda_neutral_vec(1.0 - W), clip[0], clip[1])
            ga = rng.poisson(lam_a)
            gb = rng.poisson(lam_b)
            coin = rng.random(ga.shape) < 0.5            # tirs au but si nul
            a_wins = (ga > gb) | ((ga == gb) & coin)
            winners = np.where(a_wins, a, b)
        else:
            p_a = win_expectancy_vec(elos[a], elos[b], ha)
            u = rng.random((n_sims, k // 2))
            winners = np.where(u < p_a, a, b)

        # Épinglage des résultats connus pour ce tour
        for (rr, mm), w in pinned.items():
            if rr == r:
                winners[:, mm] = w

        field = winners
        # comptage des équipes ayant atteint le tour r+1
        for col in range(field.shape[1]):
            np.add.at(reach_counts[r + 1], field[:, col], 1)

    reach_prob = np.array([c / n_sims for c in reach_counts])  # (n_rounds+1, n)
    title_prob = reach_prob[-1]  # = P(vainqueur)

    # Proba analytique du match du 1er tour (adversaire connu)
    next_match_prob = np.zeros(n)
    for m in range(n // 2):
        i, j = 2 * m, 2 * m + 1
        ha = 0.0
        if home_adv_for_hosts:
            if teams[i].is_host and not teams[j].is_host:
                ha = home_adv_for_hosts
            elif teams[j].is_host and not teams[i].is_host:
                ha = -home_adv_for_hosts
        if outcome_model == "goals":
            W = win_expectancy(teams[i].elo, teams[j].elo, ha)
            la = float(np.clip(lambda_neutral(W), clip[0], clip[1]))
            lb = float(np.clip(lambda_neutral(1.0 - W), clip[0], clip[1]))
            pij = advance_probability(scoreline_matrix(la, lb))
        else:
            pij = win_expectancy(teams[i].elo, teams[j].elo, ha)
        next_match_prob[i] = pij
        next_match_prob[j] = 1.0 - pij

    return {
        "labels": labels,            # ex ["Seizièmes","Huitièmes","Quarts","Demies","Finale","Vainqueur"]
        "reach_prob": reach_prob,    # reach_prob[r][team] = P(atteindre le tour r)
        "next_match_prob": next_match_prob,
        "title_prob": title_prob,
        "teams": teams,
        "n_sims": n_sims,
    }
