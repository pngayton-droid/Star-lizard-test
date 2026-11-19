"""Chronological Matrix versus bookmaker Asian total-goals audit; no future information."""
import os,ast,math
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
def settle(total,line,side):
 parts=[line] if int(round(line*4))%2==0 else [math.floor(line*2)/2,math.ceil(line*2)/2]
 w=l=p=0.
 for part in parts:
  d=(total-part)*(1 if side=="over" else -1)
  if d>0:w+=1/len(parts)
  elif d<0:l+=1/len(parts)
  else:p+=1/len(parts)
 return w,l,p
def summarize(g):
 return pd.Series({"bets":len(g),"matches":g.match_id.nunique(),"roi":g.profit.mean(),"predicted_roi":g.predicted_roi.mean(),"mean_price":g.price.mean()})
print("LOADING MATRIX HISTORY",flush=True)
data=features()
eligible=data[(data.date>=pd.Timestamp("2025-07-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()].sort_values(["date","match_id"])
selected=eligible.copy()
odds_by_match={}
for rec in fetch("historical_match_odds","match_id,odds_payload"):
 odds_by_match[rec["match_id"]]=[((b.get("bookmaker") or "unknown"),((b.get("markets") or {}).get("total_goals") or {})) for b in (((rec.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or [])]
selected=selected[selected.match_id.isin(odds_by_match)].copy()
print("FULL ODDS-BEARING FIXTURES",len(selected),flush=True)
rows=[]
for i,r in enumerate(selected.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="strength").head(250)
 league=data[(data.date<r.date)&(data.league==r.league)&data.hg.notna()&data.ag.notna()]
 if len(sample)<50 or len(league)<100:continue
 offers=odds_by_match.get(r.match_id,[])
 if not offers:continue
 actual=float(r.hg+r.ag)
 samples=(sample.hg+sample.ag).to_numpy(dtype=float)
 baselines=(league.hg+league.ag).to_numpy(dtype=float)
 for book,market in offers:
  for key,prices in market.items():
   try:line=float(key)
   except (TypeError,ValueError):continue
   if not (0.5<=line<=7.5):continue
   for side in ("over","under"):
    outcomes=np.array([settle(x,line,side) for x in samples]).mean(axis=0)
    base=np.array([settle(x,line,side) for x in baselines]).mean(axis=0)
    aw,al,ap=settle(actual,line,side)
    w,l,p=outcomes
    bw,bl,bp=base
    for phase in ("opening","last_seen"):
     try:price=float((prices.get(side) or {}).get(phase))
     except (TypeError,ValueError,AttributeError):continue
     if not 1.01<price<100:continue
     rows.append(dict(match_id=r.match_id,period="2026" if r.date>=pd.Timestamp("2026-01-01") else "2025",bookmaker=book,phase=phase,line=line,side=side,price=price,analogues=len(sample),predicted_roi=(price-1)*w-l,baseline_roi=(price-1)*bw-bl,profit=(price-1)*aw-al,model_fair=1+l/w if w else np.nan,baseline_fair=1+bl/bw if bw else np.nan,model_brier=(w-aw)**2+(l-al)**2,baseline_brier=(bw-aw)**2+(bl-al)**2))
 if (i+1)%50==0:print("PROGRESS",i+1,flush=True)

df=pd.DataFrame(rows)
if df.empty: raise RuntimeError("No matched goal quotes")
os.makedirs("research_results",exist_ok=True)
# Use a predetermined chronological cutoff; 2026 is untouched by 2025 selection.
df=df[(df.phase=="last_seen")&(df.side=="under")&
 (df.line.between(1.5,4.5))&(df.price.between(1.5,3.0))].copy()
df["year"]=df.period
df["net_profit"]=df.profit
# Exchange commission charged only on positive settlement profit.
exchange=df.bookmaker=="Betfair Exchange"
df.loc[exchange,"net_profit"]=df.loc[exchange,"profit"]-0.05*df.loc[exchange,"profit"].clip(lower=0)
# Bet365-anchored strategy: one quote per match, selected by model only.
anchor=(df[df.bookmaker=="Bet365"].sort_values(["predicted_roi","line"],ascending=[False,True])
 .drop_duplicates("match_id"))
anchor=anchor[anchor.predicted_roi>=.05].copy()
anchor["role"]="Bet365 anchor"
# All same-line/side rival quotes, no outcome-based re-selection.
rivals=df.merge(anchor[["match_id","line","period"]],on=["match_id","line","period"],how="inner")
rivals=rivals[rivals.bookmaker!="Bet365"].copy()
peer=df[df.bookmaker!="Betfair Exchange"].groupby(["match_id","line","side"]).price.median().rename("peer_median").reset_index()
rivals=rivals.merge(peer,on=["match_id","line","side"],how="left")
rivals["peer_outlier"]=(rivals.bookmaker=="Betfair Exchange")&(
 rivals.peer_median.isna()|(rivals.price/rivals.peer_median>1.25)|
 (rivals.price/rivals.peer_median<.8))
rivals["role"]="matched rival"
allbets=pd.concat([anchor,rivals],ignore_index=True)
allbets.to_csv("research_results/asian_goals_full_chrono_bets.csv",index=False)
allbets["usable"]=~allbets.peer_outlier.fillna(False)
summary=allbets.groupby(["year","bookmaker","usable"]).agg(
 bets=("match_id","size"),matches=("match_id","nunique"),
 gross_roi=("profit","mean"),net_roi=("net_profit","mean"),
 mean_price=("price","mean"),model_predicted_roi=("predicted_roi","mean")
).reset_index()
summary.to_csv("research_results/asian_goals_full_chrono_summary.csv",index=False)
print("FULL CHRONOLOGICAL SUMMARY",flush=True)
print(summary.to_string(index=False),flush=True)
print("UNIQUE FIXTURES",df.match_id.nunique(),"ANCHOR",len(anchor),flush=True)
