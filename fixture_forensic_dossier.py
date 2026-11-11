"""Fixture-level forensic data packet from observed venue summaries.

Does not invent referee, cards, corners, team form, or live match state.
"""
from datetime import date
from math import isfinite
from fixture_goals_baseline import find_venue

def venue_dossier(fixture,rows,as_of=None):
    """Return matched home/away xG summaries with provenance and sample warnings."""
    as_of=as_of or date.today()
    if isinstance(as_of,str):as_of=date.fromisoformat(as_of)
    output={"status":"unavailable","teams":{},"warnings":[]}
    for side in ("home","away"):
        item=find_venue(fixture,rows,side)
        if item is None:
            output["warnings"].append(f"{side.title()} venue summary unavailable or ambiguous")
            continue
        try:
            n=int(item["sample_n"])
            latest=date.fromisoformat(str(item["last_match_date"])[:10])
            xg_for=float(item["xg_for_avg"])
            xg_against=float(item["xg_against_avg"])
            if n<0 or not all(isfinite(v) and 0<=v<=8 for v in (xg_for,xg_against)):
                raise ValueError("invalid sample or xG")
        except (KeyError,ValueError,TypeError):
            output["warnings"].append(f"{side.title()} venue summary contains invalid data")
            continue
        days=(as_of-latest).days
        output["teams"][side]={
            "team":str(item["team_name"]),"venue":side,"matches":n,
            "xg_for":xg_for,
            "xg_against":xg_against,
            "xg_difference":xg_for-xg_against,
            "latest":latest.isoformat(),"days_since_latest":days}
        if n<8:output["warnings"].append(f"{side.title()} venue sample below eight matches")
        if days>90:output["warnings"].append(f"{side.title()} venue summary last updated over 90 days ago")
        if days<0:output["warnings"].append(f"{side.title()} venue data includes a future match date")
    if len(output["teams"])==2:
        output["status"]="ready" if not output["warnings"] else "caution"
    return output
