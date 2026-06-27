"""
Tests de la méthode B (goals_model_v2) + anti-fuite walk-forward.
À lancer : python test_goals_v2.py
"""
from collections import defaultdict

import numpy as np

import goals_model
import goals_model_v2 as v2
from goals_model_v2 import TeamForm, V2Config

print("=" * 60)
print("TEST 1 — Dixon-Coles à ρ=0 == Poisson indépendant (méthode A)")
print("=" * 60)
lam, mu = 1.6, 1.1
m_dc0 = v2.dixon_coles_matrix(lam, mu, 0.0)
m_indep = goals_model.scoreline_matrix(lam, mu)
diff = float(np.abs(m_dc0 - m_indep).max())
print(f"  écart max = {diff:.2e}  (doit être ~0)")
assert diff < 1e-12
print("  OK")

print("\n" + "=" * 60)
print("TEST 2 — ρ<0 augmente P(nul) (signes Dixon-Coles)")
print("=" * 60)


def p_draw(m):
    return float(np.trace(m))


d0 = p_draw(v2.dixon_coles_matrix(lam, mu, 0.0))
dneg = p_draw(v2.dixon_coles_matrix(lam, mu, -0.06))
print(f"  P(nul) ρ=0 : {d0:.4f}   ρ=-0.06 : {dneg:.4f}  (doit augmenter)")
assert dneg > d0
# matrice reste une distribution valide
m = v2.dixon_coles_matrix(lam, mu, -0.06)
assert abs(m.sum() - 1.0) < 1e-9 and m.min() >= 0.0
print("  OK")

print("\n" + "=" * 60)
print("TEST 3 — Cohérence : B tous flags OFF == méthode A")
print("=" * 60)
cfg_off = V2Config(use_elo_reinjection=False, use_form_residuals=False,
                   use_dixon_coles=False)
b = v2.predict_v2(2050.0, 1800.0, TeamForm(), TeamForm(), cfg_off)
a = goals_model.predict_match(2050.0, 1800.0)
print(f"  probs B = [{b['win_i']:.4f}, {b['draw']:.4f}, {b['win_j']:.4f}]")
print(f"  probs A = [{a['win_i']:.4f}, {a['draw']:.4f}, {a['win_j']:.4f}]")
assert abs(b["win_i"] - a["win_i"]) < 1e-12
assert abs(b["draw"] - a["draw"]) < 1e-12
# même matrice que A (Poisson indépendant NON renormalisé : somme < 1, normal)
m_a = goals_model.scoreline_matrix(*goals_model.lambdas_for_match(2050.0, 1800.0))
assert float(np.abs(b["matrix"] - m_a).max()) < 1e-12
print("  OK")

print("\n" + "=" * 60)
print("TEST 4 — Résidus shrinkés : n=0 -> aucun effet ; n>0 -> ajustement")
print("=" * 60)
# une équipe sans historique (n=0) : λ inchangé même flag résidus ON
on = V2Config(use_form_residuals=True, use_dixon_coles=False)
b0 = v2.predict_v2(1900.0, 1900.0, TeamForm(), TeamForm(), on)
ref = v2.predict_v2(1900.0, 1900.0, TeamForm(), TeamForm(),
                    V2Config(use_form_residuals=False, use_dixon_coles=False))
assert abs(b0["lambda_i"] - ref["lambda_i"]) < 1e-12
# attaque très au-dessus des attentes -> λ_i augmente
strong = TeamForm(mean_off=0.8, mean_def=0.0, n=3)
b1 = v2.predict_v2(1900.0, 1900.0, strong, TeamForm(), on)
print(f"  λ_i sans forme = {ref['lambda_i']:.3f}  ; avec +0.8 off (n=3) = {b1['lambda_i']:.3f}")
assert b1["lambda_i"] > ref["lambda_i"]
# shrinkage : poids = n/(n+k) ; k=4.5 par défaut, n=3 -> 0.4
assert abs((b1["lambda_i"] - ref["lambda_i"]) - (3 / (3 + 4.5)) * 0.8) < 1e-9
print("  OK (shrinkage = n/(n+k) vérifié)")

print("\n" + "=" * 60)
print("TEST 5 — Anti-fuite walk-forward (compare.run)")
print("=" * 60)
import compare  # noqa: E402

res = compare.run()
seen: dict[str, int] = defaultdict(int)
ok = True
for r in res["records"]:                       # ordre = ordre du rejeu (chronologique)
    if r["form_n"] != (seen[r["home"]], seen[r["away"]]):
        ok = False
        break
    seen[r["home"]] += 1
    seen[r["away"]] += 1
print(f"  {len(res['records'])} matchs : chaque prédiction n'utilise QUE les matchs "
      f"antérieurs de l'équipe -> {'OK' if ok else 'FUITE !'}")
assert ok
print(f"  ρ estimé sur {res['n_rho_samples']} matchs WC < 2026 = {res['rho']:+.4f} "
      f"(petit, légèrement négatif : conforme)")
assert -0.15 < res["rho"] < 0.05

print("\nTous les tests passent.")
