"""
Glue : Postgres -> arbre de matchs prêt pour l'UI.

Modèle « match » : 31 cases (16 + 8 + 4 + 2 + 1). Chaque case a une date, un lieu,
deux participants (équipe connue ou libellé « à déterminer ») et, quand les deux
sont connus, la probabilité Elo de chaque équipe de gagner CE match
(`elo.win_expectancy`).

Avancement : les participants des tours > 0 sont DÉDUITS des résultats —
le vainqueur du match (r, m) avance en (r+1, m // 2), position m % 2. L'arbre se
remplit donc tout seul au fil des résultats insérés dans `results`.
"""
from __future__ import annotations

from dataclasses import dataclass

import config  # noqa: F401  (UTF-8 + .env)
from db.connection import connect
from elo import win_expectancy
import goals_model

DEFAULT_RATING = 1300.0
GOALS_CLIP = (0.05, 6.0)
ROUND_LABELS = ["Seizièmes", "Huitièmes", "Quarts", "Demies", "Finale"]
ROUND_SIZES = [16, 8, 4, 2, 1]


@dataclass
class Participant:
    known: bool
    name: str               # nom de l'équipe, ou libellé provisoire si inconnu
    flag: str = "🏳️"        # emoji (peu fiable sous Windows) — gardé pour info
    code: str | None = None  # code ISO2 (sert à l'image de drapeau dans l'UI)
    elo: float | None = None
    is_host: bool = False
    team_id: int | None = None
    win_prob: float | None = None   # P(se qualifier) sur CE match (si calculable)
    goals: int | None = None        # buts probables (couche buts, affiché dans l'arbre)
    pred_score: tuple[int, int] | None = None  # score prédit (P) du match de poule
    elo_delta: float | None = None  # variation d'Elo due au match (matchs joués only)
    is_winner: bool = False


@dataclass
class MatchBox:
    round_idx: int
    match_idx: int
    fifa_no: int | None
    date: object | None      # datetime.date
    venue: str | None
    a: Participant
    b: Participant
    score: tuple[int, int] | None = None   # score le plus probable (couche buts)

    @property
    def both_known(self) -> bool:
        return self.a.known and self.b.known


def _team_meta() -> dict[int, dict]:
    """{team_id: {name, flag, code, elo, is_host}} avec la dernière note Elo."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.team_id, t.name, t.flag_emoji, t.code_iso2, t.is_host,
                   (SELECT rating FROM elo_ratings er
                    WHERE er.team_id = t.team_id
                    ORDER BY as_of DESC LIMIT 1) AS rating
            FROM teams t
            """
        ).fetchall()
    out = {}
    for tid, name, flag, code, is_host, rating in rows:
        out[tid] = {
            "name": name, "flag": flag or "🏳️", "code": code,
            "is_host": bool(is_host),
            "elo": float(rating) if rating is not None else DEFAULT_RATING,
        }
    return out


def _to_date(d):
    """Convertit une date ISO ('YYYY-MM-DD') de SQLite en datetime.date."""
    if d is None:
        return None
    from datetime import date as _date
    if isinstance(d, _date):
        return d
    try:
        return _date.fromisoformat(str(d)[:10])
    except (ValueError, TypeError):
        return None


def _fetch_state():
    with connect() as conn:
        matches = conn.execute(
            "SELECT round_idx, match_idx, match_date, venue, fifa_match_no FROM matches"
        ).fetchall()
        slots0 = conn.execute(
            "SELECT match_idx, position, team_id, label FROM bracket_slots WHERE round_idx = 0"
        ).fetchall()
        results = conn.execute(
            "SELECT round_idx, match_idx, winner_team_id FROM results"
        ).fetchall()
    match_meta = {(r, m): (_to_date(d), v, f) for r, m, d, v, f in matches}
    r0 = {(mi, pos): (tid, lab) for mi, pos, tid, lab in slots0}
    res = {(r, m): w for r, m, w in results}
    return match_meta, r0, res


def _participant_round0(r0, meta, match_idx, position) -> Participant:
    tid, label = r0.get((match_idx, position), (None, None))
    if tid is not None:
        m = meta[tid]
        return Participant(known=True, name=m["name"], flag=m["flag"],
                           code=m["code"], elo=m["elo"], is_host=m["is_host"],
                           team_id=tid)
    return Participant(known=False, name=label or "à déterminer")


def _participant_advanced(prev_winner_id, prev_fifa, meta) -> Participant:
    if prev_winner_id is not None:
        m = meta[prev_winner_id]
        return Participant(known=True, name=m["name"], flag=m["flag"],
                           code=m["code"], elo=m["elo"], is_host=m["is_host"],
                           team_id=prev_winner_id)
    label = f"Vainqueur M{prev_fifa}" if prev_fifa else "à déterminer"
    return Participant(known=False, name=label)


def _apply_probs(box: MatchBox, home_adv: float) -> None:
    """Couche buts : score le plus probable + proba de QUALIFICATION par équipe.

    Knockout en terrain neutre (cf. goals_model) ; le curseur avantage hôte
    décale W (et donc λ). win_prob = P(se qualifier) = P(victoire) + 0.5·P(nul).
    """
    a, b = box.a, box.b
    if not (a.known and b.known):
        return
    ha = 0.0
    if home_adv:
        if a.is_host and not b.is_host:
            ha = home_adv
        elif b.is_host and not a.is_host:
            ha = -home_adv
    W = win_expectancy(a.elo, b.elo, ha)
    la = min(max(goals_model.lambda_neutral(W), GOALS_CLIP[0]), GOALS_CLIP[1])
    lb = min(max(goals_model.lambda_neutral(1.0 - W), GOALS_CLIP[0]), GOALS_CLIP[1])
    m = goals_model.scoreline_matrix(la, lb)
    win_a, draw, win_b = goals_model.outcome_probabilities(m)
    box.score = goals_model.consistent_score(m)   # score cohérent avec le favori
    a.goals, b.goals = box.score
    a.win_prob = win_a + 0.5 * draw
    b.win_prob = win_b + 0.5 * draw


def load_tree(home_adv: float = 0.0) -> dict:
    """Construit l'arbre complet (liste de tours, chacun = liste de MatchBox)."""
    match_meta, r0, res = _fetch_state()
    meta = _team_meta()

    rounds: list[list[MatchBox]] = []
    for r in range(5):
        boxes = []
        for m in range(ROUND_SIZES[r]):
            d, venue, fifa = match_meta.get((r, m), (None, None, None))
            if r == 0:
                a = _participant_round0(r0, meta, m, 0)
                b = _participant_round0(r0, meta, m, 1)
            else:
                fa = match_meta.get((r - 1, 2 * m), (None, None, None))[2]
                fb = match_meta.get((r - 1, 2 * m + 1), (None, None, None))[2]
                a = _participant_advanced(res.get((r - 1, 2 * m)), fa, meta)
                b = _participant_advanced(res.get((r - 1, 2 * m + 1)), fb, meta)
            box = MatchBox(round_idx=r, match_idx=m, fifa_no=fifa,
                           date=d, venue=venue, a=a, b=b)
            _apply_probs(box, home_adv)
            # marquage du vainqueur de CE match s'il est connu
            winner_id = res.get((r, m))
            if winner_id is not None:
                if box.a.team_id == winner_id:
                    box.a.is_winner = True
                elif box.b.team_id == winner_id:
                    box.b.is_winner = True
            boxes.append(box)
        rounds.append(boxes)

    return {"labels": ROUND_LABELS, "rounds": rounds}


def qualified_teams() -> list[Participant]:
    """Équipes déjà qualifiées (placées en R32), triées par Elo décroissant."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT t.team_id, t.name, t.code_iso2, t.flag_emoji, t.is_host,
                   (SELECT rating FROM elo_ratings er WHERE er.team_id = t.team_id
                    ORDER BY as_of DESC LIMIT 1) AS elo
            FROM bracket_slots bs JOIN teams t ON t.team_id = bs.team_id
            WHERE bs.round_idx = 0 AND bs.team_id IS NOT NULL
            """
        ).fetchall()
    parts = [
        Participant(known=True, name=name, code=code, flag=flag or "🏳️",
                    is_host=bool(is_host), team_id=tid,
                    elo=float(elo) if elo is not None else DEFAULT_RATING)
        for tid, name, code, flag, is_host, elo in rows
    ]
    parts.sort(key=lambda p: -(p.elo or 0.0))
    return parts


def teams_in_contention() -> list[Participant]:
    """
    Équipes ENCORE EN COURSE (qualifiées + pas encore éliminées), triées par Elo
    décroissant. Une équipe est encore en course si elle peut atteindre le TOP-3
    de son groupe — c.-à-d. top-2 (qualif directe) OU 3e (candidate au meilleur 3e).

    Critère d'élimination (borne optimiste, sans fuite) : une équipe est éliminée
    si au moins 3 autres équipes de son groupe ont DÉJÀ plus de points que son
    maximum atteignable (pts actuels + 3 × matchs restants).
    """
    meta = _team_meta()
    alive: list[Participant] = []
    for rows in group_standings().values():
        for s in rows:
            max_pts = s["pts"] + 3 * (3 - s["mj"])      # 3 matchs de poule par équipe
            guaranteed_above = sum(
                1 for u in rows
                if u["team_id"] != s["team_id"] and u["pts"] > max_pts
            )
            if guaranteed_above < 3:                     # peut encore finir top-3
                m = meta.get(s["team_id"], {})
                alive.append(Participant(
                    known=True, name=s["name"], code=s["code"],
                    flag=s["flag"], is_host=bool(s.get("is_host", False)),
                    team_id=s["team_id"],
                    elo=m.get("elo", DEFAULT_RATING),
                ))
    alive.sort(key=lambda p: -(p.elo or 0.0))
    return alive


def elo_rank_change() -> dict[str, int]:
    """
    Évolution du RANG Elo mondial (pas du score) de chaque équipe DEPUIS LE DÉBUT
    du Mondial (11/06/2026). Un seul rejeu chronologique avec snapshot à la date
    de départ. Retour : {nom: Δrang} où Δrang > 0 = l'équipe a GAGNÉ des places
    (meilleur rang), < 0 = en a perdu, 0 = inchangé.
    """
    from collections import defaultdict
    from datetime import date as _date

    from ingestion import load_history
    from ratings_engine import k_factor, update_match

    start = _date(2026, 6, 11)
    ratings: dict[str, float] = defaultdict(lambda: 1300.0)
    pre: dict[str, float] | None = None
    for row in load_history.load().itertuples(index=False):
        if pre is None and row.date.date() >= start:
            pre = dict(ratings)
        k = k_factor(row.tournament)
        rh, ra, _ = update_match(ratings[row.home_team], ratings[row.away_team],
                                 int(row.home_score), int(row.away_score), k,
                                 neutral=bool(row.neutral))
        ratings[row.home_team], ratings[row.away_team] = rh, ra
    if pre is None:
        pre = dict(ratings)

    def _ranks(r: dict[str, float]) -> dict[str, int]:
        order = sorted(r, key=lambda n: -r[n])
        return {n: i + 1 for i, n in enumerate(order)}

    cur_rank, pre_rank = _ranks(ratings), _ranks(pre)
    return {n: pre_rank.get(n, cur_rank[n]) - cur_rank[n] for n in cur_rank}


def resolve_bracket() -> int:
    """
    Place AUTOMATIQUEMENT les équipes dans les slots R32 du bracket :
      - 1ers/2es de groupe dès qu'un groupe est TERMINÉ (« Vainqueur X » -> 1er,
        « 2e X » -> 2e) ;
      - les 8 MEILLEURS 3es dans les slots « 3e groupe », mais SEULEMENT une fois
        les 12 groupes terminés (sinon on ne peut pas classer les 12 troisièmes).

    Placement des 3es = indicatif : les 8 meilleurs 3es (tri Pts/DB/BP sur les 12
    troisièmes) sont affectés aux 8 slots dans l'ordre des affiches. L'affectation
    EXACTE suit l'Annexe C FIFA (495 combinaisons) — non reproduite ici.

    Retourne le nombre de slots renseignés. Idempotent (rejoué à chaque lancement).
    """
    standings = group_standings()
    label_to_team: dict[str, int] = {}
    finished = []                                  # groupes terminés
    for code, rows in standings.items():
        if len(rows) != 4 or not all(r["mj"] == 3 for r in rows):
            continue                               # groupe non terminé
        finished.append(code)
        label_to_team[f"Vainqueur {code}"] = rows[0]["team_id"]   # 1er (tri Pts/DB/BP)
        label_to_team[f"2e {code}"] = rows[1]["team_id"]          # 2e

    # 8 meilleurs 3es : seulement si les 12 groupes sont terminés.
    best_thirds: list[tuple[str, int]] = []        # (groupe, team_id), meilleur d'abord
    if len(finished) == 12:
        thirds = [(code, rows[2]) for code, rows in standings.items() if len(rows) >= 3]
        thirds.sort(key=lambda cr: (cr[1]["pts"], cr[1]["db"], cr[1]["bp"]), reverse=True)
        best_thirds = [(code, row["team_id"]) for code, row in thirds[:8]]

    if not label_to_team and not best_thirds:
        return 0
    n = 0
    with connect() as conn, conn.cursor() as cur:
        for label, tid in label_to_team.items():
            cur.execute(
                "UPDATE bracket_slots SET team_id = %s "
                "WHERE round_idx = 0 AND label = %s",
                (tid, label),
            )
            n += cur.rowcount
        # Affecte les 8 meilleurs 3es aux 8 slots « 3e groupe ». Placement indicatif,
        # mais on ÉVITE un affrontement contre le 1er de son PROPRE groupe (impossible
        # selon l'Annexe C). L'adversaire (vainqueur de groupe) est déjà placé.
        if best_thirds:
            group_of_team = dict(
                cur.execute("SELECT team_id, group_code FROM group_teams").fetchall())
            slots = cur.execute(
                "SELECT match_idx, position, team_id, label FROM bracket_slots "
                "WHERE round_idx = 0").fetchall()
            by_pos = {(mi, pos): tid for mi, pos, tid, _lab in slots}
            third_slots = sorted((mi, pos) for mi, pos, _t, lab in slots
                                 if lab == "3e groupe")
            remaining = list(best_thirds)
            for mi, pos in third_slots:
                opp_group = group_of_team.get(by_pos.get((mi, 1 - pos)))
                pick = next((i for i, (g, _t) in enumerate(remaining)
                             if g != opp_group), 0 if remaining else None)
                if pick is None:
                    continue
                _g, tid = remaining.pop(pick)
                cur.execute(
                    "UPDATE bracket_slots SET team_id = %s "
                    "WHERE round_idx = 0 AND match_idx = %s AND position = %s",
                    (tid, mi, pos),
                )
                n += cur.rowcount
    return n


def group_standings(only: list[str] | None = None) -> dict[str, list[dict]]:
    """
    Classement de chaque groupe, calculé depuis group_matches (donc à jour avec
    le dataset). Tri : Pts, puis diff. de buts, puis buts pour (critères FIFA
    principaux). Chaque ligne porte aussi la forme (5 derniers, chronologique).

    Retour : {group_code: [ {rank,name,code,flag,is_host,mj,g,n,p,bp,bc,db,pts,
                             form:[ 'W'|'D'|'L'|'' x5 ]}, ... ]}
    """
    meta = _team_meta()
    with connect() as conn:
        members = conn.execute(
            "SELECT group_code, team_id FROM group_teams ORDER BY group_code, draw_pos"
        ).fetchall()
        matches = conn.execute(
            """
            SELECT group_code, home_team_id, away_team_id, home_score, away_score,
                   played_at
            FROM group_matches ORDER BY played_at
            """
        ).fetchall()

    codes = [c for c in sorted({g for g, _ in members}) if (only is None or c in only)]
    stats: dict[int, dict] = {}
    for code, tid in members:
        if only is not None and code not in only:
            continue
        m = meta.get(tid, {})
        stats[tid] = {
            "group": code, "team_id": tid,
            "name": m.get("name", "?"), "code": m.get("code"),
            "flag": m.get("flag", "🏳️"), "is_host": m.get("is_host", False),
            "mj": 0, "g": 0, "n": 0, "p": 0, "bp": 0, "bc": 0, "pts": 0,
            "_form": [],  # (date, 'W'|'D'|'L')
        }

    for code, h, a, hs, as_, played in matches:
        if h not in stats or a not in stats:
            continue
        sh, sa = stats[h], stats[a]
        sh["mj"] += 1; sa["mj"] += 1
        sh["bp"] += hs; sh["bc"] += as_
        sa["bp"] += as_; sa["bc"] += hs
        if hs > as_:
            sh["g"] += 1; sh["pts"] += 3; sa["p"] += 1
            rh, ra = "W", "L"
        elif hs == as_:
            sh["n"] += 1; sa["n"] += 1; sh["pts"] += 1; sa["pts"] += 1
            rh, ra = "D", "D"
        else:
            sa["g"] += 1; sa["pts"] += 3; sh["p"] += 1
            rh, ra = "L", "W"
        sh["_form"].append((played, rh)); sa["_form"].append((played, ra))

    out: dict[str, list[dict]] = {}
    for code in codes:
        rows = [s for s in stats.values() if s["group"] == code]
        for s in rows:
            s["db"] = s["bp"] - s["bc"]
            form = [r for _, r in sorted(s["_form"], key=lambda x: x[0] or "")][-3:]
            s["form"] = form + [""] * (3 - len(form))  # 3 matchs de poule par équipe
            del s["_form"]
        rows.sort(key=lambda s: (s["pts"], s["db"], s["bp"]), reverse=True)
        for i, s in enumerate(rows, 1):
            s["rank"] = i
        out[code] = rows
    return out


def _participant_from_meta(meta: dict, tid: int) -> Participant:
    m = meta[tid]
    return Participant(known=True, name=m["name"], code=m["code"], flag=m["flag"],
                       elo=m["elo"], is_host=m["is_host"], team_id=tid)


def _predict_pair(meta: dict, x: int, y: int) -> tuple[Participant, Participant, float]:
    """Prédiction (terrain neutre) pour la paire (x, y) : win_prob de chacun + nul."""
    a = _participant_from_meta(meta, x)
    b = _participant_from_meta(meta, y)
    W = win_expectancy(a.elo, b.elo, 0.0)
    la = min(max(goals_model.lambda_neutral(W), GOALS_CLIP[0]), GOALS_CLIP[1])
    lb = min(max(goals_model.lambda_neutral(1.0 - W), GOALS_CLIP[0]), GOALS_CLIP[1])
    mat = goals_model.scoreline_matrix(la, lb)
    win_a, draw, win_b = goals_model.outcome_probabilities(mat)
    a.win_prob, b.win_prob = win_a, win_b           # proba de VICTOIRE (nul à part)
    a.pred_score = goals_model.consistent_score(mat)  # score PRÉDIT cohérent (P)
    b.pred_score = a.pred_score
    return a, b, draw


def group_fixtures(only: list[str] | None = None) -> dict[str, list[dict]]:
    """
    TOUS les matchs de poule par groupe : joués d'abord (avec score RÉEL), puis à
    venir (appariements déduits + date/heure de Paris). Chaque match porte la
    prédiction P (score cohérent + probas) et, s'il est joué, le score réel R.

    Note : la prédiction utilise le rating Elo COURANT (post-résultat pour les
    matchs déjà joués) ; l'écart avec une vraie prédiction pré-match est minime.

    Retour : {group_code: [ {a, b, draw, pred:(P), real:(R)|None, played, date,
                            time(Paris), venue} ]}
    """
    from itertools import combinations
    from ingestion.source_groups import REMAINING_SCHEDULE

    meta = _team_meta()
    with connect() as conn:
        members = conn.execute(
            "SELECT group_code, team_id FROM group_teams ORDER BY group_code, draw_pos"
        ).fetchall()
        played = conn.execute(
            "SELECT group_code, home_team_id, away_team_id, home_score, away_score,"
            " played_at, pred_home_goals, pred_away_goals, p_home, p_draw, p_away,"
            " elo_home_pre, elo_away_pre, elo_home_delta, elo_away_delta"
            " FROM group_matches"
        ).fetchall()

    by_group: dict[str, list[int]] = {}
    for code, tid in members:
        by_group.setdefault(code, []).append(tid)
    played_by_group: dict[str, list] = {}
    played_pairs = set()
    for row in played:
        code, h, a = row[0], row[1], row[2]
        played_by_group.setdefault(code, []).append(row)
        played_pairs.add((code, frozenset((h, a))))

    out: dict[str, list[dict]] = {}
    codes = [c for c in sorted(by_group) if only is None or c in only]
    for code in codes:
        items = []
        # 1) matchs JOUÉS : prédiction PRÉ-MATCH FIGÉE (lue en base), score réel.
        for (_c, h, a, hs, as_, d, ph, pa_g, pH, pD, pA, eh, ea, edh, eda) in sorted(
                played_by_group.get(code, []), key=lambda r: r[5] or ""):
            A = _participant_from_meta(meta, h)
            B = _participant_from_meta(meta, a)
            if eh is not None:           # Elo PRÉ-match figé (pas l'Elo courant)
                A.elo = eh
            if ea is not None:
                B.elo = ea
            A.elo_delta, B.elo_delta = edh, eda   # variation d'Elo due au match
            A.win_prob, B.win_prob = pH, pA
            pred = (ph, pa_g) if ph is not None else None
            A.pred_score = B.pred_score = pred
            items.append({"a": A, "b": B, "draw": pD, "pred": pred,
                          "real": (hs, as_), "played": True,
                          "date": d, "time": None, "venue": None})
        # 2) matchs À VENIR : prédiction LIVE (Elo courant), évolue avec les résultats.
        for x, y in combinations(by_group[code], 2):
            if (code, frozenset((x, y))) in played_pairs:
                continue
            pa, pb, draw = _predict_pair(meta, x, y)
            d, t, venue = REMAINING_SCHEDULE.get(frozenset((pa.name, pb.name)),
                                                 (None, None, None))
            items.append({"a": pa, "b": pb, "draw": draw, "pred": pa.pred_score,
                          "real": None, "played": False,
                          "date": d, "time": t, "venue": venue})
        out[code] = items
    return out


if __name__ == "__main__":
    tree = load_tree()
    for r, boxes in enumerate(tree["rounds"]):
        print(f"\n=== {tree['labels'][r]} ({len(boxes)} matchs) ===")
        for bx in boxes:
            pa = f"{bx.a.win_prob*100:.0f}%" if bx.a.win_prob is not None else "  -"
            pb = f"{bx.b.win_prob*100:.0f}%" if bx.b.win_prob is not None else "  -"
            print(f"  M{bx.fifa_no} {bx.date}  {bx.a.name:16s} {pa:>4s}  |  "
                  f"{bx.b.name:16s} {pb:>4s}")
