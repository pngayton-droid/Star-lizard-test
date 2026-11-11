"""Conservative team matching within an exact StatsAPI competition ID."""
import re
import unicodedata

def normalize(value):
    raw=unicodedata.normalize("NFKD",str(value or "").casefold())
    raw="".join(ch for ch in raw if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+",raw))

def fixture_team(item,side):
    data=item.get(side+"_team") or {}
    return data.get("name","") if isinstance(data,dict) else str(data)

def venue_readiness(item,rows,min_venue=8,min_xg=8):
    comp=str(item.get("competition_id") or "")
    home=normalize(fixture_team(item,"home"))
    away=normalize(fixture_team(item,"away"))
    matches=[r for r in rows if str(r["competition_id"])==comp]
    def locate(name):
        candidates=[r for r in matches if normalize(r["team_name"])==name]
        return candidates[0] if len(candidates)==1 else None
    h=locate(home);a=locate(away)
    if not h or not a:
        return {"status":"Team name unresolved","home_games":0,"away_games":0,
                "home_xg":0,"away_xg":0}
    h_games=int(h["home_matches"]);a_games=int(a["away_matches"])
    hx=int(h["home_xg_matches"]);ax=int(a["away_xg_matches"])
    ready=h_games>=min_venue and a_games>=min_venue and hx>=min_xg and ax>=min_xg
    return {"status":"Venue xG sample ready" if ready else "Limited team/venue history",
            "home_games":h_games,"away_games":a_games,"home_xg":hx,"away_xg":ax}
