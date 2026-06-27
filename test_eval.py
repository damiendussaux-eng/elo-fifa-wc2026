"""
Tests de la métrique RPS (evaluation.py). À lancer : python test_eval.py
"""
from evaluation import rps_single, rps_mean, outcome_index, WIN_I, DRAW, WIN_J

print("=" * 60)
print("TEST 1 — RPS : pronostic parfait -> 0")
print("=" * 60)
assert rps_single([1.0, 0.0, 0.0], WIN_I) == 0.0
assert rps_single([0.0, 1.0, 0.0], DRAW) == 0.0
assert rps_single([0.0, 0.0, 1.0], WIN_J) == 0.0
print("  OK (0 sur chaque issue)")

print("\n" + "=" * 60)
print("TEST 2 — RPS : pronostic uniforme (valeurs exactes)")
print("=" * 60)
u = [1/3, 1/3, 1/3]
print(f"  uniforme / victoire i = {rps_single(u, WIN_I):.4f}  (= 5/18)")
print(f"  uniforme / nul        = {rps_single(u, DRAW):.4f}  (= 1/9)")
assert abs(rps_single(u, WIN_I) - 5/18) < 1e-12
assert abs(rps_single(u, DRAW) - 1/9) < 1e-12
# La spec annonçait 0.1667 ; c'est inexact pour le RPS standard (voir evaluation.py).
assert abs(rps_single(u, WIN_I) - 1/6) > 0.1
print("  OK (la valeur 0.1667 de la spec ne correspond à aucune issue : voir note)")

print("\n" + "=" * 60)
print("TEST 3 — RPS récompense la confiance bien placée")
print("=" * 60)
confiant_bon = rps_single([0.8, 0.15, 0.05], WIN_I)
prudent = rps_single([0.4, 0.35, 0.25], WIN_I)
confiant_faux = rps_single([0.8, 0.15, 0.05], WIN_J)
print(f"  confiant & juste = {confiant_bon:.4f}  < prudent = {prudent:.4f}  "
      f"< confiant & faux = {confiant_faux:.4f}")
assert confiant_bon < prudent < confiant_faux

print("\n" + "=" * 60)
print("TEST 4 — outcome_index et rps_mean")
print("=" * 60)
assert outcome_index(2, 0) == WIN_I and outcome_index(1, 1) == DRAW and outcome_index(0, 3) == WIN_J
m = rps_mean([[1, 0, 0], u], [WIN_I, WIN_I])
print(f"  rps_mean([parfait, uniforme]) = {m:.4f}  (= (0 + 5/18)/2)")
assert abs(m - (0 + 5/18) / 2) < 1e-12

print("\nTous les tests passent.")
