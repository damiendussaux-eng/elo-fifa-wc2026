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
from datetime import date, timedelta

import pandas as pd
import requests

from ingestion.load_history import LOCAL_CSV, OVERRIDE_CSV

ESPN_URL = ("https://site.api.espn.com/apis/site/v2/sports/soccer/"
            "fifa.world/scoreboard?dates={d}")

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


if __name__ == "__main__":
    import config  # noqa: F401
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
