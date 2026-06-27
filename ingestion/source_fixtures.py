"""
Source des AFFICHES du tableau (§6c, refonte « arbre ») -> tables matches +
bracket_slots (round 0).

Contenu = calendrier officiel FIFA de la phase à élimination directe WC2026
(matchs 73→104) : dates, lieux, n° officiels, et les qualifiés DÉJÀ connus placés
dans la bonne case. Les emplacements non encore déterminés portent un libellé
provisoire (« Vainqueur F », « 2e H », « 3e groupe »).

Ordre des match_idx (leaf order) : choisi pour que le vainqueur du match
(round r, match m) avance en (r+1, m // 2), reproduisant l'arbre officiel
(M73→…→finale M104). fifa_match_no garde la trace du n° officiel.

Sources :
  - Calendrier officiel FIFA WC2026 (repris sur Wikipédia « 2026 FIFA World Cup
    knockout stage ») : structure, dates, lieux.
  - Qualifiés confirmés à ce jour (phase de groupes en cours) : Afrique du Sud,
    Canada, Allemagne, Maroc, Brésil, États-Unis, Mexique, Suisse, Argentine.

Mettre à jour : compléter les `team` au fur et à mesure des qualifications, et
enregistrer les résultats dans `results` (l'avancement dans l'arbre est déduit).

Usage :
    python -m ingestion.source_fixtures           # (ré)écrit matches + slots R32
    python -m ingestion.source_fixtures --show
"""
from __future__ import annotations

import argparse
from datetime import date

import config  # noqa: F401  (UTF-8 + .env)

# Une affiche connue -> ("team", "Nom dans teams") ; sinon -> ("label", "texte").
T = lambda name: ("team", name)   # noqa: E731
L = lambda text: ("label", text)  # noqa: E731

# round 0 (Seizièmes / R32), par match_idx (leaf order).
# Chaque affiche = un EMPLACEMENT (1er/2e de groupe, ou 3e) selon le calendrier
# officiel FIFA. Les équipes y sont placées AUTOMATIQUEMENT par glue.resolve_bracket
# dès que le groupe est terminé (« Vainqueur X » = 1er de X, « 2e X » = 2e de X).
# Les « 3e groupe » (meilleurs 3es, Annexe C) restent indéterminés ici.
# (fifa_no, date, venue, affiche_haut, affiche_bas)
R32: list[tuple[int, date, str, tuple, tuple]] = [
    (73, date(2026, 6, 28), "Inglewood",      L("2e A"),         L("2e B")),
    (75, date(2026, 6, 30), "Guadalupe",      L("Vainqueur F"),  L("2e C")),
    (74, date(2026, 6, 29), "Foxborough",     L("Vainqueur E"),  L("3e groupe")),
    (77, date(2026, 6, 30), "East Rutherford", L("Vainqueur I"), L("3e groupe")),
    (83, date(2026, 7, 2),  "Toronto",        L("2e K"),         L("2e L")),
    (84, date(2026, 7, 2),  "Inglewood",      L("Vainqueur H"),  L("2e J")),
    (81, date(2026, 7, 2),  "Santa Clara",    L("Vainqueur D"),  L("3e groupe")),
    (82, date(2026, 7, 1),  "Seattle",        L("Vainqueur G"),  L("3e groupe")),
    (76, date(2026, 6, 29), "Houston",        L("Vainqueur C"),  L("2e F")),
    (78, date(2026, 6, 30), "Arlington",      L("2e E"),         L("2e I")),
    (79, date(2026, 7, 1),  "Mexico City",    L("Vainqueur A"),  L("3e groupe")),
    (80, date(2026, 7, 1),  "Atlanta",        L("Vainqueur L"),  L("3e groupe")),
    (86, date(2026, 7, 4),  "Miami Gardens",  L("Vainqueur J"),  L("2e H")),
    (88, date(2026, 7, 3),  "Arlington",      L("2e D"),         L("2e G")),
    (85, date(2026, 7, 1),  "Vancouver",      L("Vainqueur B"),  L("3e groupe")),
    (87, date(2026, 7, 3),  "Kansas City",    L("Vainqueur K"),  L("3e groupe")),
]

# Tours > 0 : seulement les métadonnées (les équipes sont déduites des résultats).
# {round_idx: [(fifa_no, date, venue), ... par match_idx]}
LATER: dict[int, list[tuple[int, date, str]]] = {
    1: [  # Huitièmes (R16)
        (90, date(2026, 7, 4), "Houston"),
        (89, date(2026, 7, 4), "Philadelphia"),
        (93, date(2026, 7, 6), "Arlington"),
        (94, date(2026, 7, 6), "Seattle"),
        (91, date(2026, 7, 5), "East Rutherford"),
        (92, date(2026, 7, 5), "Mexico City"),
        (95, date(2026, 7, 7), "Atlanta"),
        (96, date(2026, 7, 7), "Vancouver"),
    ],
    2: [  # Quarts
        (97,  date(2026, 7, 9),  "Foxborough"),
        (98,  date(2026, 7, 10), "Inglewood"),
        (99,  date(2026, 7, 11), "Miami Gardens"),
        (100, date(2026, 7, 11), "Kansas City"),
    ],
    3: [  # Demies
        (101, date(2026, 7, 14), "Arlington"),
        (102, date(2026, 7, 15), "Atlanta"),
    ],
    4: [  # Finale
        (104, date(2026, 7, 19), "East Rutherford"),
    ],
}

ROUND_SIZES = [16, 8, 4, 2, 1]


def load() -> None:
    """(Ré)écrit la table matches (31 lignes) + les slots R32 (32 lignes)."""
    from db.connection import connect

    match_rows: list[tuple] = []        # (round, match_idx, date, venue, fifa)
    slot_rows: list[tuple] = []         # (round, match_idx, position, team_name|None, label|None)

    for match_idx, (fifa, d, venue, a, b) in enumerate(R32):
        match_rows.append((0, match_idx, d.isoformat(), venue, fifa))  # date ISO
        for position, (kind, val) in enumerate((a, b)):
            if kind == "team":
                slot_rows.append((0, match_idx, position, val, None))
            else:
                slot_rows.append((0, match_idx, position, None, val))

    for round_idx, metas in LATER.items():
        for match_idx, (fifa, d, venue) in enumerate(metas):
            match_rows.append((round_idx, match_idx, d.isoformat(), venue, fifa))

    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO matches (round_idx, match_idx, match_date, venue, fifa_match_no)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (round_idx, match_idx) DO UPDATE
              SET match_date = EXCLUDED.match_date,
                  venue = EXCLUDED.venue,
                  fifa_match_no = EXCLUDED.fifa_match_no
            """,
            match_rows,
        )
        # Résolution des noms -> team_id.
        cur.execute("SELECT name, team_id FROM teams")
        id_by_name = dict(cur.fetchall())
        resolved = []
        for round_idx, match_idx, position, name, label in slot_rows:
            tid = id_by_name.get(name) if name else None
            if name and tid is None:
                raise ValueError(f"Équipe absente de teams : {name!r}")
            resolved.append((round_idx, match_idx, position, tid, label))
        cur.executemany(
            """
            INSERT INTO bracket_slots (round_idx, match_idx, position, team_id, label)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (round_idx, match_idx, position) DO UPDATE
              SET team_id = EXCLUDED.team_id, label = EXCLUDED.label
            """,
            resolved,
        )
        # Nations hôtes (★ + avantage à domicile dans l'UI).
        cur.executemany(
            "UPDATE teams SET is_host = 1 WHERE name = %s",
            [("United States",), ("Mexico",), ("Canada",)],
        )
    n_known = sum(1 for _, _, _, a, b in R32 for x in (a, b) if x[0] == "team")
    print(f"matches : 31 lignes écrites. Slots R32 : 32 ({n_known} équipes connues).")


def show() -> None:
    from db.connection import connect

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.round_idx, m.match_idx, m.fifa_match_no, m.match_date, m.venue,
                   t0.name, s0.label, t1.name, s1.label
            FROM matches m
            LEFT JOIN bracket_slots s0
              ON s0.round_idx=m.round_idx AND s0.match_idx=m.match_idx AND s0.position=0
            LEFT JOIN teams t0 ON t0.team_id=s0.team_id
            LEFT JOIN bracket_slots s1
              ON s1.round_idx=m.round_idx AND s1.match_idx=m.match_idx AND s1.position=1
            LEFT JOIN teams t1 ON t1.team_id=s1.team_id
            ORDER BY m.round_idx, m.match_idx
            """
        ).fetchall()
    names = ["Seizièmes", "Huitièmes", "Quarts", "Demies", "Finale"]
    cur_r = -1
    for r, mi, fifa, d, venue, n0, l0, n1, l1 in rows:
        if r != cur_r:
            print(f"\n=== {names[r]} ===")
            cur_r = r
        a = n0 or l0 or "à déterminer"
        b = n1 or l1 or "à déterminer"
        print(f"  M{fifa} {d}  {a:18s} vs {b:18s} @ {venue}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        show()
    else:
        load()
        show()


if __name__ == "__main__":
    main()
