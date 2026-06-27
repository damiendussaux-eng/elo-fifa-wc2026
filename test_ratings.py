"""
Vérifications du moteur de rating from scratch.
À lancer : python test_ratings.py
"""
import pandas as pd
from ratings_engine import (
    goal_difference_index, k_factor, update_match, compute_ratings, classify_tier
)
from elo import win_expectancy

print("=" * 60)
print("TEST 1 — Indice de différence de buts G (eloratings.net)")
print("=" * 60)
cases = {0: 1.0, 1: 1.0, 2: 1.5, 3: 1.75, 4: 1.875, 5: 2.0}
for n, expected in cases.items():
    got = goal_difference_index(n)
    print(f"  N={n} -> G={got}  (attendu {expected})")
    assert abs(got - expected) < 1e-12
print("  OK")

print()
print("=" * 60)
print("TEST 2 — Paliers de K")
print("=" * 60)
checks = [
    ("FIFA World Cup", 60),
    ("FIFA World Cup qualification", 40),
    ("UEFA Euro", 50),
    ("UEFA Euro qualification", 40),
    ("Copa América", 50),
    ("Friendly", 20),
    ("Some Random Trophy", 30),  # défaut
]
for tour, expected_k in checks:
    got = k_factor(tour)
    print(f"  {tour:32s} -> K={got} (tier={classify_tier(tour)}, attendu {expected_k})")
    assert got == expected_k
print("  OK")

print()
print("=" * 60)
print("TEST 3 — Exemple chiffré publié (Belgique bat Angleterre 2-0)")
print("=" * 60)
# Source (thepunterspage, reprenant eloratings) : R_n = 2084 + (20 × 1.5)(1 − 0.798)
#   = 2084 + 6.06 = 2090. K=20 (amical), G=1.5 (victoire 2 buts), terrain neutre.
# On choisit r_away tel que W_e(Belgique) ≈ 0.798.
r_bel, r_eng = 2084.0, 1845.0
we = win_expectancy(r_bel, r_eng, 0.0)
print(f"  W_e(Belgique) calculée = {we:.3f}  (cible ≈ 0.798)")
rh_new, ra_new, delta = update_match(r_bel, r_eng, 2, 0, k=20, neutral=True)
print(f"  ΔBelgique = {delta:.2f}  (cible ≈ +6.06)")
print(f"  Belgique : {r_bel} -> {rh_new:.2f}  (cible ≈ 2090)")
assert abs(delta - 6.06) < 0.15

print()
print("=" * 60)
print("TEST 4 — Symétrie (somme conservée)")
print("=" * 60)
rh_new, ra_new, delta = update_match(1900, 1700, 3, 1, k=60, neutral=False)
print(f"  Δlocal = {delta:.3f}, Δvisiteur = {ra_new - 1700:.3f}  (doivent être opposés)")
assert abs((rh_new - 1900) + (ra_new - 1700)) < 1e-9
print(f"  Somme avant = {1900+1700}, somme après = {rh_new+ra_new:.6f}")
print("  OK")

print()
print("=" * 60)
print("TEST 5 — compute_ratings sur un mini-historique synthétique")
print("=" * 60)
data = pd.DataFrame([
    # date, home, away, hs, as, tournament, neutral
    ("2024-01-01", "France", "Italie", 2, 0, "Friendly", False),
    ("2024-02-01", "Italie", "Espagne", 1, 1, "UEFA Euro", True),
    ("2024-03-01", "France", "Espagne", 3, 0, "FIFA World Cup", True),
    ("2024-04-01", "Espagne", "France", 1, 0, "FIFA World Cup qualification", False),
], columns=["date", "home_team", "away_team", "home_score", "away_score",
            "tournament", "neutral"])
ratings, hist = compute_ratings(data, init_rating=1500.0, return_history=True)
print("  Ratings finaux :")
for team, r in ratings.items():
    print(f"    {team:9s} {r:.1f}")
# La somme totale doit rester = 3 équipes × 1500 (jeu à somme nulle)
total = sum(ratings.values())
print(f"  Somme = {total:.4f}  (doit = {3*1500})")
assert abs(total - 3 * 1500) < 1e-6
print()
print("  Historique :")
print(hist.to_string(index=False))

print()
print("Tous les tests passent.")
