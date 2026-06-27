"""
Elo win-expectancy for football, version World Football Elo Ratings (Lange).
Référence primaire : http://eloratings.net/about

Formule (espérance de gain de l'équipe A) :

    W_A = 1 / (1 + 10 ** ( -(R_A - R_B + H) / 400 ))

où H est l'avantage de terrain (≈ +100 pour une nation hôte jouant chez elle,
0 en terrain neutre — cas par défaut en élimination directe sur sites fixes).

IMPORTANT — interprétation en élimination directe :
En knockout il n'y a pas de match nul (prolongation + tirs au but tranchent).
Le W_A d'Elo compte le nul comme 0,5 ; on l'utilise donc comme APPROXIMATION
de P(A se qualifie). Biais connu mais non quantifié ici : les tirs au but étant
proches du pile-ou-face, cette approximation tend à surestimer les gros favoris.
À calibrer/backtester avant toute utilisation sérieuse.
"""

from __future__ import annotations
import numpy as np


def win_expectancy(rating_a: float, rating_b: float, home_adv: float = 0.0) -> float:
    """Probabilité (scalaire) que A batte/élimine B."""
    dr = (rating_a + home_adv) - rating_b
    return 1.0 / (1.0 + 10.0 ** (-dr / 400.0))


def win_expectancy_vec(ratings_a: np.ndarray, ratings_b: np.ndarray,
                       home_adv: np.ndarray | float = 0.0) -> np.ndarray:
    """Version vectorisée pour le Monte-Carlo."""
    dr = (ratings_a + home_adv) - ratings_b
    return 1.0 / (1.0 + 10.0 ** (-dr / 400.0))
