"""
UI Streamlit — ARBRE du tableau final WC2026 (style Google).

5 colonnes : Seizièmes (16 cases) → Huitièmes (8) → Quarts (4) → Demies (2) →
Finale (1) = 31 cases. Chaque case = un match : date + 2 équipes (drapeau, nom,
proba Elo de gagner CE match). « À déterminer » tant que l'adversaire est inconnu.
L'arbre se remplit au fil des résultats (table `results`, avancement déduit).

Lancement : uv run streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# `streamlit run app/streamlit_app.py` met le dossier app/ sur sys.path, pas la
# racine du projet : on l'ajoute pour pouvoir importer config / app / db / elo.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

import config  # noqa: F401,E402  (UTF-8 + .env)
import evaluation  # noqa: E402
from app import glue  # noqa: E402
from ingestion.teams_ref import fr_name  # noqa: E402

st.set_page_config(
    page_title="Coupe du Monde de Football 2026 — Résultats et pronostics Elo",
    layout="wide")


@st.cache_resource(show_spinner="Mise à jour des données (téléchargement, Elo, "
                                "bracket, groupes)…",
                   ttl=900)  # 15 min : sinon les données restent figées au 1er boot
def bootstrap_refresh() -> dict:
    """
    Rafraîchit TOUT périodiquement : re-télécharge le dataset, recalcule l'Elo,
    réingère le bracket et les matchs/classements de poule. Le TTL (15 min) est
    ESSENTIEL en ligne : sans lui, cache_resource ne s'exécute qu'au démarrage du
    process Streamlit Cloud et sert ensuite des données figées indéfiniment (les
    nouveaux résultats et 3es de groupe ne remontaient jamais). Robuste : repli sur
    le cache local si le réseau échoue, et n'empêche pas l'app de démarrer si la
    base est KO.
    """
    from db.migrate import migrate
    from ingestion import (load_history, load_ratings, live_results,
                           source_fixtures, source_groups)

    # Auto-réparation Streamlit Cloud : après un push qui AJOUTE des fonctions, le
    # file-watcher ré-exécute ce script mais peut garder en cache (sys.modules) les
    # modules importés dans leur ANCIENNE version -> « module has no attribute … ».
    # On recharge à la volée ceux qui sont périmés (live_results AVANT glue, qui en
    # dépend), évitant d'avoir à rebooter l'app manuellement.
    try:
        import importlib
        if not hasattr(live_results, "update_ko_cache"):
            importlib.reload(live_results)
        if not hasattr(glue, "resolve_knockout_results"):
            importlib.reload(glue)
    except Exception:                                 # reload best-effort
        pass

    status: dict = {"ok": True, "as_of": None, "warnings": [], "live": None}
    try:
        load_history.download(force=True)          # dataset martj42 frais
    except Exception as exc:                        # réseau KO -> cache local
        status["warnings"].append(f"téléchargement indisponible ({exc}) — "
                                  "dernier dataset local utilisé")
    try:
        # Source plus à jour (ESPN) : complète martj42 pour les matchs récents,
        # avec vérification de concordance. Tolérant si ESPN est injoignable.
        status["live"] = live_results.update_cache()
        status["ko_cache"] = live_results.update_ko_cache()  # affiches+horaires+résultats KO (ESPN)
    except Exception as exc:
        status["warnings"].append(f"source live ESPN indisponible ({exc})")
    try:
        migrate()                                  # schéma (idempotent)
        ratings, as_of = load_ratings.compute_current_ratings()
        load_ratings.persist(ratings, as_of)       # Elo courant
        source_fixtures.load()                     # bracket + dates (emplacements)
        source_groups.load()                       # matchs + prédictions figées
        status["resolved"] = glue.resolve_bracket()  # place 1ers/2es de groupe (repli)
        status["ko_resolved"] = glue.resolve_knockout_results()  # affiches+résultats KO (ESPN)
        status["as_of"] = str(as_of)
    except Exception as exc:                        # base KO -> on garde l'existant
        status["ok"] = False
        status["warnings"].append(f"base non rafraîchie ({exc})")
    return status


@st.cache_data(show_spinner=False)
def _rank_changes_cached(as_of: str | None) -> dict:
    """Évolution du rang Elo (cache par `as_of` : recalcul seulement si données MAJ)."""
    return glue.elo_rank_change()


MOIS = ["", "janv.", "févr.", "mars", "avril", "mai", "juin",
        "juil.", "août", "sept.", "oct.", "nov.", "déc."]
HEADER_H = 30             # hauteur de l'en-tête de colonne (= décalage des connecteurs)
COL_W = 260               # largeur FIXE d'une colonne/case (assez large pour les noms
                          # complets + Elo pré-match/delta ; le tout déborde -> scroll H)
BOX_H = 78                # hauteur FIXE d'une case-match (contient date + 2 équipes en entier)
SLOT0 = 92                # emplacement d'un 16e (doit dépasser BOX_H pour laisser un écart)
BODY_H = SLOT0 * 16       # hauteur du corps -> alignement « arbre » (space-around)
BRACKET_H = BODY_H + HEADER_H
LINE = "#6b78b0"          # couleur des traits de liaison
ROUND_SIZES = [16, 8, 4, 2, 1]


def date_fr(d) -> str:
    return f"{d.day} {MOIS[d.month]}" if d else "date à confirmer"


# Couleurs de FOND des cases selon le statut du match. Volontairement HORS du
# gradient rouge-jaune-vert (réservé aux lignes d'équipes) : ardoise / bleu / violet.
STATUS_BG = {
    "done":   ("#232a3f", "#7c89ad"),   # déjà joué — ardoise neutre
    "today":  ("#143258", "#3b9bff"),   # aujourd'hui, pas encore terminé — bleu
    "future": ("#281d4a", "#9b6bff"),   # jours suivants — violet
}
STATUS_LABEL = {
    "done": "déjà joué", "today": "aujourd'hui (en cours)", "future": "à venir",
}


def _match_status(date_val, is_done: bool) -> str:
    from datetime import date as _date
    if is_done:
        return "done"
    d = date_val
    if not isinstance(d, _date):
        try:
            d = _date.fromisoformat(str(date_val))
        except (ValueError, TypeError):
            return "future"
    return "today" if d <= datetime.now().date() else "future"


def status_legend() -> str:
    chips = []
    for s in ("done", "today", "future"):
        bg, acc = STATUS_BG[s]
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:6px;'
            'margin-right:16px;">'
            f'<span style="display:inline-block;width:15px;height:15px;'
            f'border-radius:3px;background:{bg};border-left:4px solid {acc};"></span>'
            f'<span style="color:#333;font-size:0.8rem;">{STATUS_LABEL[s]}</span></span>'
        )
    return f'<div style="margin:2px 0 8px;">{"".join(chips)}</div>'


def heat_color(p: float | None) -> tuple[str, str]:
    """Gradient feu tricolore selon la proba de gagner CE match :
    rouge (faible) -> jaune (50 %) -> vert (élevé). Couleurs vives, texte blanc."""
    if p is None:
        return "#1b2142", "#7b86c2"          # inconnu / à déterminer
    p = max(0.0, min(1.0, p))
    hue = 120 * p                            # 0=rouge, 60=jaune, 120=vert
    light = 40 - 4 * (1 - abs(2 * p - 1))    # jaune (mid) un peu plus sombre -> texte lisible
    return f"hsl({hue:.0f},82%,{light:.0f}%)", "#ffffff"


# Sous-nations britanniques : codes flagcdn dédiés (sinon "gb" = Union Jack).
SPECIAL_FLAG = {"England": "gb-eng", "Scotland": "gb-sct", "Wales": "gb-wls"}


def flag_img(name: str, code: str | None, known: bool = True, w: int = 21) -> str:
    """Mini-drapeau en IMAGE (flagcdn), fiable partout — contrairement aux
    emojis de drapeau que Windows n'affiche pas (il les rend en code ISO2)."""
    h = round(w * 2 / 3)
    placeholder = (f'<span style="display:inline-block;width:{w}px;height:{h}px;'
                   'border-radius:2px;background:#2a3358;flex:0 0 auto;"></span>')
    if not known:
        return placeholder
    c = SPECIAL_FLAG.get(name) or (code or "").lower()
    if not c:
        return placeholder
    return (
        f'<img src="https://flagcdn.com/w40/{c}.png" width="{w}" height="{h}" '
        f'alt="" loading="lazy" style="flex:0 0 auto;border-radius:2px;'
        f'object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.18);">'
    )


def flag_html(part) -> str:
    return flag_img(part.name, part.code, part.known)


def team_row(part, pr: bool = False, real_goal=None) -> str:
    """Ligne d'une équipe. `pr=True` (arbre) ajoute 2 colonnes : P (buts prédits)
    et R (buts réels, vide tant qu'indisponible)."""
    bg, fg = heat_color(part.win_prob if part.known else None)
    name = fr_name(part.name) + (" ★" if getattr(part, "is_host", False) else "")
    if part.win_prob is not None:
        pct = f"{part.win_prob*100:.0f}%"
        if (not pr) and part.goals is not None:   # mode poule : proba · buts inline
            pct += f'<span style="font-weight:400;"> · </span>{part.goals}'
    else:
        pct = ""
    weight = "700" if part.is_winner else "400"
    border = "box-shadow:inset 0 0 0 2px #16e0a3;" if part.is_winner else ""
    style_name = "font-style:italic;opacity:.85;" if not part.known else ""
    check = "✓ " if part.is_winner else ""
    elo = ""
    if part.known and part.elo is not None:
        inner = f"{part.elo:.0f}"
        d = getattr(part, "elo_delta", None)
        if d is not None:                       # match joué : + points gagnés/perdus
            inner += f" {'+' if d >= 0 else '−'} {abs(d):.0f}"
        elo = (f'<span style="flex:0 0 auto;opacity:.72;font-weight:400;'
               f'font-size:0.92em;margin-right:4px;">({inner})</span>')
    pr_cells = ""
    if pr:
        pg = part.goals if part.goals is not None else "·"
        rg = real_goal if real_goal is not None else "·"
        pr_cells = (f'<span style="flex:0 0 15px;text-align:center;">{pg}</span>'
                    f'<span style="flex:0 0 15px;text-align:center;">{rg}</span>')
    return (
        f'<div style="display:flex;align-items:center;gap:6px;padding:3px 6px;'
        f'border-radius:5px;background:{bg};color:{fg};font-size:0.76rem;'
        f'line-height:1.25;font-weight:{weight};{border}margin:2px 0;">'
        f'{flag_html(part)}'
        f'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;'
        f'white-space:nowrap;{style_name}">{check}{name}</span>'
        f'{elo}<b>{pct}</b>{pr_cells}</div>'
    )


def match_box(bx) -> str:
    when = date_fr(bx.date)
    if getattr(bx, "time", None):
        when += f" · {bx.time}"               # heure de Paris (ESPN)
    head = f"M{bx.fifa_no} · {when}"
    extra = f' <span style="color:#5b6178;">· {bx.venue}</span>' if bx.venue else ""
    rs = getattr(bx, "real_score", None)       # buts réels (a, b) si match joué
    ra = rs[0] if rs else None
    rb = rs[1] if rs else None
    bg, acc = STATUS_BG[_match_status(bx.date, bx.a.is_winner or bx.b.is_winner)]
    # En-tête : date à gauche, libellés des colonnes P (prédit) / R (réel) à droite.
    header = (
        # mêmes gap (6px) et retrait horizontal (6px) que les pastilles d'équipe,
        # pour que P et R tombent pile au-dessus des chiffres des lignes.
        '<div style="display:flex;align-items:center;gap:6px;padding:0 6px;'
        'font-size:0.62rem;line-height:1.2;margin-bottom:2px;">'
        f'<span style="flex:1;color:#f78fb3;overflow:hidden;'
        f'text-overflow:ellipsis;white-space:nowrap;">{head}{extra}</span>'
        '<span style="flex:0 0 15px;text-align:center;color:#9aa3c7;'
        'font-weight:700;">P</span>'
        '<span style="flex:0 0 15px;text-align:center;color:#9aa3c7;'
        'font-weight:700;">R</span></div>'
    )
    return (
        f'<div style="background:{bg};border:1px solid #2a3358;'
        f'border-left:4px solid {acc};border-radius:8px;'
        f'padding:4px 7px;box-sizing:border-box;height:{BOX_H}px;overflow:hidden;">'
        f'{header}{team_row(bx.a, pr=True, real_goal=ra)}'
        f'{team_row(bx.b, pr=True, real_goal=rb)}'
        '</div>'
    )


def _round_column(label: str, boxes_html: str) -> str:
    return (
        f'<div style="flex:0 0 {COL_W}px;display:flex;flex-direction:column;">'
        f'<div style="height:{HEADER_H}px;line-height:{HEADER_H}px;text-align:center;'
        f'font-weight:700;color:#f72585;text-transform:uppercase;font-size:0.78rem;'
        f'letter-spacing:.5px;">{label}</div>'
        f'<div style="height:{BODY_H}px;display:flex;flex-direction:column;'
        f'justify-content:space-around;">{boxes_html}</div>'
        '</div>'
    )


def _connector_column(left_size: int) -> str:
    """
    Colonne de traits reliant les `left_size` cases d'un tour aux `left_size//2`
    cases du tour suivant. Chaque unité = une accolade « ] » (bords haut/droit/bas)
    dont les bords horizontaux tombent pile sur le centre des deux cases sources,
    et dont le milieu du trait vertical s'aligne sur la case d'arrivée.
    """
    u = BODY_H / left_size                      # hauteur d'un « slot » du tour gauche
    unit = (
        f'<div style="height:{u:.2f}px;box-sizing:border-box;'
        f'border-top:2px solid {LINE};border-right:2px solid {LINE};'
        f'border-bottom:2px solid {LINE};"></div>'
    )
    units = unit * (left_size // 2)
    return (
        '<div style="flex:0 0 22px;display:flex;flex-direction:column;">'
        f'<div style="height:{HEADER_H}px;"></div>'
        f'<div style="height:{BODY_H}px;display:flex;flex-direction:column;'
        f'justify-content:space-around;">{units}</div>'
        '</div>'
    )


def render_tree(tree: dict) -> None:
    parts = []
    n_rounds = len(tree["rounds"])
    for r, boxes in enumerate(tree["rounds"]):
        boxes_html = "".join(match_box(bx) for bx in boxes)
        parts.append(_round_column(tree["labels"][r], boxes_html))
        if r < n_rounds - 1:
            parts.append(_connector_column(ROUND_SIZES[r]))
    html = (
        f'<div style="display:flex;height:{BRACKET_H}px;background:#0b0e1f;'
        f'border-radius:10px;padding:8px;overflow-x:auto;'
        f'-webkit-overflow-scrolling:touch;">'
        + "".join(parts) + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _rank_arrow(delta: int) -> str:
    """Flèche d'évolution du RANG Elo : ↑ vert (gagné), ↓ rouge (perdu), → orange."""
    if delta > 0:
        return (f'<span title="rang Elo : +{delta}" style="color:#16e0a3;'
                f'font-weight:700;">▲{delta}</span>')
    if delta < 0:
        return (f'<span title="rang Elo : {delta}" style="color:#e24b4a;'
                f'font-weight:700;">▼{abs(delta)}</span>')
    return ('<span title="rang Elo inchangé" style="color:#f5a623;'
            'font-weight:700;">▬</span>')


def render_qualified(teams, rank_changes: dict[str, int] | None = None) -> None:
    """Panneau de droite : équipes en lice triées par Elo décroissant (drapeau,
    nom, Elo) + flèche d'évolution du RANG Elo mondial depuis le début du Mondial."""
    rank_changes = rank_changes or {}
    rows = []
    for i, p in enumerate(teams, 1):
        host = " ★" if getattr(p, "is_host", False) else ""
        arrow = _rank_arrow(rank_changes.get(p.name, 0))
        rows.append(
            '<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;'
            'background:#141a33;border:1px solid #2a3358;border-radius:6px;'
            'margin:3px 0;font-size:0.82rem;">'
            f'<span style="color:#7b86c2;width:1.3rem;text-align:right;'
            f'flex:0 0 auto;">{i}</span>'
            f'{flag_html(p)}'
            '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;'
            f'white-space:nowrap;color:#ffffff;">{fr_name(p.name)}{host}</span>'
            f'<b style="color:#16e0a3;">{p.elo:.0f}</b>'
            f'<span style="flex:0 0 auto;width:2.2rem;text-align:right;'
            f'font-size:0.78rem;">{arrow}</span></div>'
        )
    now = datetime.now().strftime("%d/%m/%Y à %H:%M")
    header = (
        '<div style="font-weight:700;color:#f72585;text-transform:uppercase;'
        'font-size:0.78rem;letter-spacing:.5px;margin-bottom:1px;">'
        f'Encore en lice · Elo actuel ({len(teams)})</div>'
        '<div style="color:#7b86c2;font-size:0.68rem;margin-bottom:6px;">'
        f'🕒 {now}</div>'
    )
    legend = (
        '<div style="color:#9aa3c7;font-size:0.68rem;line-height:1.4;'
        'margin-bottom:8px;">Flèche = évolution du <b>rang Elo</b> depuis le '
        '<b>début du Mondial</b> (11/06) : '
        '<span style="color:#16e0a3;font-weight:700;">▲</span> monté · '
        '<span style="color:#e24b4a;font-weight:700;">▼</span> descendu · '
        '<span style="color:#f5a623;font-weight:700;">▬</span> stable.</div>'
    )
    st.markdown(header + legend + "".join(rows), unsafe_allow_html=True)


# Les 12 groupes, affichés en grille de 3 colonnes (donc 4 lignes).
DISPLAY_GROUPS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
FORM_COLORS = {"W": "#16e0a3", "L": "#e24b4a", "D": "#7c7f8a"}


def _pastille(result: str) -> str:
    if result in FORM_COLORS:
        return (f'<span style="display:inline-block;width:11px;height:11px;'
                f'border-radius:50%;background:{FORM_COLORS[result]};'
                f'margin-right:2px;"></span>')
    return ('<span style="display:inline-block;width:11px;height:11px;'
            'border-radius:50%;background:transparent;border:1px solid #3a4470;'
            'margin-right:2px;"></span>')


def _group_card(code: str, rows: list[dict]) -> str:
    th = ('text-align:center;color:#f78fb3;font-weight:600;padding:3px 2px;'
          'font-size:0.64rem;')
    head = (
        f'<th style="text-align:left;{th}">Équipe</th>'
        f'<th style="{th}">MJ</th><th style="{th}">G</th><th style="{th}">N</th>'
        f'<th style="{th}">P</th><th style="{th}">BP</th><th style="{th}">BC</th>'
        f'<th style="{th}">DB</th><th style="{th}">Pts</th>'
        f'<th style="{th}">3 derniers</th>'
    )
    trs = []
    for r in rows:
        td = "text-align:center;padding:3px 2px;color:#dfe3ff;"
        team = (
            f'<td style="padding:3px 2px;"><div style="display:flex;'
            f'align-items:center;gap:6px;">'
            f'<span style="color:#7b86c2;width:0.9rem;flex:0 0 auto;">{r["rank"]}</span>'
            f'{flag_img(r["name"], r["code"], w=18)}'
            f'<span style="color:#fff;flex:1;min-width:0;white-space:nowrap;'
            f'overflow:hidden;text-overflow:ellipsis;">{fr_name(r["name"])}</span>'
            f'</div></td>'
        )
        form = "".join(_pastille(x) for x in r["form"])
        trs.append(
            f'<tr style="border-top:1px solid #2a3358;">{team}'
            f'<td style="{td}">{r["mj"]}</td><td style="{td}">{r["g"]}</td>'
            f'<td style="{td}">{r["n"]}</td><td style="{td}">{r["p"]}</td>'
            f'<td style="{td}">{r["bp"]}</td><td style="{td}">{r["bc"]}</td>'
            f'<td style="{td}">{r["db"]:+d}</td>'
            f'<td style="{td}color:#16e0a3;font-weight:700;">{r["pts"]}</td>'
            f'<td style="{td}white-space:nowrap;">{form}</td></tr>'
        )
    # Largeurs FIXES identiques pour tous les groupes (sinon chaque tableau
    # dimensionne ses colonnes selon son contenu -> désalignement).
    colgroup = ('<colgroup><col style="width:34%">'
                + '<col style="width:6%">' * 8
                + '<col style="width:18%"></colgroup>')
    return (
        '<div style="background:#141a33;border:1px solid #2a3358;border-radius:8px;'
        'padding:8px 10px;">'
        f'<div style="font-weight:700;color:#f72585;margin-bottom:4px;'
        f'font-size:0.85rem;">Groupe {code}</div>'
        '<table style="width:100%;table-layout:fixed;border-collapse:collapse;'
        'font-size:0.72rem;">'
        f'{colgroup}<thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(trs)}</tbody></table></div>'
    )


def render_groups(standings: dict[str, list[dict]]) -> None:
    cards = "".join(_group_card(c, standings[c]) for c in DISPLAY_GROUPS
                    if c in standings)
    grid = (
        '<div style="display:grid;gap:12px;'
        'grid-template-columns:repeat(auto-fit,minmax(300px,1fr));">'
        + cards + '</div>'
    )
    legend = (
        '<div style="margin-top:12px;padding:10px 14px;background:#141a33;'
        'border:1px solid #2a3358;border-radius:8px;color:#b8c0e0;'
        'font-size:0.78rem;line-height:1.6;">'
        '<b style="color:#f72585;">Légende</b><br>'
        '<b>Équipe</b> : classée par points décroissants · '
        '<b>MJ</b> matchs joués · <b>G</b> gagnés · <b>N</b> nuls · '
        '<b>P</b> perdus · <b>BP</b> buts pour · <b>BC</b> buts contre · '
        '<b>DB</b> différence de buts (BP − BC) · <b>Pts</b> points.<br>'
        '<b>Pts = 3 × G + 1 × N</b> (victoire 3 pts, nul 1 pt, défaite 0 pt). '
        'À égalité de points : départage par différence de buts, puis buts pour '
        '(critères FIFA principaux).<br>'
        '<b>3 derniers</b> : '
        f'{_pastille("W")} gagné · {_pastille("L")} perdu · '
        f'{_pastille("D")} nul · {_pastille("")} non disputé.'
        '</div>'
    )
    st.markdown(grid + legend, unsafe_allow_html=True)


def _fixture_box(m: dict) -> str:
    d, t, v = m["date"], m["time"], m["venue"]
    if m["played"]:
        when = f'Joué · {date_fr(_as_date(d))}'
    elif d is not None:
        when = f'{date_fr(_as_date(d))}' + (f' · {t} (Paris)' if t else "")
        when += f' <span style="color:#5b6178;">· {v}</span>' if v else ""
    else:
        when = "date/heure à confirmer"

    pred = m.get("pred")
    real = m.get("real")
    draw = m.get("draw")

    # Marqueur de réussite de la prédiction (matchs joués seulement) :
    #  ✓ score exact prédit == réel ; × issue prédite (proba max) ≠ issue réelle.
    mark = ""
    if m["played"] and real is not None and pred is not None:
        ro = "A" if real[0] > real[1] else ("B" if real[0] < real[1] else "N")
        pa, pb, pd = m["a"].win_prob or 0, m["b"].win_prob or 0, draw or 0
        po = "A" if (pa >= pb and pa >= pd) else ("B" if (pb >= pa and pb >= pd) else "N")
        if tuple(real) == tuple(pred):
            mark = '<span style="color:#16e0a3;font-weight:700;">✓</span> '
        elif po != ro:
            mark = '<span style="color:#e24b4a;font-weight:700;">×</span> '

    bottom = []
    if real is not None:
        bottom.append(f'<b style="color:#16e0a3;">R {real[0]}–{real[1]}</b>')
    if pred is not None:
        bottom.append(f'<span style="color:#ffffff;">P {pred[0]}–{pred[1]}</span>')
    if draw is not None:
        bottom.append(f'<span style="color:#9aa3c7;">nul {draw*100:.0f}%</span>')
    bottom_html = (f'<div style="text-align:center;font-size:0.66rem;margin-top:3px;">'
                   f'{mark}{" · ".join(bottom)}</div>') if bottom else ""
    bg, acc = STATUS_BG[_match_status(m["date"], m["played"])]
    return (
        f'<div style="background:{bg};border:1px solid #2a3358;'
        f'border-left:4px solid {acc};border-radius:8px;'
        'padding:5px 8px;box-sizing:border-box;margin:5px 0;">'
        f'<div style="font-size:0.66rem;line-height:1.2;color:#f78fb3;'
        f'margin-bottom:3px;white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis;">{when}</div>'
        f'{team_row(m["a"])}{team_row(m["b"])}{bottom_html}'
        '</div>'
    )


def render_group_fixtures(fixtures: dict[str, list[dict]]) -> None:
    if not fixtures:
        st.caption("Aucun match de poule à afficher.")
        return
    cards = []
    for code in DISPLAY_GROUPS:
        if code not in fixtures:
            continue
        boxes = "".join(_fixture_box(m) for m in fixtures[code])
        cards.append(
            '<div style="background:#0e1226;border:1px solid #2a3358;'
            'border-radius:8px;padding:8px 10px;">'
            f'<div style="font-weight:700;color:#f72585;margin-bottom:2px;'
            f'font-size:0.85rem;">Groupe {code}</div>{boxes}</div>'
        )
    grid = ('<div style="display:grid;gap:12px;'
            'grid-template-columns:repeat(auto-fit,minmax(300px,1fr));">'
            + "".join(cards) + '</div>')
    legend = (
        '<div style="margin-top:10px;color:#b8c0e0;font-size:0.76rem;">'
        '<b style="color:#16e0a3;">R</b> = score réel · '
        '<b>P</b> = score prédit · le % à côté de chaque équipe = proba de victoire · '
        '<b style="color:#16e0a3;">✓</b> score exact prédit · '
        '<b style="color:#e24b4a;">×</b> issue (V/N/D) mal prédite.<br>'
        'Prédictions des matchs <b>joués FIGÉES</b> (Elo d\'avant le match) ; celles '
        'des matchs à venir évoluent avec les résultats. Heures en <b>heure de Paris</b>.'
        '</div>'
    )
    st.markdown(grid + legend, unsafe_allow_html=True)


def _as_date(d):
    from datetime import date as _date
    if isinstance(d, _date):
        return d
    try:
        return _date.fromisoformat(str(d))
    except (ValueError, TypeError):
        return None


def _real_outcome(real) -> str:
    return "A" if real[0] > real[1] else ("B" if real[0] < real[1] else "N")


def _pred_outcome(m: dict) -> str:
    pa, pb, pd = m["a"].win_prob or 0, m["b"].win_prob or 0, m["draw"] or 0
    return "A" if (pa >= pb and pa >= pd) else ("B" if (pb >= pa and pb >= pd) else "N")


def _svg_donut(frac: float, label: str, sub: str, color: str) -> str:
    p = max(0.0, min(1.0, frac)) * 100
    return (
        '<div style="text-align:center;">'
        f'<svg width="130" height="130" viewBox="0 0 42 42" role="img" '
        f'aria-label="{label} : {p:.0f} %">'
        '<circle cx="21" cy="21" r="15.915" fill="none" stroke="#2a3358" '
        'stroke-width="6"/>'
        f'<circle cx="21" cy="21" r="15.915" fill="none" stroke="{color}" '
        f'stroke-width="6" stroke-dasharray="{p:.1f} {100 - p:.1f}" '
        'transform="rotate(-90 21 21)" stroke-linecap="round"/>'
        '<text x="21" y="21" text-anchor="middle" dominant-baseline="central" '
        f'font-size="8" font-weight="bold" fill="#000000">{p:.0f}%</text></svg>'
        f'<div style="color:#000000;font-size:0.9rem;font-weight:700;'
        f'margin-top:2px;">{label} — {p:.0f}%</div>'
        f'<div style="color:#333333;font-size:0.78rem;">{sub}</div></div>'
    )


def render_stats(fixtures: dict[str, list[dict]]) -> None:
    played = [m for ms in fixtures.values() for m in ms
              if m["played"] and m["real"] and m["pred"]]
    n = len(played)
    if n == 0:
        st.caption("Aucun match joué : statistiques indisponibles.")
        return
    res_ok = sum(1 for m in played if _pred_outcome(m) == _real_outcome(m["real"]))
    score_ok = sum(1 for m in played if tuple(m["real"]) == tuple(m["pred"]))

    # RPS moyen sur les prédictions PRÉ-MATCH figées (probas 3 issues).
    rps = evaluation.rps_mean(
        [[m["a"].win_prob or 0, m["draw"] or 0, m["b"].win_prob or 0] for m in played],
        [evaluation.outcome_index(*m["real"]) for m in played],
    )
    rps_card = (
        '<div style="text-align:center;min-width:120px;">'
        f'<div style="font-size:1.9rem;font-weight:800;color:#000000;'
        f'line-height:1.1;margin-top:6px;">{rps:.3f}</div>'
        '<div style="color:#000000;font-size:0.9rem;font-weight:700;">RPS moyen</div>'
        '<div style="color:#333333;font-size:0.78rem;">qualité des probabilités</div>'
        '</div>'
    )
    html = (
        '<div style="display:flex;gap:20px;justify-content:center;align-items:center;'
        'flex-wrap:wrap;padding:6px 0;">'
        + _svg_donut(res_ok / n, "Résultats bien prédits",
                     f"{res_ok}/{n} matchs (V/N/D)", "#16e0a3")
        + _svg_donut(score_ok / n, "Scores exacts bien prédits",
                     f"{score_ok}/{n} matchs", "#378add")
        + rps_card
        + '</div>'
    )
    explain = (
        '<div style="color:#000000;font-size:0.84rem;line-height:1.6;'
        'max-width:820px;margin:4px auto 0;">'
        '<b>Qu\'est-ce que le RPS (Ranked Probability Score) ?</b> Il mesure la '
        'qualité des <b>probabilités</b> prédites pour les 3 issues ordonnées '
        '(victoire / nul / défaite), pas seulement le résultat brut. '
        '<b>0 = prédiction parfaite</b> ; plus c\'est <b>bas</b>, mieux c\'est. '
        'Repères : un pronostic au hasard (1/3, 1/3, 1/3) vaut ≈ 0,22 ; un bon '
        'modèle de football international se situe autour de 0,18–0,20. '
        'Contrairement au « % de résultats bien prédits », le RPS récompense la '
        '<b>confiance bien placée</b> et pénalise les certitudes erronées. '
        '(Calculé sur les prédictions pré-match figées des matchs de poule joués.)'
        '<div style="text-align:center;font-family:var(--font-mono),monospace;'
        'background:#f1efe8;border:1px solid #d3d1c7;border-radius:6px;'
        'padding:10px 12px;margin:10px auto 6px;max-width:600px;font-size:0.95rem;">'
        'RPS = <sup>1</sup>⁄<sub>(r−1)</sub> · '
        '∑<sub>i=1</sub><sup>r−1</sup> ( ∑<sub>j=1</sub><sup>i</sup> '
        '(p<sub>j</sub> − e<sub>j</sub>) )²</div>'
        '<div style="font-size:0.8rem;">avec <b>r = 3</b> issues ordonnées '
        '(victoire / nul / défaite), <b>p<sub>j</sub></b> = probabilité prédite de '
        'l\'issue j, <b>e<sub>j</sub></b> = 1 si l\'issue j est réalisée, 0 sinon. '
        'Pour r = 3 : RPS = ½·[ (p<sub>1</sub>−e<sub>1</sub>)² + '
        '(p<sub>1</sub>+p<sub>2</sub>−e<sub>1</sub>−e<sub>2</sub>)² ]. '
        'Réf. : Epstein (1969) ; Constantinou &amp; Fenton (2012).<br>'
        'Cette formule donne le RPS d\'<b>un</b> match. Le chiffre affiché ci-dessus '
        'est le <b>RPS moyen</b> sur les <b>N</b> matchs de poule déjà joués : '
        '<b>RPS<sub>moyen</sub> = <sup>1</sup>⁄<sub>N</sub> · ∑<sub>matchs</sub> '
        'RPS(match)</b>.</div>'
        '</div>'
    )
    st.markdown(html + explain, unsafe_allow_html=True)


def _argmax3(probs) -> int:
    """Indice de l'issue la plus probable (0 = victoire A, 1 = nul, 2 = victoire B),
    même ordre que evaluation.outcome_index."""
    return max(range(3), key=lambda i: probs[i])


def _mecp_term(pred, real) -> float:
    """Somme des 3 carrés d'un match pour la MECP : (buts A), (buts B), (écart)."""
    pa, pb = pred
    ra, rb = real
    return (pa - ra) ** 2 + (pb - rb) ** 2 + ((pa - pb) - (ra - rb)) ** 2


def render_ko_stats(ko: list[dict]) -> None:
    """Précision des prévisions de la PHASE FINALE (matchs KO joués) : résultats bien
    prévus, RPS moyen, scores exacts, et MECP (erreur quadratique de score)."""
    n = len(ko)
    if n == 0:
        st.caption("Aucun match de phase finale joué : statistiques indisponibles.")
        return
    res_ok = sum(1 for m in ko
                 if _argmax3(m["probs"]) == evaluation.outcome_index(*m["real"]))
    score_ok = sum(1 for m in ko if tuple(m["pred"]) == tuple(m["real"]))
    rps = evaluation.rps_mean([list(m["probs"]) for m in ko],
                              [evaluation.outcome_index(*m["real"]) for m in ko])
    mecp = sum(_mecp_term(m["pred"], m["real"]) for m in ko) / n

    rps_card = (
        '<div style="text-align:center;min-width:120px;">'
        f'<div style="font-size:1.9rem;font-weight:800;color:#000000;'
        f'line-height:1.1;margin-top:6px;">{rps:.3f}</div>'
        '<div style="color:#000000;font-size:0.9rem;font-weight:700;">RPS moyen</div>'
        '<div style="color:#333333;font-size:0.78rem;">qualité des probabilités</div>'
        '</div>'
    )
    mecp_card = (
        '<div style="text-align:center;min-width:120px;">'
        f'<div style="font-size:1.9rem;font-weight:800;color:#000000;'
        f'line-height:1.1;margin-top:6px;">{mecp:.2f}</div>'
        '<div style="color:#000000;font-size:0.9rem;font-weight:700;">MECP</div>'
        '<div style="color:#333333;font-size:0.78rem;">erreur de score (0 = parfait)</div>'
        '</div>'
    )
    html = (
        '<div style="display:flex;gap:20px;justify-content:center;align-items:center;'
        'flex-wrap:wrap;padding:6px 0;">'
        + _svg_donut(res_ok / n, "Résultats bien prévus",
                     f"{res_ok}/{n} matchs (V/N/D)", "#16e0a3")
        + rps_card
        + _svg_donut(score_ok / n, "Scores exacts bien prédits",
                     f"{score_ok}/{n} matchs", "#378add")
        + mecp_card
        + '</div>'
    )
    explain = (
        '<div style="color:#000000;font-size:0.84rem;line-height:1.6;'
        'max-width:820px;margin:4px auto 0;">'
        '<b>MECP — Moyenne des Erreurs Carrées de Prévision.</b> Pour chaque match KO '
        'joué, on additionne trois carrés : (buts prévus A − buts réels A)², '
        '(buts prévus B − buts réels B)² et (écart prévu − écart réel)² ; la MECP est '
        'la <b>moyenne</b> de cette somme sur tous les matchs. '
        '<b>Plus c\'est proche de 0, meilleure est la prévision de score</b> ; plus '
        'c\'est élevé, moins bonne. Contrairement au « % de scores exacts » (tout ou '
        'rien), la MECP mesure <b>à quel point</b> on s\'est trompé et récompense les '
        'quasi-bons scores.'
        '<div style="text-align:center;font-family:var(--font-mono),monospace;'
        'background:#f1efe8;border:1px solid #d3d1c7;border-radius:6px;'
        'padding:10px 12px;margin:10px auto 6px;max-width:640px;font-size:0.95rem;">'
        'MECP = <sup>1</sup>⁄<sub>N</sub> · ∑<sub>matchs</sub> [ (p<sub>A</sub>−r'
        '<sub>A</sub>)² + (p<sub>B</sub>−r<sub>B</sub>)² + '
        '((p<sub>A</sub>−p<sub>B</sub>) − (r<sub>A</sub>−r<sub>B</sub>))² ]</div>'
        '<div style="font-size:0.8rem;">avec <b>p</b> = buts prévus, <b>r</b> = buts '
        'réels, A et B les deux équipes, N le nombre de matchs KO joués. '
        'Le <b>RPS</b> (voir phase de groupes) juge les <b>probabilités</b> d\'issue ; '
        'la <b>MECP</b> juge les <b>buts</b>. Les deux se mettent à jour à chaque '
        'nouveau résultat.</div>'
        '</div>'
    )
    st.markdown(html + explain, unsafe_allow_html=True)


def accessible_text(fixtures: dict[str, list[dict]], tree: dict | None = None) -> str:
    """Texte simple (lecteur d'écran) des prédictions des matchs NON joués :
    matchs de poule à venir PUIS matchs de la phase finale."""
    now = datetime.now().strftime("%d/%m/%Y à %H:%M")
    out = [
        "COUPE DU MONDE 2026 — PRÉDICTIONS DES MATCHS NON ENCORE JOUÉS",
        f"Document généré le {now}.",
        "Estimations Elo + modèle de buts. Matchs supposés en terrain neutre.",
        "Heures données en heure de Paris.",
        "",
        "=== PHASE DE GROUPES ===",
    ]
    any_match = False
    for code in DISPLAY_GROUPS:
        ups = [m for m in fixtures.get(code, []) if not m["played"]]
        if not ups:
            continue
        any_match = True
        out.append(f"Groupe {code} :")
        for m in ups:
            a, b = fr_name(m["a"].name), fr_name(m["b"].name)
            dd = _as_date(m["date"])
            when = date_fr(dd) if dd else "date à confirmer"
            if m["time"]:
                when += f" à {m['time']} heure de Paris"
            pa = round((m["a"].win_prob or 0) * 100)
            pb = round((m["b"].win_prob or 0) * 100)
            pd = round((m["draw"] or 0) * 100)
            ps = m["pred"]
            out.append(f"- {a} contre {b}, le {when}.")
            out.append(f"  Probabilités de victoire : {a} {pa} %, "
                       f"match nul {pd} %, {b} {pb} %.")
            if ps is not None:
                out.append(f"  Score le plus probable : {a} {ps[0]}, {b} {ps[1]}.")
        out.append("")
    if not any_match:
        out.append("Aucun match de poule à venir : la phase de groupes est terminée.")
        out.append("")

    # --- Phase finale (arbre) ---
    out.append("=== PHASE FINALE ===")
    any_ko = False
    if tree:
        for r, boxes in enumerate(tree["rounds"]):
            todo = [bx for bx in boxes if not (bx.a.is_winner or bx.b.is_winner)]
            if not todo:
                continue
            out.append(f"{tree['labels'][r]} :")
            for bx in todo:
                any_ko = True
                a = fr_name(bx.a.name) if bx.a.known else bx.a.name
                b = fr_name(bx.b.name) if bx.b.known else bx.b.name
                dd = _as_date(bx.date)
                when = date_fr(dd) if dd else "date à confirmer"
                out.append(f"- {a} contre {b}, le {when}.")
                if bx.both_known and bx.a.win_prob is not None:
                    pa = round(bx.a.win_prob * 100)
                    pb = round(bx.b.win_prob * 100)
                    out.append(f"  Qualification : {a} {pa} %, {b} {pb} %.")
                    if bx.score is not None:
                        out.append(f"  Score le plus probable : "
                                   f"{a} {bx.score[0]}, {b} {bx.score[1]}.")
                else:
                    out.append("  Adversaire(s) à déterminer.")
            out.append("")
    if not any_ko:
        out.append("Aucun match de phase finale à venir.")
    return "\n".join(out)


def guardrails() -> None:
    st.markdown(
        """
<div style="background:#3a0ca3;border-left:6px solid #f72585;border-radius:8px;
            padding:10px 16px;margin:2px 0 12px 0;color:#fff;font-size:0.9rem;">
<b>⚠️ Garde-fous</b> — Attention, ces pronostics ont été générés juste pour le
plaisir de coder, pas pour être utilisés pour faire des paris sportifs.<br>
Les jeux d'argent et de hasard peuvent être dangereux : pertes d'argent, conflits
familiaux, addiction… Nos conseils sur joueurs-info-service.fr
(09-74-75-13-13 - appel non surtaxé).<br>
<b>Comment lire les tableaux ?</b> Sur chaque ligne : la probabilité de se
qualifier et les buts les plus probables, via une couche « buts »
(λ = polynôme de l'Elo, Csató &amp; Gyimesi 2025) à deux lois de Poisson
indépendantes. Limites assumées : modèle de buts <b>étendu aux knockouts</b>
(usage au-delà des auteurs) ; Poisson indépendantes (sous-estime un peu les nuls
serrés, pas de Dixon-Coles) ; <b>λ borné [0.05, 6]</b> (régression peu fiable pour
les outsiders) ; terrain <b>neutre</b> par défaut ; tirs au but ≈ pile-ou-face.
Estimations, pas une vérité.
</div>
""",
        unsafe_allow_html=True,
    )


RESPONSIVE_CSS = """
<style>
/* Largeur max sur très grand écran + padding compact (surtout mobile). */
.block-container { max-width: 1500px; padding-top: 1.4rem;
                  padding-left: 1.2rem; padding-right: 1.2rem; }
@media (max-width: 640px) {
  .block-container { padding-left: 0.5rem; padding-right: 0.5rem; padding-top: 0.8rem; }
  h1 { font-size: 1.5rem !important; }
  h2 { font-size: 1.25rem !important; }
}
</style>
"""


def main() -> None:
    boot = bootstrap_refresh()   # rafraîchit tout (1×/lancement) avant l'affichage
    st.markdown(RESPONSIVE_CSS, unsafe_allow_html=True)

    st.title("🌎 Coupe du Monde de Football 2026 — Résultats et pronostics "
             "basés sur score Elo")
    guardrails()

    with st.sidebar:
        st.header("Réglages")
        if boot.get("as_of"):
            st.caption(f"✅ Données rafraîchies au lancement · Elo au {boot['as_of']}.")
        if boot.get("resolved"):
            st.caption(f"🪜 {boot['resolved']} places de groupe (1ers/2es) placées "
                       "automatiquement dans le tableau.")
        live = boot.get("live")
        if live:
            msg = (f"🔄 Source live ESPN : {live['filled']} match(s) récent(s) "
                   f"complété(s), {live['concord']} concordant(s) avec martj42")
            nd = len(live.get("discrepancies", []))
            msg += f", {nd} divergence(s)." if nd else ", 0 divergence."
            st.caption(msg)
            for diso, pair, mj, es in live.get("discrepancies", []):
                st.warning(f"Divergence {diso} {pair} : martj42 {mj} vs ESPN {es}")
        for w in boot.get("warnings", []):
            st.warning(w)
        home_adv = st.slider(
            "Avantage hôte (points Elo)", 0, 150, 0, step=5,
            help="0 = terrain neutre (défaut). ~100 = avantage à domicile "
                 "classique d'eloratings, appliqué quand une nation hôte "
                 "(★ USA/CAN/MEX) affronte une non-hôte.",
        )
        if st.button("🔄 Recharger les données", use_container_width=True,
                     type="primary"):
            bootstrap_refresh.clear()   # force un nouveau rafraîchissement complet
            st.rerun()
        st.caption(
            "Tout est rafraîchi à chaque lancement de l'app (dataset, Elo, bracket, "
            "groupes). Le bouton force un nouveau rafraîchissement immédiat."
        )

    try:
        tree = glue.load_tree(home_adv=float(home_adv))
    except Exception as exc:
        st.error(
            f"Impossible de charger l'arbre : {exc}\n\n"
            "Le rafraîchissement initial a échoué — recharge la page (bouton "
            "« Recharger les données ») ou vérifie l'accès réseau (dataset + ESPN)."
        )
        return

    n_known = sum(
        1 for boxes in tree["rounds"] for bx in boxes
        for p in (bx.a, bx.b) if p.known
    )
    st.markdown("## 🏆 Phase finale de la Coupe du Monde de football 2026")
    st.markdown(
        '<div style="font-size:1.05rem;font-weight:600;color:#1c1c1c;'
        'margin:2px 0 10px 0;">'
        f'31 matchs · {n_known} équipes déjà placées · avantage hôte = '
        f'{home_adv} pts Elo · ★ = nation hôte · ✓ = vainqueur connu.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(status_legend(), unsafe_allow_html=True)
    st.caption("↔ Faites glisser l'arbre horizontalement (souris/tactile) pour voir "
               "toutes les colonnes, y compris sur grand écran. "
               "Affiches, horaires (heure de Paris) et résultats sont alimentés "
               "automatiquement par les sources officielles (martj42 + ESPN) ; les "
               "8 meilleurs 3es sont placés d'après les affiches réelles dès "
               "qu'elles sont publiées. Le vainqueur de chaque match avance tout seul.")
    col_tree, col_list = st.columns([5, 1.2], gap="medium")
    with col_tree:
        render_tree(tree)
    with col_list:
        render_qualified(glue.teams_in_contention(),
                         _rank_changes_cached(boot.get("as_of")))

    st.markdown("### 📈 Précision des prévisions (phase éliminatoires)")
    st.caption("Sur les matchs de la phase finale déjà joués, prédiction pré-match "
               "figée vs résultat réel. Mis à jour à chaque nouveau résultat.")
    render_ko_stats(glue.knockout_predictions())

    st.markdown("### 📊 Phases de groupes")
    st.caption("Classements actualisés depuis les résultats des matchs de poule.")
    render_groups(glue.group_standings(only=DISPLAY_GROUPS))

    st.markdown("### ⚽ Matchs de poule — prédit (P) vs réel (R)")
    st.caption("Matchs joués (score réel R) puis à venir (heure de Paris), par groupe. "
               "Matchs supposés en terrain neutre.")
    st.markdown(status_legend(), unsafe_allow_html=True)
    fixtures = glue.group_fixtures(only=DISPLAY_GROUPS)
    render_group_fixtures(fixtures)

    st.markdown("### 📈 Précision des prédictions (matchs de poule joués)")
    render_stats(fixtures)

    st.markdown("### ♿ Accessibilité")
    st.caption("Fichier texte des prédictions des matchs non encore joués, "
               "lisible par un lecteur d'écran.")
    st.download_button(
        "⬇️ Télécharger les prédictions (texte accessible)",
        data=accessible_text(fixtures, tree),
        file_name="predictions_matchs_a_venir.txt",
        mime="text/plain",
    )


if __name__ == "__main__":
    main()
