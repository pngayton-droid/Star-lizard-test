"""Paired audit of post-hoc probability coherence on frozen walk-forward predictions.
No model fitting; no future data used; evaluates retrospective holdout only.
"""
import pandas as pd,numpy as np
from pathlib import Path
src=Path("research_results/ht_second_half_fair_odds_predictions.csv")
df=pd.read_csv(src,dtype={"selection":str})
df=df[df.split=="holdout_2000"].copy()
if df.match_id.nunique()!=2000:raise RuntimeError("Expected exactly 2,000 retrospective holdout fixtures")
required=["next_goal","second_half_result","over_0_5_2h","over_1_5_2h","over_2_5_2h","home_scores_2h","away_scores_2h","both_score_2h"]
out=[];violations={k:0 for k in ["totals_order","none_goal","both_score","union","scoreless_draw"]}
for mid,g in df.groupby("match_id",sort=False):
 p={m:{str(r.selection):float(r.probability) for r in grp.itertuples()} for m,grp in g.groupby("market")}
 y={m:str(grp.loc[grp.won==1,"selection"].iloc[0]) for m,grp in g.groupby("market")}
 if any(m not in p for m in required):raise RuntimeError("Missing target "+str(mid))
 raw={k:dict(v) for k,v in p.items()}
 o05=p["over_0_5_2h"]["1"];o15=p["over_1_5_2h"]["1"];o25=p["over_2_5_2h"]["1"]
 h=p["home_scores_2h"]["1"];a=p["away_scores_2h"]["1"];both=p["both_score_2h"]["1"]
 violations["totals_order"]+=int(o05+1e-9<o15 or o15+1e-9<o25)
 violations["none_goal"]+=int(abs(p["next_goal"]["none"]-(1-o05))>1e-6)
 violations["both_score"]+=int(both>min(h,a,o15)+1e-9)
 violations["union"]+=int(h+a-both>o05+1e-9)
 violations["scoreless_draw"]+=int(p["second_half_result"]["draw"]+1e-9<1-o05)
 o15=min(o15,o05);o25=min(o25,o15)
 for k,v in [("over_0_5_2h",o05),("over_1_5_2h",o15),("over_2_5_2h",o25)]:p[k]={"1":v,"0":1-v}
 n=p["next_goal"];hs=n["home"]/max(n["home"]+n["away"],1e-12)
 p["next_goal"]={"home":o05*hs,"away":o05*(1-hs),"none":1-o05}
 both=min(both,h,a,o15);p["both_score_2h"]={"1":both,"0":1-both}
 excess=max(0.,h+a-both-o05)
 if excess:
  rh=max(0.,h-both);ra=max(0.,a-both)
  th=min(rh,excess*rh/max(rh+ra,1e-12))
  h-=th;a-=min(ra,excess-th)
 p["home_scores_2h"]={"1":h,"0":1-h};p["away_scores_2h"]={"1":a,"0":1-a}
 d=p["second_half_result"]["draw"]
 if d<1-o05:
  other=p["second_half_result"]["home"]+p["second_half_result"]["away"]
  fac=o05/max(other,1e-12)
  p["second_half_result"]={"home":p["second_half_result"]["home"]*fac,
                           "away":p["second_half_result"]["away"]*fac,"draw":1-o05}
 for m in required:
  out.append({"match_id":mid,"market":m,"original_logloss":-np.log(max(raw[m][y[m]],1e-12)),
              "adjusted_logloss":-np.log(max(p[m][y[m]],1e-12)),
              "changed":int(any(abs(raw[m][k]-p[m][k])>1e-8 for k in raw[m]))})
result=pd.DataFrame(out)
summary=result.groupby("market").agg(matches=("match_id","nunique"),original_logloss=("original_logloss","mean"),adjusted_logloss=("adjusted_logloss","mean"),changed_matches=("changed","sum")).reset_index()
summary["delta_adjusted_minus_original"]=summary.adjusted_logloss-summary.original_logloss
summary.loc[len(summary)]={"market":"EQUAL_WEIGHT_ALL_EIGHT","matches":2000,
 "original_logloss":result.original_logloss.mean(),"adjusted_logloss":result.adjusted_logloss.mean(),
 "changed_matches":result.changed.sum(),"delta_adjusted_minus_original":(result.adjusted_logloss-result.original_logloss).mean()}
Path("research_results").mkdir(exist_ok=True)
summary.to_csv("research_results/probability_consistency_audit.csv",index=False)
pd.DataFrame([{"check":k,"violating_matches":v,"matches":2000} for k,v in violations.items()]).to_csv("research_results/probability_consistency_violations.csv",index=False)
print(summary.to_string(index=False));print("Original violations:",violations)
print("Positive delta means coherence made log loss WORSE.")
