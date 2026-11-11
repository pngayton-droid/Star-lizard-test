"""Conservative historical-league coverage matching for live fixtures.

Only explicit league-name aliases qualify; never infer from country alone.
Source counts are historical, not a guarantee of team-level readiness.
"""
import pandas as pd

ALIASES={
"E0":("premier league","english premier league"),
"E1":("championship","efl championship"),
"SP1":("la liga","laliga","primera division","primera división"),
"I1":("serie a","italian serie a"),
"D1":("bundesliga","german bundesliga"),
"F1":("ligue 1","ligue 1 mcdonald"),
"N1":("eredivisie",),
"B1":("jupiler pro league","belgian pro league","first division a"),
"P1":("primeira liga","liga portugal","liga portugal betclic"),
"SC0":("scottish premiership","scottish premier league"),
"T1":("super lig","süper lig","turkish super league"),
"G1":("super league greece","greek super league"),
}
# Explicit disambiguation: "Serie A" alone can refer to Brazil, too.
COUNTRY_HINT={
"E0":"england","E1":"england","SP1":"spain","I1":"italy",
"D1":"germany","F1":"france","N1":"netherlands","B1":"belgium",
"P1":"portugal","SC0":"scotland","T1":"turkey","G1":"greece",
}
def _name(value):
    return " ".join(str(value or "").casefold().replace("-"," ").split())

def match_league(competition,country=None):
    name=_name(competition)
    nation=_name(country)
    if not name: return None
    for code,names in ALIASES.items():
        if name not in tuple(_name(x) for x in names):
            continue
        # Ambiguous competition titles require country context to avoid false matches.
        if code in ("I1","D1","E0","G1") and not nation:
            return None
        if nation and COUNTRY_HINT[code] not in nation:
            return None
        return code
    return None

def archive_league_summary(coverage):
    if coverage.empty:
        return pd.DataFrame(columns=["league","matches","corners","yellow_cards","b365_odds"])
    df=coverage[coverage.source.eq("Football-data")].copy()
    if df.empty:
        return pd.DataFrame(columns=["league","matches","corners","yellow_cards","b365_odds"])
    for column in ("matches","corners","yellow_cards","b365_odds"):
        df[column]=pd.to_numeric(df[column],errors="coerce").fillna(0)
    return df.groupby("league",as_index=False)[["matches","corners","yellow_cards","b365_odds"]].sum()

def classify_fixture(item,summary,min_matches=500):
    comp=item.get("competition") or {}
    country=None
    if isinstance(comp,dict):
        name=comp.get("name")
        country=comp.get("country") or comp.get("country_name")
        if isinstance(country,dict):
            country=country.get("name")
    else:
        name=str(comp)
    country=country or item.get("country") or item.get("country_name")
    if isinstance(country,dict):
        country=country.get("name")
    code=match_league(name,country)
    if not code:
        return {"status":"Unmatched","league_code":None,"historical_matches":0,
                "reason":"Competition identity not confidently matched"}
    rows=summary[summary.league.eq(code)]
    n=int(rows.matches.iloc[0]) if not rows.empty else 0
    if n<min_matches:
        return {"status":"Limited history","league_code":code,"historical_matches":n,
                "reason":"Below historical match threshold"}
    return {"status":"League covered","league_code":code,"historical_matches":n,
            "reason":"League archive meets threshold; team and market readiness unverified"}
