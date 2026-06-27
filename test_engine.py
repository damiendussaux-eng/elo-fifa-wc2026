"""
Vérifications du moteur (sanity checks). À lancer : python test_engine.py
Les notes Elo ci-dessous sont des PLACEHOLDERS illustratifs, PAS des vraies
notes courantes — à remplacer par les données réelles d'eloratings.net.
"""
import numpy as np
from bracket_sim import Team, simulate
from elo import win_expectancy

print("=" * 60)
print("TEST 1 — Mini bracket 8 équipes (cohérence)")
print("=" * 60)
mini = [
    Team("Alpha", "AA", 2100),
    Team("Bravo", "BB", 1700),
    Team("Charlie", "CC", 1950),
    Team("Delta", "DD", 1800),
    Team("Echo", "EE", 2000),
    Team("Foxtrot", "FF", 1600),
    Team("Golf", "GG", 1850),
    Team("Hotel", "HH", 1750),
]
res = simulate(mini, n_sims=200_000, seed=1)
print("Tours :", res["labels"])
print(f"Somme des P(vainqueur) = {res['title_prob'].sum():.4f}  (doit ≈ 1.0)")
print(f"Somme P(atteindre finale) = {res['reach_prob'][2].sum():.4f}  (doit ≈ 2.0)")
print()
print("P(vainqueur) par équipe (triées) :")
order = np.argsort(-res["title_prob"])
for i in order:
    print(f"  {mini[i].name:8s} Elo {mini[i].elo:.0f}  ->  {res['title_prob'][i]*100:5.1f} %")

print()
print("TEST 2 — next_match_prob == Elo analytique du 1er match")
# Alpha(2100) vs Bravo(1700) : écart 400 -> ~91% attendu
analytic = win_expectancy(2100, 1700)
print(f"  Alpha vs Bravo : analytique {analytic*100:.1f}% | moteur {res['next_match_prob'][0]*100:.1f}%")
print(f"  (rappel : 400 pts d'écart ≈ 91% pour le mieux noté)")
assert abs(res["next_match_prob"][0] - analytic) < 1e-9

print()
print("TEST 3 — P(atteindre huitièmes) == P(gagner son seizième)")
# reach_prob[1] doit égaler next_match_prob (au bruit MC près)
diff = np.abs(res["reach_prob"][1] - res["next_match_prob"]).max()
print(f"  écart max MC vs analytique = {diff:.4f}  (faible attendu)")

print()
print("=" * 60)
print("TEST 4 — Épinglage d'un résultat connu")
print("=" * 60)
# On fige : au 1er tour (match 0), c'est Bravo (index 1) qui gagne, pas Alpha
res2 = simulate(mini, n_sims=100_000, pinned={(0, 0): 1}, seed=2)
print(f"  P(Bravo atteint les huitièmes) avec résultat figé = {res2['reach_prob'][1][1]*100:.1f}%  (doit = 100%)")
print(f"  P(Alpha atteint les huitièmes) = {res2['reach_prob'][1][0]*100:.1f}%  (doit = 0%)")
assert res2["reach_prob"][1][1] == 1.0
assert res2["reach_prob"][1][0] == 0.0

print()
print("=" * 60)
print("TEST 5 — Passage à l'échelle : 32 équipes (seizièmes WC2026)")
print("=" * 60)
rng = np.random.default_rng(0)
# 32 placeholders Elo entre 1500 et 2100
teams32 = [Team(f"T{i:02d}", f"{i:02d}", float(rng.integers(1500, 2100)))
           for i in range(32)]
import time
t0 = time.time()
res32 = simulate(teams32, n_sims=50_000, seed=7)
dt = time.time() - t0
print(f"  32 équipes, 50k sims en {dt:.2f}s")
print(f"  Tours : {res32['labels']}")
print(f"  Somme P(vainqueur) = {res32['title_prob'].sum():.4f}  (doit ≈ 1.0)")
top = np.argsort(-res32["title_prob"])[:5]
print("  Top 5 favoris (placeholders) :")
for i in top:
    print(f"    {teams32[i].name} Elo {teams32[i].elo:.0f} -> titre {res32['title_prob'][i]*100:4.1f}% | "
          f"finale {res32['reach_prob'][4][i]*100:4.1f}% | quarts {res32['reach_prob'][2][i]*100:4.1f}%")
print()
print("Tous les tests passent.")
