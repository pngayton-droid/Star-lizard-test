"""Transparent Poisson goals research baseline, not calibrated fair odds."""
from math import exp, factorial, isfinite
from fixture_team_readiness import normalize, fixture_team

def find_venue(item,rows,side):
    competition=str(item.get("competition_id") or "")
    name=normalize(fixture_team(item,side))
    venue="home" if side=="home" else "away"
    found=[r for r in rows if str(r["competition_id"])==competition and
           r["venue"]==venue and normalize(r["team_name"])==name]
    return found[0] if len(found)==1 else None

def baseline(item,rows):
    home=find_venue(item,rows,"home")
    away=find_venue(item,rows,"away")
    if not home or not away:return None
    if min(int(home["sample_n"]),int(away["sample_n"]))<8:return None
    try:
        values=[float(home["xg_for_avg"]),float(away["xg_against_avg"]),
                float(away["xg_for_avg"]),float(home["xg_against_avg"])]
    except (KeyError,ValueError,TypeError):
        return None
    if not all(isfinite(v) and 0<=v<=8 for v in values):return None
    home_mu=(values[0]+values[1])/2
    away_mu=(values[2]+values[3])/2
    total=home_mu+away_mu
    under25=sum(exp(-total)*total**k/factorial(k) for k in range(3))
    under15=sum(exp(-total)*total**k/factorial(k) for k in range(2))
    return {"home_xg":home_mu,"away_xg":away_mu,"total_xg":total,
            "over_1_5":1-under15,"over_2_5":1-under25,
            "home_n":int(home["sample_n"]),"away_n":int(away["sample_n"]),
            "home_last":str(home["last_match_date"]),"away_last":str(away["last_match_date"])}
