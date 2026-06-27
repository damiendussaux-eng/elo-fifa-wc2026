"""
Référentiel pays : nom (tel qu'écrit dans le dataset martj42) -> code ISO-3166-1
alpha-2. Le drapeau emoji est dérivé du code ISO (indicateurs régionaux unicode),
donc pas besoin de stocker chaque emoji à la main.

Couverture : hôtes + nations susceptibles de jouer la WC2026 + grandes nations.
Un nom absent renvoie (None, None) : team_id est créé sans drapeau, l'UI affiche
un placeholder. Compléter au fur et à mesure que les qualifiés se confirment.
"""
from __future__ import annotations

# Nom dataset -> ISO2
NAME_TO_ISO2: dict[str, str] = {
    # Hôtes
    "United States": "US", "Canada": "CA", "Mexico": "MX",
    # UEFA
    "France": "FR", "England": "GB", "Spain": "ES", "Germany": "DE",
    "Portugal": "PT", "Italy": "IT", "Netherlands": "NL", "Belgium": "BE",
    "Croatia": "HR", "Denmark": "DK", "Switzerland": "CH", "Austria": "AT",
    "Poland": "PL", "Ukraine": "UA", "Serbia": "RS", "Sweden": "SE",
    "Wales": "GB", "Scotland": "GB", "Norway": "NO", "Czech Republic": "CZ",
    "Czechia": "CZ", "Turkey": "TR", "Türkiye": "TR", "Greece": "GR",
    "Hungary": "HU", "Romania": "RO", "Republic of Ireland": "IE",
    "Slovakia": "SK", "Slovenia": "SI", "Albania": "AL", "Finland": "FI",
    "Bosnia and Herzegovina": "BA", "Iceland": "IS", "North Macedonia": "MK",
    "Russia": "RU",
    # CONMEBOL
    "Brazil": "BR", "Argentina": "AR", "Uruguay": "UY", "Colombia": "CO",
    "Chile": "CL", "Peru": "PE", "Ecuador": "EC", "Paraguay": "PY",
    "Venezuela": "VE", "Bolivia": "BO",
    # CONCACAF
    "Costa Rica": "CR", "Panama": "PA", "Jamaica": "JM", "Honduras": "HN",
    "El Salvador": "SV", "Guatemala": "GT", "Haiti": "HT",
    "Trinidad and Tobago": "TT", "Curaçao": "CW", "Curacao": "CW",
    # CONMEBOL/CONCACAF misc
    "Suriname": "SR",
    # CAF
    "Morocco": "MA", "Senegal": "SN", "Tunisia": "TN", "Algeria": "DZ",
    "Egypt": "EG", "Nigeria": "NG", "Cameroon": "CM", "Ghana": "GH",
    "Ivory Coast": "CI", "Côte d'Ivoire": "CI", "Mali": "ML",
    "Burkina Faso": "BF", "South Africa": "ZA", "DR Congo": "CD",
    "Congo DR": "CD", "Cape Verde": "CV", "Cabo Verde": "CV",
    "Guinea": "GN", "Zambia": "ZM", "Angola": "AO", "Gabon": "GA",
    "Equatorial Guinea": "GQ", "Uganda": "UG", "Benin": "BJ",
    "Tanzania": "TZ", "Mauritania": "MR", "Mozambique": "MZ",
    # AFC
    "Japan": "JP", "South Korea": "KR", "Korea Republic": "KR",
    "Iran": "IR", "IR Iran": "IR", "Australia": "AU", "Saudi Arabia": "SA",
    "Qatar": "QA", "Iraq": "IQ", "United Arab Emirates": "AE",
    "Uzbekistan": "UZ", "Jordan": "JO", "Oman": "OM", "China PR": "CN",
    "China": "CN", "Bahrain": "BH", "Kuwait": "KW", "Vietnam": "VN",
    "Thailand": "TH", "Indonesia": "ID", "India": "IN", "Palestine": "PS",
    "North Korea": "KP", "Korea DPR": "KP", "Syria": "SY", "Lebanon": "LB",
    # OFC
    "New Zealand": "NZ", "New Caledonia": "NC", "Fiji": "FJ",
    "Solomon Islands": "SB", "Tahiti": "PF", "Vanuatu": "VU",
    "Papua New Guinea": "PG",
}

# Cas où le drapeau emoji par indicateurs régionaux n'existe pas (sous-nations
# du Royaume-Uni) : emoji « tag sequence » dédié.
SPECIAL_FLAGS: dict[str, str] = {
    "England": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "Scotland": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
    "Wales": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
}


def iso2_to_flag(iso2: str) -> str:
    """Convertit un code alpha-2 en drapeau emoji (indicateurs régionaux)."""
    iso2 = iso2.upper()
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in iso2)


def meta_for(name: str) -> tuple[str | None, str | None]:
    """Retourne (iso2, flag_emoji) pour un nom d'équipe, ou (None, None)."""
    if name in SPECIAL_FLAGS:
        return NAME_TO_ISO2.get(name), SPECIAL_FLAGS[name]
    iso2 = NAME_TO_ISO2.get(name)
    if iso2 is None:
        return None, None
    return iso2, iso2_to_flag(iso2)


# Traduction des noms (anglais du dataset -> français) pour l'AFFICHAGE seulement.
# La logique interne (clés teams.name, drapeaux, jointures) reste en anglais.
FR_NAMES: dict[str, str] = {
    "Mexico": "Mexique", "South Africa": "Afrique du Sud",
    "South Korea": "Corée du Sud", "Czech Republic": "Tchéquie",
    "Canada": "Canada", "Bosnia and Herzegovina": "Bosnie-Herzégovine",
    "Qatar": "Qatar", "Switzerland": "Suisse",
    "Brazil": "Brésil", "Morocco": "Maroc", "Haiti": "Haïti", "Scotland": "Écosse",
    "United States": "États-Unis", "Paraguay": "Paraguay",
    "Australia": "Australie", "Turkey": "Turquie",
    "Germany": "Allemagne", "Curaçao": "Curaçao", "Ivory Coast": "Côte d'Ivoire",
    "Ecuador": "Équateur", "Netherlands": "Pays-Bas", "Japan": "Japon",
    "Sweden": "Suède", "Tunisia": "Tunisie", "Belgium": "Belgique",
    "Egypt": "Égypte", "Iran": "Iran", "New Zealand": "Nouvelle-Zélande",
    "Spain": "Espagne", "Cape Verde": "Cap-Vert", "Saudi Arabia": "Arabie saoudite",
    "Uruguay": "Uruguay", "France": "France", "Senegal": "Sénégal",
    "Iraq": "Irak", "Norway": "Norvège", "Argentina": "Argentine",
    "Algeria": "Algérie", "Austria": "Autriche", "Jordan": "Jordanie",
    "Portugal": "Portugal", "DR Congo": "RD Congo", "Uzbekistan": "Ouzbékistan",
    "Colombia": "Colombie", "England": "Angleterre", "Croatia": "Croatie",
    "Ghana": "Ghana", "Panama": "Panama",
    # autres grandes nations (au cas où elles apparaîtraient)
    "Italy": "Italie", "Poland": "Pologne", "Denmark": "Danemark",
    "Nigeria": "Nigéria", "Cameroon": "Cameroun", "Serbia": "Serbie",
}


def fr_name(name: str) -> str:
    """Nom français pour l'affichage ; renvoie tel quel si inconnu (libellés TBD)."""
    return FR_NAMES.get(name, name)
