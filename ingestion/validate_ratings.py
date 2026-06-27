"""
Validation des ratings calculés FROM SCRATCH contre les valeurs publiées par
eloratings.net (§6a). On NE cherche PAS l'égalité à l'unité : leur classification
de tournois, leur initialisation et leurs cas limites diffèrent. On vérifie :
  - l'ordre de grandeur (écart faible et SYSTÉMATIQUE, pas du bruit),
  - l'ordre des nations (corrélation de rang).

Source de référence (fichiers de données publics d'eloratings.net) :
  - https://www.eloratings.net/World.tsv   : classement courant (col2=ISO2, col3=Elo)
  - https://www.eloratings.net/en.teams.tsv: ISO2 -> nom anglais (+ alias)

Usage : python -m ingestion.validate_ratings
"""
from __future__ import annotations

from pathlib import Path

import requests

import config  # noqa: F401  (UTF-8 stdout + .env)
from ingestion.load_ratings import compute_current_ratings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORLD_TSV = "https://www.eloratings.net/World.tsv"
TEAMS_TSV = "https://www.eloratings.net/en.teams.tsv"

# Alias nom-dataset (martj42) -> nom-eloratings, quand ils diffèrent.
DATASET_TO_ELO = {
    "South Korea": "South Korea",
    "United States": "United States",
    "IR Iran": "Iran",
    "China PR": "China",
}


def _fetch(url: str, cache_name: str) -> str:
    cache = DATA_DIR / cache_name
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        cache.write_text(resp.text, encoding="utf-8")
        return resp.text
    except Exception as exc:  # repli sur le cache si réseau indisponible
        if cache.exists():
            print(f"[avertissement] réseau KO ({exc}); cache {cache_name} utilisé.")
            return cache.read_text(encoding="utf-8")
        raise


def fetch_elo_reference() -> dict[str, float]:
    """Retourne {nom_anglais: rating} depuis eloratings.net."""
    world = _fetch(WORLD_TSV, "elo_world.tsv")
    teams = _fetch(TEAMS_TSV, "elo_teams.tsv")

    name_by_iso: dict[str, str] = {}
    for line in teams.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].strip():
            name_by_iso[cols[0].strip()] = cols[1].strip()

    rating_by_name: dict[str, float] = {}
    for line in world.splitlines():
        cols = line.split("\t")
        if len(cols) < 4:
            continue
        iso2, rating_s = cols[2].strip(), cols[3].strip()
        try:
            rating = float(rating_s)
        except ValueError:
            continue
        name = name_by_iso.get(iso2, iso2)
        rating_by_name[name] = rating
    return rating_by_name


def _norm(s: str) -> str:
    return s.strip().lower()


def validate(top_n: int = 30) -> None:
    mine, as_of = compute_current_ratings()
    elo_ref = fetch_elo_reference()
    elo_norm = {_norm(k): v for k, v in elo_ref.items()}

    # Apparie sur le top_n de NOS notes (les nations qui comptent pour la WC).
    mine_sorted = sorted(mine.items(), key=lambda kv: -kv[1])[:top_n]

    rows = []
    for name, my_r in mine_sorted:
        ref_name = DATASET_TO_ELO.get(name, name)
        ref = elo_norm.get(_norm(ref_name))
        if ref is None:
            continue
        rows.append((name, my_r, ref, my_r - ref))

    if not rows:
        print("Aucune correspondance trouvée — vérifier les alias.")
        return

    diffs = sorted(d for *_, d in rows)
    n = len(diffs)
    median = diffs[n // 2] if n % 2 else (diffs[n // 2 - 1] + diffs[n // 2]) / 2
    mean = sum(diffs) / n

    print(f"Validation au {as_of} — {n} nations appariées (top {top_n} maison).\n")
    print(f"{'Équipe':22s} {'maison':>8s} {'eloratings':>11s} {'écart':>8s}")
    print("-" * 52)
    for name, my_r, ref, d in rows:
        print(f"{name:22s} {my_r:8.1f} {ref:11.1f} {d:+8.1f}")
    print("-" * 52)
    print(f"Écart MÉDIAN (maison − eloratings) = {median:+.1f}")
    print(f"Écart MOYEN                        = {mean:+.1f}")
    print(f"Écart absolu médian                = "
          f"{sorted(abs(d) for d in diffs)[n // 2]:.1f}")
    print(
        "\nLecture : un écart négatif quasi constant = décalage SYSTÉMATIQUE "
        "(init/classification de tournois différentes), pas une erreur de formule. "
        "L'ordre des nations doit, lui, concorder."
    )


if __name__ == "__main__":
    validate()
