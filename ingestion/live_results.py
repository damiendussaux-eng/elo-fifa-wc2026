"""
Source de résultats LIVE (plus à jour que martj42) : API scoreboard publique
d'ESPN (sans clé). Sert à COMPLÉTER automatiquement le dataset martj42 pour les
matchs récents qu'il n'a pas encore publiés (décalage de 1-2 jours), avec
VÉRIFICATION DE CONCORDANCE sur les matchs déjà présents dans les deux sources.

Sortie : écrit data/espn_results.csv (mêmes colonnes que REQUIRED), que
load_history fusionne automatiquement -> Elo, classements et prédictions à jour.

Subtilité gérée : ESPN et martj42 peuvent INVERSER domicile/extérieur (matchs sur
site neutre). On apparie donc par PAIRE NON ORDONNÉE {équipe, équipe} + date pour
éviter tout doublon, et on compare les scores par équipe (pas par position).
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from ingestion.load_history import DATA_DIR, LOCAL_CSV, OVERRIDE_CSV

ESPN_URL = ("https://site.api.espn.com/apis/site/v2/sports/soccer/"
            "fifa.world/scoreboard?dates={d}")

# Cache de la phase à élimination directe (affiches + horaires + résultats), récupéré
# d'ESPN, source de vérité de l'arbre. Une ligne par match KO vu chez ESPN.
KO_CSV = DATA_DIR / "espn_ko.csv"
# season.slug d'ESPN -> index de tour de l'arbre (0 = 16es … 4 = finale).
SLUG_TO_ROUND = {"round-of-32": 0, "round-of-16": 1, "quarterfinals": 2,
                 "semifinals": 3, "final": 4}
# Été 2026 : la France est à l'heure d'été (CEST = UTC+2) sur TOUTE la fenêtre du
# Mondial (11 juin → 19 juillet). Décalage fixe -> pas de dépendance tzdata.
PARIS_OFFSET = timedelta(hours=2)


def _to_paris(utc_iso: str) -> tuple[str, str] | None:
    """'2026-06-28T19:00Z' (UTC) -> ('2026-06-28', '21:00') en heure de Paris."""
    if not utc_iso:
        return None
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    wall = dt.astimezone(timezone.utc) + PARIS_OFFSET   # heure murale de Paris
    return wall.strftime("%Y-%m-%d"), wall.strftime("%H:%M")

# Noms ESPN -> noms du dataset martj42 (uniquement là où ils diffèrent).
ESPN_TO_DATASET = {
    "Türkiye": "Turkey", "Turkiye": "Turkey",
    "Czechia": "Czech Republic",
    "Congo DR": "DR Congo", "DR Congo": "DR Congo",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "USA": "United States",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}


def _name(n: str) -> str:
    return ESPN_TO_DATASET.get(n, n)


def fetch_scores(dates: list[str]) -> dict[tuple[str, str], dict]:
    """
    Renvoie {(date_iso, frozenset{équipeA, équipeB}): {team: buts, ...}} pour les
    matchs TERMINÉS récupérés d'ESPN sur les dates données (format 'YYYYMMDD').
    """
    out: dict[tuple[str, str], dict] = {}
    for d in dates:
        try:
            j = requests.get(ESPN_URL.format(d=d), timeout=20).json()
        except Exception:
            continue
        for e in j.get("events", []):
            try:
                comp = e["competitions"][0]
                if not comp["status"]["type"].get("completed"):
                    continue
                cs = comp["competitors"]
                h = next(c for c in cs if c["homeAway"] == "home")
                a = next(c for c in cs if c["homeAway"] == "away")
                hn, an = _name(h["team"]["displayName"]), _name(a["team"]["displayName"])
                hs, as_ = int(h["score"]), int(a["score"])
            except Exception:
                continue
            diso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            out[(diso, frozenset((hn, an)))] = {hn: hs, an: as_}
    return out


def update_cache(days_back: int = 6, days_fwd: int = 2) -> dict:
    """
    Met à jour data/espn_results.csv : pour chaque match terminé chez ESPN dans la
    fenêtre [aujourd'hui−days_back, +days_fwd] que martj42 n'a PAS encore publié,
    écrit une ligne (en respectant l'orientation domicile/extérieur de martj42 si
    le match y figure). Vérifie la concordance sur les matchs communs.

    Retour : {filled, concord, discrepancies:[...], espn_total}.
    """
    today = date.today()
    dates = [(today + timedelta(days=k)).strftime("%Y%m%d")
             for k in range(-days_back, days_fwd + 1)]
    espn = fetch_scores(dates)

    # Index martj42 des matchs WC2026 par PAIRE non ordonnée (date/orientation
    # peuvent différer entre sources ; chaque paire ne joue qu'une fois en poules).
    try:
        m = pd.read_csv(LOCAL_CSV)
    except Exception:
        m = pd.DataFrame(columns=["date", "home_team", "away_team",
                                  "home_score", "away_score", "tournament", "neutral"])
    m["date"] = pd.to_datetime(m["date"], errors="coerce")
    wc = m[(m["tournament"] == "FIFA World Cup")
           & (m["date"] >= pd.Timestamp("2026-06-01"))
           & (m["date"] <= pd.Timestamp("2026-08-31"))]
    idx: dict[frozenset, dict] = {}
    for r in wc.itertuples(index=False):
        if pd.isna(r.date):
            continue
        score = None
        if not (pd.isna(r.home_score) or pd.isna(r.away_score)):
            score = {r.home_team: int(r.home_score), r.away_team: int(r.away_score)}
        nb = str(r.neutral).strip().lower()
        idx[frozenset((r.home_team, r.away_team))] = {
            "date": r.date.strftime("%Y-%m-%d"), "home": r.home_team,
            "away": r.away_team, "score": score,
            "neutral": True if nb == "true" else (False if nb == "false" else True)}

    rows = []
    concord = 0
    discrepancies = []
    for (diso, pair), goals in espn.items():
        info = idx.get(pair)                       # appariement par paire (sans date)
        if info is not None and info["score"] is not None:
            # Match déjà publié par martj42 -> vérification de concordance, sans override.
            if info["score"] == goals:
                concord += 1
            else:
                discrepancies.append((diso, tuple(pair), info["score"], goals))
            continue
        # Match manquant chez martj42 -> on le complète depuis ESPN.
        if info is not None:                       # garde date/orientation/neutral de martj42
            diso, home, away, neutral = info["date"], info["home"], info["away"], info["neutral"]
        else:                                      # match inconnu de martj42 (rare)
            home, away = tuple(pair)
            neutral = False
        if home not in goals or away not in goals:
            continue                               # nom non concordant -> on saute
        rows.append((diso, home, away, goals[home], goals[away], "FIFA World Cup", neutral))

    if rows:
        with open(OVERRIDE_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "home_team", "away_team", "home_score",
                        "away_score", "tournament", "neutral"])
            w.writerows(rows)
    elif OVERRIDE_CSV.exists():
        OVERRIDE_CSV.unlink()                      # plus de trou -> cache inutile

    return {"filled": len(rows), "concord": concord,
            "discrepancies": discrepancies, "espn_total": len(espn)}


def fetch_ko_events(dates: list[str]) -> list[dict]:
    """
    Événements de la phase à élimination directe vus chez ESPN sur les dates données.
    Chaque dict : round_idx, city, date (Paris), time (Paris), home, away, hs, as_,
    completed, winner (nom dataset du vainqueur, TIRS AU BUT INCLUS via le drapeau
    `winner` d'ESPN). Noms mappés sur le dataset. Les affiches encore indéterminées
    (« Round of 32 5 Winner ») sont ignorées (équipes inconnues).
    """
    out: list[dict] = []
    seen: set = set()
    for d in dates:
        try:
            j = requests.get(ESPN_URL.format(d=d), timeout=20).json()
        except Exception:
            continue
        for e in j.get("events", []):
            r = SLUG_TO_ROUND.get(e.get("season", {}).get("slug", ""))
            if r is None:
                continue                            # pas un match KO
            try:
                comp = e["competitions"][0]
                cs = comp["competitors"]
                h = next(c for c in cs if c["homeAway"] == "home")
                a = next(c for c in cs if c["homeAway"] == "away")
                hd, ad = h["team"]["displayName"], a["team"]["displayName"]
            except Exception:
                continue
            if "Winner" in hd or "Winner" in ad:
                continue                            # affiche encore indéterminée
            hn, an = _name(hd), _name(ad)
            city = (((comp.get("venue", {}) or {}).get("address", {}) or {})
                    .get("city", "") or "").split(",")[0].strip()
            paris = _to_paris(comp.get("date") or e.get("date"))
            diso, tparis = paris if paris else ("", "")
            completed = bool(comp["status"]["type"].get("completed"))
            try:
                hs, as_ = int(h.get("score")), int(a.get("score"))
            except (TypeError, ValueError):
                hs = as_ = None
            winner = hn if h.get("winner") else (an if a.get("winner") else "")
            key = (r, city, diso, hn, an)
            if key in seen:
                continue
            seen.add(key)
            out.append({"round_idx": r, "city": city, "date": diso, "time": tparis,
                        "home": hn, "away": an, "hs": hs, "as_": as_,
                        "completed": completed, "winner": winner})
    return out


def update_ko_cache(days_back: int = 10, days_fwd: int = 30) -> int:
    """
    Écrit data/espn_ko.csv : affiches + horaires (heure de Paris) + résultats de la
    phase à élimination directe, sur une fenêtre couvrant tout le tableau final.
    Source = ESPN (vérité des affiches et des vainqueurs, tirs au but inclus).
    Tolérant si ESPN est injoignable. Retour : nb de matchs KO écrits.
    """
    today = date.today()
    dates = [(today + timedelta(days=k)).strftime("%Y%m%d")
             for k in range(-days_back, days_fwd + 1)]
    evs = fetch_ko_events(dates)
    cols = ["round_idx", "city", "date", "time", "home", "away",
            "hs", "as_", "completed", "winner"]
    with open(KO_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in sorted(evs, key=lambda x: (x["round_idx"], x["date"], x["city"])):
            w.writerow([e["round_idx"], e["city"], e["date"], e["time"],
                        e["home"], e["away"],
                        "" if e["hs"] is None else e["hs"],
                        "" if e["as_"] is None else e["as_"],
                        int(e["completed"]), e["winner"]])
    return len(evs)


if __name__ == "__main__":
    import config  # noqa: F401
    nk = update_ko_cache()
    print(f"Matchs KO ESPN (affiches/horaires/résultats) : {nk} -> {KO_CSV.name}")
    res = update_cache()
    print(f"ESPN : {res['espn_total']} matchs terminés vus.")
    print(f"Complétés (absents de martj42) : {res['filled']} -> {OVERRIDE_CSV.name}")
    print(f"Concordants avec martj42 : {res['concord']}")
    if res["discrepancies"]:
        print("DIVERGENCES :")
        for diso, pair, mj, es in res["discrepancies"]:
            print(f"  {diso} {pair} : martj42 {mj} vs ESPN {es}")
    else:
        print("Aucune divergence sur les matchs communs.")
