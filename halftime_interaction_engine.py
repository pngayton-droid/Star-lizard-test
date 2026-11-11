"""Chronological, exploratory halftime interaction scanner.

No fixture-level fair odds and no betting value inference. Screening on the
training period only; holdout estimates are descriptive, not independent after
repeated model development.
"""
from math import sqrt
import pandas as pd
from halftime_state_scanner import scan_halftime_states

OUTCOMES={
    "2H at least one goal":"second_half_goal",
    "2H at least two goals":"second_half_over15",
    "2H at least three goals":"second_half_over25",
    "Home scores 2H":"home_scored",
    "Away scores 2H":"away_scored",
    "Home wins 2H":"home_won_2h",
    "Away wins 2H":"away_won_2h",
    "2H draw":"second_half_draw",
    "Both teams score 2H":"btts_2h",
}
def _frame(rows):
    records=[]
    for r in rows:
        h,a=int(r["home_ht_goals"]),int(r["away_ht_goals"])
        hx,ax=float(r["home_ht_xg"]),float(r["away_ht_xg"])
        sh,sa=int(r["home_second_half_goals"]),int(r["away_second_half_goals"])
        records.append({
            "date":str(r["match_date"]),
            "score":f"{h}-{a}" if max(h,a)<=4 else "5+ score",
            "state":"Draw" if h==a else ("Home leading" if h>a else "Away leading"),
            "xg_leader":"Level" if abs(hx-ax)<0.001 else ("Home" if hx>ax else "Away"),
            "ht_total_xg":"Under 0.5" if hx+ax<0.5 else ("0.5–1.49" if hx+ax<1.5 else "1.5+"),
            "home_ht_xg":"Under 0.2" if hx<0.2 else ("0.2–0.79" if hx<0.8 else "0.8+"),
            "away_ht_xg":"Under 0.2" if ax<0.2 else ("0.2–0.79" if ax<0.8 else "0.8+"),
            "second_half_goal":int(sh+sa>=1),
            "second_half_over15":int(sh+sa>=2),
            "second_half_over25":int(sh+sa>=3),
            "home_scored":int(sh>0),"away_scored":int(sa>0),
            "home_won_2h":int(sh>sa),"away_won_2h":int(sa>sh),
            "second_half_draw":int(sh==sa),"btts_2h":int(sh>0 and sa>0),
        })
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)

def scan_interactions(rows,minimum=100,train_fraction=0.7):
    frame=_frame(rows)
    if len(frame)<minimum*3:return pd.DataFrame()
    # Keep all matches on the same calendar date in the same partition.
    dates=sorted(frame.date.unique())
    cut=dates[max(1,min(len(dates)-1,int(len(dates)*train_fraction)))]
    train=frame[frame.date<cut]
    test=frame[frame.date>=cut]
    dimensions=["score","state","xg_leader","ht_total_xg","home_ht_xg","away_ht_xg"]
    output=[]
    for i,left in enumerate(dimensions):
        for right in dimensions[i+1:]:
            for (lv,rv),tr in train.groupby([left,right]):
                if len(tr)<minimum:continue
                te=test[(test[left]==lv)&(test[right]==rv)]
                if len(te)<max(30,minimum//3):continue
                for name,target in OUTCOMES.items():
                    base=float(train[target].mean())
                    tr_rate=float(tr[target].mean())
                    te_rate=float(te[target].mean())
                    # Rank by training deviation only; do not optimize on holdout.
                    output.append({"filters":f"{left}={lv}; {right}={rv}",
                        "market":name,"train_n":len(tr),"later_n":len(te),
                        "train_rate_pct":round(100*tr_rate,1),
                        "later_rate_pct":round(100*te_rate,1),
                        "training_lift_pp":round(100*(tr_rate-base),1),
                        "later_start":cut})
    if not output:return pd.DataFrame()
    return pd.DataFrame(output).sort_values(
        ["training_lift_pp","train_n"],ascending=[False,False]).reset_index(drop=True)
