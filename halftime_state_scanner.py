"""Historical halftime state scanner; exhaustive score states, descriptive only."""
import pandas as pd

def scan_halftime_states(rows,min_n=80):
    records=[]
    for r in rows:
        h=int(r["home_ht_goals"]); a=int(r["away_ht_goals"])
        hx=float(r["home_ht_xg"]); ax=float(r["away_ht_xg"])
        sh=int(r["home_second_half_goals"]);sa=int(r["away_second_half_goals"])
        total=sh+sa
        records.append({
            "score":f"{h}-{a}" if max(h,a)<=4 else "5+ score",
            "state":"Draw" if h==a else ("Home leading" if h>a else "Away leading"),
            "xg_leader":"Level" if abs(hx-ax)<0.001 else ("Home" if hx>ax else "Away"),
            "ht_total_xg":"Under 0.5" if hx+ax<0.5 else ("0.5–1.49" if hx+ax<1.5 else "1.5+"),
            "home_ht_xg":"Under 0.2" if hx<0.2 else ("0.2–0.79" if hx<0.8 else "0.8+"),
            "away_ht_xg":"Under 0.2" if ax<0.2 else ("0.2–0.79" if ax<0.8 else "0.8+"),
            "second_half_goal":int(total>0),"second_half_over15":int(total>=2),
            "second_half_over25":int(total>=3),"home_scored":int(sh>0),
            "away_scored":int(sa>0),"home_won_2h":int(sh>sa),
            "away_won_2h":int(sa>sh),"second_half_draw":int(sh==sa),
            "btts_2h":int(sh>0 and sa>0),
        })
    frame=pd.DataFrame.from_records(records)
    if frame.empty:return pd.DataFrame()
    metrics=["second_half_goal","second_half_over15","second_half_over25",
             "home_scored","away_scored","home_won_2h","away_won_2h",
             "second_half_draw","btts_2h"]
    outputs=[]
    for dimension in ["state","score","xg_leader","ht_total_xg","home_ht_xg","away_ht_xg"]:
        for value,subset in frame.groupby(dimension):
            if len(subset)<min_n:continue
            record={"dimension":dimension,"segment":value,"matches":len(subset)}
            record.update({name:round(float(subset[name].mean())*100,1) for name in metrics})
            outputs.append(record)
    return pd.DataFrame(outputs).sort_values(["dimension","matches"],ascending=[True,False])
