"""
Validation d'ARCHITECTURE de l'arbre KO : on simule TOUT le tableau final jusqu'à
la finale en fabriquant un cache ESPN synthétique (les 31 matchs « terminés »),
puis on vérifie que le pipeline réel (resolve_knockout_results + load_tree) remplit
l'arbre sans blocage : affiches correctes, vainqueurs avancés, un seul champion.

But : garantir qu'il n'y aura plus de problème de mise à jour avec les données
réelles, quel que soit le scénario de résultats (y compris tirs au but).

Pré-requis : la base doit déjà avoir été construite au moins une fois (le bootstrap
de l'app le fait ; les slots R32 sont placés d'après ESPN). Le test sauvegarde puis
restaure le vrai cache data/espn_ko.csv.

Usage : uv run python test_bracket_sim.py
"""
from __future__ import annotations

import csv
import shutil

import config  # noqa: F401  (UTF-8 + .env)
import app.glue as glue
from db.connection import connect
from ingestion.live_results import KO_CSV

ROUND_SIZES = [16, 8, 4, 2, 1]
ROUND_NAMES = ["16es", "8es", "Quarts", "Demies", "Finale"]


def _state():
    """Affiches R32 réelles + métadonnées (ville/date) + Elo, depuis la base."""
    with connect() as conn, conn.cursor() as cur:
        slots0 = cur.execute(
            "SELECT match_idx, position, team_id FROM bracket_slots "
            "WHERE round_idx=0").fetchall()
        meta = {(r, m): (v, d) for r, m, v, d in cur.execute(
            "SELECT round_idx, match_idx, venue, match_date FROM matches").fetchall()}
        names = dict(cur.execute("SELECT team_id, name FROM teams").fetchall())
        elos = dict(cur.execute(
            "SELECT t.team_id, (SELECT rating FROM elo_ratings er "
            "WHERE er.team_id=t.team_id ORDER BY as_of DESC LIMIT 1) FROM teams t"
        ).fetchall())
    r0 = {(mi, pos): tid for mi, pos, tid in slots0 if tid is not None}
    return r0, meta, names, elos


def simulate_full_cache() -> int:
    """Fabrique un cache ESPN couvrant les 31 matchs, vainqueur = meilleur Elo
    (déterministe). Écrit KO_CSV. Retourne le nombre de matchs écrits."""
    r0, meta, names, elos = _state()
    if len([1 for k in r0 if k[1] == 0]) < 16:
        raise SystemExit("Base non prête : les 16es ne sont pas placés. "
                         "Lance l'app une fois (bootstrap) avant ce test.")

    winners: dict[tuple[int, int], int] = {}
    rows = []

    def part(r, m, pos):
        return r0.get((m, pos)) if r == 0 else winners.get((r - 1, 2 * m + pos))

    for r in range(5):
        for m in range(ROUND_SIZES[r]):
            a_id, b_id = part(r, m, 0), part(r, m, 1)
            assert a_id and b_id, f"Participant manquant en {ROUND_NAMES[r]} m{m}"
            na, nb = names[a_id], names[b_id]
            ea = elos.get(a_id) or 0.0
            eb = elos.get(b_id) or 0.0
            win_id = a_id if ea >= eb else b_id
            winners[(r, m)] = win_id
            hs, as_ = (2, 1) if win_id == a_id else (1, 2)
            venue, sdate = meta.get((r, m), ("", ""))
            rows.append([r, venue, str(sdate or "")[:10], "20:00",
                         na, nb, hs, as_, 1, names[win_id]])

    with open(KO_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round_idx", "city", "date", "time", "home", "away",
                    "hs", "as_", "completed", "winner"])
        w.writerows(rows)
    return len(rows)


def validate() -> None:
    n = simulate_full_cache()
    print(f"Cache synthétique : {n} matchs (les 31 du tableau).")
    resolved = glue.resolve_knockout_results()
    print(f"resolve_knockout_results : {resolved} résultats écrits.")
    assert resolved == 31, f"31 résultats attendus, {resolved} obtenus"

    tree = glue.load_tree()
    # 1) Toutes les cases ont leurs deux équipes connues (aucun « Vainqueur M… »).
    for r, boxes in enumerate(tree["rounds"]):
        for bx in boxes:
            assert bx.both_known, (
                f"Case non remplie en {ROUND_NAMES[r]} : "
                f"{bx.a.name} vs {bx.b.name}")
    # 2) Avancement cohérent : le gagnant d'une case est bien dans la case suivante.
    for r in range(4):
        for m, bx in enumerate(tree["rounds"][r]):
            win = bx.a if bx.a.is_winner else (bx.b if bx.b.is_winner else None)
            assert win is not None, f"Pas de vainqueur marqué en {ROUND_NAMES[r]} m{m}"
            nxt = tree["rounds"][r + 1][m // 2]
            advanced = {nxt.a.team_id, nxt.b.team_id}
            assert win.team_id in advanced, (
                f"{win.name} (vainqueur {ROUND_NAMES[r]} m{m}) absent du tour suivant")
    # 3) Un seul champion en finale.
    final = tree["rounds"][4][0]
    champ = final.a if final.a.is_winner else (final.b if final.b.is_winner else None)
    assert champ is not None, "Pas de champion en finale"
    print(f"Champion simulé : {champ.name}")
    print("OK : arbre rempli des 16es à la finale, avancement cohérent, "
          "aucun blocage.")


if __name__ == "__main__":
    backup = KO_CSV.with_suffix(".csv.bak")
    had = KO_CSV.exists()
    if had:
        shutil.copy(KO_CSV, backup)
    try:
        validate()
    finally:
        if had:
            shutil.move(backup, KO_CSV)            # restaure le vrai cache ESPN
            glue.resolve_knockout_results()        # rétablit l'état réel en base
        elif KO_CSV.exists():
            KO_CSV.unlink()
        print("Cache ESPN réel restauré.")
