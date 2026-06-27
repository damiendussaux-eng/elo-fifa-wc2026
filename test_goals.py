"""
Validation de la couche « buts » (goals_model). Valeurs déjà vérifiées (§8 spec).
À lancer : python test_goals.py
"""
import numpy as np

from elo import win_expectancy
from goals_model import (
    lambda_neutral, lambda_host_home, lambda_host_away, lambda_neutral_vec,
    scoreline_matrix, outcome_probabilities, most_likely_score,
    advance_probability, lambdas_for_match, predict_match,
)

print("=" * 60)
print("TEST 1 — Continuité aux frontières")
print("=" * 60)
print(f"  lambda_neutral(0.9)   = {lambda_neutral(0.9):.5f}  (cible 2.86899)")
print(f"  lambda_host_home(0.9) = {lambda_host_home(0.9):.5f}  (cible 2.54747)")
print(f"  lambda_host_away(0.1) = {lambda_host_away(0.1):.5f}  (cible 2.28291)")
assert abs(lambda_neutral(0.9) - 2.86899) < 2e-3
assert abs(lambda_host_home(0.9) - 2.54747) < 2e-3
assert abs(lambda_host_away(0.1) - 2.28291) < 2e-3
# vec == scalaire
assert abs(float(lambda_neutral_vec(0.9)) - lambda_neutral(0.9)) < 1e-9
assert abs(float(lambda_neutral_vec(0.95)) - lambda_neutral(0.95)) < 1e-9
print("  OK")

print("\n" + "=" * 60)
print("TEST 2 — Plausibilité & monotonie")
print("=" * 60)
ln05 = lambda_neutral(0.5)
print(f"  lambda_neutral(0.5) = {ln05:.3f}  (cible ≈ 1.323 ; total ≈ {2*ln05:.2f})")
assert abs(ln05 - 1.323) < 5e-3
xs = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
vals = [lambda_neutral(w) for w in xs]
print("  λ croissant sur [0.3,0.8] :", [f"{v:.3f}" for v in vals])
assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
print("  OK")

print("\n" + "=" * 60)
print("TEST 3 — Distribution des scores (sommes ≈ 1)")
print("=" * 60)
m = scoreline_matrix(1.5, 1.2, max_goals=10)
wi, dr, wj = outcome_probabilities(m)
print(f"  somme matrice = {m.sum():.5f}")
print(f"  P(i)+P(nul)+P(j) = {wi + dr + wj:.5f}")
assert abs(m.sum() - 1.0) < 1e-3
assert abs((wi + dr + wj) - 1.0) < 1e-3
print("  OK")

print("\n" + "=" * 60)
print("TEST 4 — Cohérence avec l'Elo")
print("=" * 60)
# match équilibré -> advance ≈ 0.5
li, lj = lambdas_for_match(1900, 1900)
adv = advance_probability(scoreline_matrix(li, lj))
print(f"  équilibré : advance = {adv:.3f}  (cible 0.500)")
assert abs(adv - 0.5) < 1e-3
# 2100 vs 1800 : W_e ≈ 0.849 ; P(qualif) modèle ≈ 0.836
we = win_expectancy(2100, 1800)
pred = predict_match(2100, 1800)
print(f"  2100 vs 1800 : W_e Elo = {we:.3f} (cible 0.849) ; "
      f"P(qualif) = {pred['advance_i']:.3f} (cible ≈ 0.836)")
assert abs(we - 0.849) < 2e-3
assert abs(pred["advance_i"] - 0.836) < 1.5e-2
print("  OK")

print("\n" + "=" * 60)
print("TEST 5 — Scores les plus probables")
print("=" * 60)
cases = [((1900, 1900), (1, 1)), ((2150, 1600), (4, 0)), ((1750, 2000), (0, 2))]
for (ei, ej), expected in cases:
    pred = predict_match(ei, ej)
    s = pred["most_likely_score"]
    print(f"  {ei} vs {ej} -> {s[0]}-{s[1]}  (cible {expected[0]}-{expected[1]}) "
          f"| λ = {pred['lambda_i']:.2f}/{pred['lambda_j']:.2f}")
    assert s == expected
print("  OK")

print("\n" + "=" * 60)
print("TEST 6 — Logique terrain hôte (λ^h et λ^a dépendent de W de l'hôte)")
print("=" * 60)
# Hôte i (elo 1800) reçoit j (elo 1900) : +100 -> W_host = W(1900 vs 1900) = 0.5
li, lj = lambdas_for_match(1800, 1900, i_host_home=True)
w_host = win_expectancy(1800, 1900, 100.0)
print(f"  W_host = {w_host:.3f} ; λ_hôte = {li:.3f} (=λ^h(W)) ; "
      f"λ_visiteur = {lj:.3f} (=λ^a(W))")
assert abs(li - lambda_host_home(w_host)) < 1e-9
assert abs(lj - lambda_host_away(w_host)) < 1e-9
print("  OK")

print("\n" + "=" * 60)
print("TEST 7 — Clip de stabilité [0.05, 6.0]")
print("=" * 60)
li, lj = lambdas_for_match(2400, 1200)   # écart énorme -> λ brut explose
print(f"  2400 vs 1200 : λ = {li:.3f}/{lj:.3f}  (bornés)")
assert 0.05 <= li <= 6.0 and 0.05 <= lj <= 6.0
print("  OK")

print("\nTous les tests passent.")
