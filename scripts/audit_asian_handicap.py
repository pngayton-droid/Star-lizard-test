"""Chronological Asian match handicap audit. Saved StatsAPI only; no bookmaker prices assumed."""
import os,ast,math
import numpy as np,pandas as pd
from supabase import create_client
from collections import defaultdict,deque
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
 out=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(cols).range(start,start+999).execute().data or []
  out+=batch
  if len(batch)<1000:break
 return out
source=open("pages/Similarity_Pricing.py",encoding="utf-8").read()
tree=ast.parse(source)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features","analogues","opponent_adjusted_xg"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())
extra=open("scripts/test_shots_similarity.py",encoding="utf-8").read()
ex=ast.parse(extra)
helpers=[n for n in ex.body if isinstance(n,ast.FunctionDef) and n.name in {"load","match_corners_cards"}]
exec(compile(ast.fix_missing_locations(ast.Module(body=helpers,type_ignores=[])),"helpers","exec"),globals())
def split(line):
 return [line] if int(round(line*4))%2==0 else [math.floor(line*2)/2,math.ceil(line*2)/2]
def units(goal_diff,line):
 w=l=p=0.
 for part in split(line):
  delta=goal_diff+part
  if delta>0:w+=1/len(split(line))
  elif delta<0:l+=1/len(split(line))
  else:p+=1/len(split(line))
 return w,l,p
def fair(sample,line):
 outcomes=np.array([units(float(x),line) for x in sample],float).mean(axis=0)
 w,l,p=outcomes
 return (1+l/w if w else np.nan),w,l,p
print("LOADING",flush=True)
data=features()
eligible=data[(data.date>=pd.Timestamp("2025-07-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()].sort_values(["date","match_id"])
selected=eligible.iloc[np.unique(np.linspace(0,len(eligible)-1,min(1000,len(eligible)),dtype=int))]
lines=[round(x/4,2) for x in range(-12,13)]
rows=[]
for i,r in enumerate(selected.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="strength").head(250)
 league=data[(data.date<r.date)&(data.league==r.league)&data.hg.notna()&data.ag.notna()]
 if len(sample)<50 or len(league)<100:continue
 actual=float(r.hg-r.ag)
 for line in lines:
  for model,history in (("Matrix",sample),("League baseline",league)):
   price,w,l,p=fair((history.hg-history.ag).to_numpy(),line)
   if not np.isfinite(price):continue
   aw,al,ap=units(actual,line)
   # RPS-equivalent squared error for the three-way settlement components.
   # This tests expected stake return at a fixed 1.95 quote, not bookmaker profitability.
   ev195=(1.95-1)*aw-al
   predicted_ev195=(1.95-1)*w-l
   rows.append(dict(match_id=r.match_id,period="2026" if r.date>=pd.Timestamp("2026-01-01") else "2025",line=line,model=model,analogues=len(history),fair=price,win_units=w,loss_units=l,push_units=p,real_win=aw,real_loss=al,real_push=ap,brier_win=(w-aw)**2,brier_loss=(l-al)**2,predicted_ev195=predicted_ev195,actual_ev195=ev195))
 if (i+1)%50==0:print("PROGRESS",i+1,flush=True)
df=pd.DataFrame(rows)
if df.empty:raise RuntimeError("No test rows")
pairs=df.pivot_table(index=["match_id","line"],columns="model",values="fair").dropna().index
df=df.set_index(["match_id","line"]).loc[pairs].reset_index()
summary=df.groupby(["line","model"],as_index=False).agg(fixtures=("match_id","nunique"),brier_win=("brier_win","mean"),brier_loss=("brier_loss","mean"),predicted_win=("win_units","mean"),actual_win=("real_win","mean"),predicted_push=("push_units","mean"),actual_push=("real_push","mean"))
period=df.groupby(["period","model"],as_index=False).agg(observations=("match_id","size"),brier_win=("brier_win","mean"),brier_loss=("brier_loss","mean"))
os.makedirs("research_results",exist_ok=True)
df.to_csv("research_results/asian_handicap_audit_detail.csv",index=False)
summary.to_csv("research_results/asian_handicap_audit_summary.csv",index=False)
period.to_csv("research_results/asian_handicap_audit_by_period.csv",index=False)
print("TESTED",df.match_id.nunique(),flush=True)
print(summary.to_string(index=False),flush=True)
print(period.to_string(index=False),flush=True)


print("LOADING ASIAN BOOKMAKER QUOTES",flush=True)
odds_records=fetch("historical_match_odds","match_id,odds_payload")
odds_by_match={}
for rec in odds_records:
 offers={}
 for bookmaker in (((rec.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []):
  name=str(bookmaker.get("bookmaker") or "unknown")
  offers[name]=(bookmaker.get("markets") or {}).get("asian_handicap") or {}
 odds_by_match[rec["match_id"]]=offers
def get_quote(market,side,line,phase):
 for k,entry in (market.get(side) or {}).items():
  try:
   if abs(float(k)-line)<0.00001:
    price=float(entry.get(phase))
    if 1.01<price<100:return price
  except (TypeError,ValueError,AttributeError):pass
 return None
price_rows=[]
for record in df[df.model=="Matrix"].itertuples(index=False):
 for book,market in odds_by_match.get(record.match_id,{}).items():
  for side,handicap,aw,al,pw,pl in (("home",record.line,record.real_win,record.real_loss,record.win_units,record.loss_units),
                                    ("away",-record.line,record.real_loss,record.real_win,record.loss_units,record.win_units)):
   for phase in ("opening","last_seen"):
    price=get_quote(market,side,handicap,phase)
    if price is None:continue
    ev=(price-1)*pw-pl
    profit=(price-1)*aw-al
    price_rows.append(dict(match_id=record.match_id,period=record.period,line=handicap,side=side,phase=phase,bookmaker=book,price=price,model_fair=(1+pl/pw if pw else np.nan),predicted_roi=ev,realized_profit=profit,signal_5pct=int(ev>=.05),signal_10pct=int(ev>=.10)))
priced=pd.DataFrame(price_rows)
if priced.empty:raise RuntimeError("No matched Asian prices")
priced.to_csv("research_results/asian_handicap_bookmaker_detail.csv",index=False)
def summary_fn(frame):
 return pd.Series({"quotes":len(frame),"matches":frame.match_id.nunique(),"average_predicted_roi":frame.predicted_roi.mean(),"actual_roi_all":frame.realized_profit.mean(),"bets_5pct":int(frame.signal_5pct.sum()),"roi_5pct":frame.loc[frame.signal_5pct==1,"realized_profit"].mean(),"bets_10pct":int(frame.signal_10pct.sum()),"roi_10pct":frame.loc[frame.signal_10pct==1,"realized_profit"].mean()})
priced.groupby(["phase","side","bookmaker","line"],dropna=False).apply(summary_fn,include_groups=False).reset_index().to_csv("research_results/asian_handicap_bookmaker_by_line.csv",index=False)
priced.groupby(["phase","side","bookmaker"],dropna=False).apply(summary_fn,include_groups=False).reset_index().to_csv("research_results/asian_handicap_bookmaker_summary.csv",index=False)
priced.groupby(["period","phase","side","bookmaker"],dropna=False).apply(summary_fn,include_groups=False).reset_index().to_csv("research_results/asian_handicap_bookmaker_by_period.csv",index=False)
# One selection per fixture, bookmaker and quote phase, chosen only by predicted EV.
best=priced.sort_values(["predicted_roi","line"],ascending=[False,True]).drop_duplicates(["match_id","bookmaker","phase"])
best=best[best.predicted_roi>=.05]
best.to_csv("research_results/asian_handicap_bookmaker_best_bets.csv",index=False)
if len(best):
 best.groupby(["period","phase","bookmaker"],dropna=False).apply(summary_fn,include_groups=False).reset_index().to_csv("research_results/asian_handicap_bookmaker_best_summary.csv",index=False)
print("PRICED",len(priced),"UNIQUE MATCHES",priced.match_id.nunique(),"BEST",len(best),flush=True)
print(priced.groupby(["phase","side","bookmaker"]).apply(summary_fn,include_groups=False).to_string(),flush=True)
