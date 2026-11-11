"""Pure point-in-time venue summary guard for historical fixture research.

A latest-observation check detects known leakage but cannot establish whether
the entire aggregate was computed only from pre-kickoff records.
"""
from datetime import date
from math import isfinite
from fixture_goals_baseline import find_venue

def baseline_input_audit(fixture, rows, fixture_date):
    target=date.fromisoformat(str(fixture_date)[:10])
    sources={}
    warnings=[]
    for side in ("home","away"):
        row=find_venue(fixture,rows,side)
        if row is None:
            warnings.append(f"{side}: venue data missing or ambiguous")
            continue
        try:
            latest=date.fromisoformat(str(row["last_match_date"])[:10])
            n=int(row["sample_n"])
            xg_for=float(row["xg_for_avg"])
            xg_against=float(row["xg_against_avg"])
            if not (isfinite(xg_for) and isfinite(xg_against) and
                    0<=xg_for<=8 and 0<=xg_against<=8):
                raise ValueError("Invalid venue xG")
        except (KeyError,ValueError,TypeError):
            warnings.append(f"{side}: malformed venue provenance")
            continue
        sources[side]={"latest":latest.isoformat(),"sample_n":n,
                       "known_future_observations":latest>=target}
        if latest>=target:
            warnings.append(f"{side}: latest venue observation is on or after fixture date")
        if n<8:warnings.append(f"{side}: fewer than eight venue samples")
    return {"eligible_for_current_pricing":len(sources)==2 and
                all(not s["known_future_observations"] and s["sample_n"]>=8 for s in sources.values()),
            "point_in_time_verified":False,
            "sources":sources,"warnings":warnings}
