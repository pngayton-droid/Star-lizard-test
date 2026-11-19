"""One-off chronological Match Matrix audit. Supabase only; zero StatsAPI calls."""
import os,ast,json,math
from collections import defaultdict,deque
import numpy as np,pandas as pd
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,columns):
 rows=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(columns).range(start,start+999).execute().data or []
  rows.extend(batch)
  if len(batch)<1000:break
 return rows
def load():
 cols="match_id,match_date,competition_id,home_team,away_team,home_goals,away_goals,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_xg,away_xg"
 df=pd.DataFrame(fetch("historical_xg",cols))
 df["match_date"]=pd.to_datetime(df.match_date)
 for col in ["home_goals","away_goals","home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg","home_xg","away_xg"]:
  df[col]=pd.to_numeric(df[col],errors="coerce")
 return df.sort_values(["match_date","match_id"]).reset_index(drop=True)
def match_corners_cards():
 rows=[]
 for item in fetch("historical_match_events","match_id,stats_data"):
  overview=((item.get("stats_data") or {}).get("overview") or {})
  rec={"match_id":item["match_id"]}
  for key,prefix in (("corner_kicks","corners"),("yellow_cards","yellows")):
   sides=((overview.get(key) or {}).get("all") or {})
   for side in ("home","away"):
    try:rec[f"{prefix}_{side}"]=float(sides[side])
    except (ValueError,TypeError,KeyError):rec[f"{prefix}_{side}"]=np.nan
  rows.append(rec)
 return pd.DataFrame(rows,columns=["match_id","corners_home","corners_away","yellows_home","yellows_away"])
def historical_opening_prices():
 output=[]
 for item in fetch("historical_match_odds","match_id,odds_payload"):
  books=((item.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []
  candidates=[]
  for book in books:
   markets=(book.get("markets") or {}).get("match_odds") or {}
   try:odds=[float((markets.get(side) or {}).get("opening")) for side in ("home","draw","away")]
   except (TypeError,ValueError):continue
   if min(odds)<=1:continue
   margin=sum(1/x for x in odds)
   if not 0.95<=margin<=1.30:continue
   candidates.append([1/x/margin for x in odds])
  if candidates:
   probs=np.median(np.asarray(candidates),axis=0);probs/=probs.sum()
   output.append({"match_id":item["match_id"],"market_home":float(probs[0]),"market_draw":float(probs[1]),"market_away":float(probs[2])})
 return pd.DataFrame(output,columns=["match_id","market_home","market_draw","market_away"])
# Execute the EXACT feature and analogue functions used in the dashboard, not a replacement model.
source=open("pages/Similarity_Pricing.py",encoding="utf-8").read()
tree=ast.parse(source)
names={"season","features","analogues"}
nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
for node in nodes:node.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())
print("LOADING_DATABASE",flush=True)
data=features().merge(historical_opening_prices(),on="match_id",how="left",validate="one_to_one")
print("LOADED",len(data),"bookmaker",int(data.market_home.notna().sum()),flush=True)
eligible=data[(data.date>=pd.Timestamp("2025-07-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.h_form.notna()&data.a_form.notna()].sort_values(["date","match_id"])
selected=eligible.iloc[np.unique(np.linspace(0,len(eligible)-1,min(2000,len(eligible)),dtype=int))]
rows=[]
for i,r in enumerate(selected.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 actual=np.array([r.hg>r.ag,r.hg==r.ag,r.hg<r.ag],dtype=float)
 variants={}
 for variant in ("strength","combined","form"):
  matches=analogues(data,target,"Pre-match",r.date,2.0,feature_set=variant)
  if len(matches)<30:break
  variants[variant]=np.array([(matches.hg>matches.ag).mean(),(matches.hg==matches.ag).mean(),(matches.hg<matches.ag).mean()])
 if len(variants)!=3:continue
 for variant,p in variants.items():
  rows.append({"match_id":r.match_id,"date":str(r.date.date()),"model":variant,"actual":int(np.argmax(actual)),"home":float(p[0]),"draw":float(p[1]),"away":float(p[2]),"brier":float(np.mean((p-actual)**2)),"book_home":r.market_home,"book_draw":r.market_draw,"book_away":r.market_away,"league":r.league,"ppg_gap":float(r.h_ppg-r.a_ppg),"gd_gap":float(r.h_gdpg-r.a_gdpg) if pd.notna(r.h_gdpg) and pd.notna(r.a_gdpg) else np.nan,"rank_gap":float(r.a_rank-r.h_rank) if pd.notna(r.a_rank) and pd.notna(r.h_rank) else np.nan})
 if (i+1)%250==0:print("PROGRESS",i+1,"of",len(selected),flush=True)
result=pd.DataFrame(rows)
result.to_csv("consolidated_match_matrix_test.csv",index=False)
print("SUMMARY",result.groupby("model").agg(matches=("match_id","nunique"),brier=("brier","mean")).round(6).to_json(orient="index"),flush=True)
paired=result.dropna(subset=["book_home","book_draw","book_away"]).copy()
paired["book_brier"]=paired.apply(lambda r:np.mean((np.array([r.book_home,r.book_draw,r.book_away])-np.eye(3)[int(r.actual)])**2),axis=1)
print("BOOKMAKER_PAIRED",paired.groupby("model").agg(matches=("match_id","nunique"),matrix_brier=("brier","mean"),book_brier=("book_brier","mean")).round(6).to_json(orient="index"),flush=True)
for model in ("strength","combined","form"):
 subset=result[result.model==model]
 for name,col,actual in (("Home","home",0),("Away","away",2)):
  v=subset.copy();v["binary_brier"]=(v[col]-(v.actual==actual).astype(float))**2
  print("OUTCOME",model,name,"n",len(v),"brier",round(v.binary_brier.mean(),6),flush=True)
# Predeclared bins; avoid optimizing thresholds on the evaluated sample.
strength=result[result.model=="strength"].copy()
strength["aligned"]=np.select([
 (strength.ppg_gap>0)&(strength.gd_gap>0),
 (strength.ppg_gap<0)&(strength.gd_gap<0),
 (strength.ppg_gap*strength.gd_gap<0)
],["Home superior","Away superior","Conflicting signals"],default="Tied/unknown")
strength["gd_band"]=pd.cut(strength.gd_gap.abs(),bins=[-0.001,0.25,0.5,1.0,float("inf")],labels=["0–0.25","0.25–0.50","0.50–1.00","1.00+"])
strength["rank_agrees"]=np.where(strength.rank_gap.isna(),"Unknown",np.where(((strength.rank_gap>0)&(strength.ppg_gap>0)&(strength.gd_gap>0))|((strength.rank_gap<0)&(strength.ppg_gap<0)&(strength.gd_gap<0)),"Yes","No"))
strength["pick"]=np.where(strength.aligned=="Home superior",0,np.where(strength.aligned=="Away superior",2,-1))
strength["correct_pick"]=(strength.pick==strength.actual).astype(int)
strength["model_prob_pick"]=np.where(strength.pick==0,strength.home,np.where(strength.pick==2,strength.away,np.nan))
strength["book_prob_pick"]=np.where(strength.pick==0,strength.book_home,np.where(strength.pick==2,strength.book_away,np.nan))
strength["book_roi"]=np.where(strength.book_prob_pick>0,(strength.correct_pick/strength.book_prob_pick)-1,np.nan)
strength.to_csv("match_matrix_strength_segments.csv",index=False)
for keys in (["aligned"],["aligned","gd_band"],["aligned","rank_agrees"]):
 for group,sub in strength.groupby(keys,observed=True,dropna=False):
  with_book=sub[sub.book_prob_pick.notna()]
  print("SEGMENT",str(group),"n",len(sub),"home_win",round((sub.actual==0).mean(),4),"draw",round((sub.actual==1).mean(),4),"away_win",round((sub.actual==2).mean(),4),"pick_hit",round(sub.loc[sub.pick>=0,"correct_pick"].mean(),4) if (sub.pick>=0).any() else None,"matrix_brier",round(sub.brier.mean(),6),"book_n",len(with_book),"book_roi_illustrative",round(with_book.book_roi.mean(),4) if len(with_book) else None,flush=True)
print("DONE",flush=True)
