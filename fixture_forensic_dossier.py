"""Fixture-level forensic data packet from observed venue summaries.

Does not invent referee, cards, corners, team form, or live match state.
"""
from datetime import date
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
        n=int(item["sample_n"])
        latest=date.fromisoformat(str(item["last_match_date"])[:10])
        days=(as_of-latest).days
        output["teams"][side]={
            "team":str(item["team_name"]),"venue":side,"matches":n,
            "xg_for":float(item["xg_for_avg"]),
            "xg_against":float(item["xg_against_avg"]),
            "xg_difference":float(item["xg_for_avg"])-float(item["xg_against_avg"]),
            "latest":latest.isoformat(),"days_since_latest":days}
        if n<8:output["warnings"].append(f"{side.title()} venue sample below eight matches")
        if days>90:output["warnings"].append(f"{side.title()} venue summary last updated over 90 days ago")
        if days<0:output["warnings"].append(f"{side.title()} venue data includes a future match date")
    if len(output["teams"])==2:
        output["status"]="ready" if not output["warnings"] else "caution"
    return output
