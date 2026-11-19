"""Chronological Match Matrix card totals against saved Bet365 prices.\nAll fixtures included; red cards provisionally count as two additional cards.\nNot exact Bet365 settlement: second-yellow dismissals and recipient eligibility unknown.\n"""
import os,ast
import numpy as np,pandas as pd
from supabase import create_client
from collections import defaultdict,deque
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
 out=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(cols).range(start,start+999).execute().data or []
  out.extend(batch)
  if len(batch)<1000:break
 return out
def import_functions(path,names):
 tree=ast.parse(open(path,encoding="utf-8").read())
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 for n in nodes:n.decorator_list=[]
 exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),path,"exec"),globals())
import_functions("pages/Similarity_Pricing.py",{"season","features","analogues","opponent_adjusted_xg"})
import_functions("scripts/test_shots_similarity.py",{"load","match_corners_cards"})
data=features()
quotes={}
for rec in fetch("historical_match_odds","match_id,odds_payload"):
 for b in (((rec.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []):
  if b.get("bookmaker")=="Bet365":
   quotes[rec["match_id"]]=(b.get("markets") or {}).get("match_odds") or {}
   break

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
eligible=data[(data.date>=pd.Timestamp("2021-01-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.match_id.isin(quotes)].sort_values(["date","match_id"])
rows=[]
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="combined").head(250)
 if len(sample)<50:continue
 try:
  prices=np.array([float((quotes[r.match_id].get(side) or {}).get("last_seen")) for side in ("home","draw","away")])
 except (ValueError,TypeError,AttributeError):continue
 if not np.all(np.isfinite(prices)) or np.any((prices<1.2)|(prices>20)):continue
 raw=np.array([(sample.hg>sample.ag).mean(),(sample.hg==sample.ag).mean(),(sample.hg<sample.ag).mean()])
 raw=np.clip(raw,0.005,0.995);raw=raw/raw.sum()
 book=(1/prices);book=book/book.sum()
 actual=0 if r.hg>r.ag else (1 if r.hg==r.ag else 2)
 rows.append(dict(match_id=r.match_id,year=int(r.date.year),actual=actual,**{f"raw_{j}":raw[j] for j in range(3)},**{f"book_{j}":book[j] for j in range(3)},**{f"price_{j}":prices[j] for j in range(3)}))
 if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
df=pd.DataFrame(rows)
if df.empty:raise RuntimeError("No eligible full-market forecasts")
os.makedirs("research_results",exist_ok=True)
df.to_csv("research_results/match_odds_calibration_forecasts.csv",index=False)
train=df[df.year<=2024].copy()
test=df[df.year>=2025].copy()
if len(train)<1000 or len(test)<100:raise RuntimeError("Insufficient chronological training/test data")
def matrix(frame,prefix):return frame[[f"{prefix}_{j}" for j in range(3)]].to_numpy(dtype=float)
# Model-only multinomial calibration; does NOT use bookmaker odds to train.
# Bookmaker implied prices are used strictly as a comparator and for EV selection.
def features(frame):return np.log(np.clip(matrix(frame,"raw"),0.005,1))
cal=LogisticRegression(C=0.05,max_iter=1000)
cal.fit(features(train),train.actual)
def calibrate(frame):return cal.predict_proba(features(frame))
def evaluate(frame,split):
 truth=frame.actual.to_numpy(dtype=int)
 odds=matrix(frame,"price")
 for label,prob in [("raw",matrix(frame,"raw")),("calibrated",calibrate(frame)),("bookmaker",matrix(frame,"book"))]:
  brier=np.mean(np.sum((prob-np.eye(3)[truth])**2,axis=1))/3
  ll=log_loss(truth,prob,labels=[0,1,2])
  picks=[]
  if label!="bookmaker":
   for i in range(len(frame)):
    ev=prob[i]*odds[i]-1
    j=int(np.argmax(ev))
    if ev[j]>=0.05:
     picks.append((odds[i,j]-1 if truth[i]==j else -1,j,odds[i,j],ev[j]))
  for band in ("all","below_3","3_to_6","6_plus"):
   chosen=[x for x in picks if band=="all" or (band=="below_3" and x[2]<3) or (band=="3_to_6" and 3<=x[2]<6) or (band=="6_plus" and x[2]>=6)]
   yield dict(split=split,model=label,band=band,fixtures=len(frame),brier=brier,log_loss=ll,bets=len(chosen),roi=float(np.mean([x[0] for x in chosen])) if chosen else np.nan,units=float(np.sum([x[0] for x in chosen])),predicted_roi=float(np.mean([x[3] for x in chosen])) if chosen else np.nan)
result=[]
for split,frame in [("training_2021_2024",train),("validation_2025",test[test.year==2025]),("validation_2026",test[test.year==2026]),("validation_2025_2026",test)]:
 if len(frame):result.extend(evaluate(frame,split))
out=pd.DataFrame(result)
out.to_csv("research_results/match_odds_calibration_summary.csv",index=False)
print("TRAIN",len(train),"TEST",len(test),flush=True)
print(out.to_string(index=False),flush=True)
