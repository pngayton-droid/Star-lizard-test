"""Out-of-time comparison of halftime xG similarity tolerances."""
import os
import numpy as np
import pandas as pd
from supabase import create_client

client=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
cols="match_date,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_second_half_goals,away_second_half_goals"
rows=[]
for start in range(0,100000,1000):
    batch=client.table("halftime_research_outcomes").select(cols).order("match_date").range(start,start+999).execute().data or []
    rows.extend(batch)
    if len(batch)<1000:break
df=pd.DataFrame(rows).dropna()
for c in cols.split(",")[1:]:df[c]=pd.to_numeric(df[c],errors="coerce")
df=df.dropna()
df["match_date"]=pd.to_datetime(df["match_date"])
df["h"]=df.home_ht_goals.astype(int)
df["a"]=df.away_ht_goals.astype(int)
hg=df.home_second_half_goals.astype(int);ag=df.away_second_half_goals.astype(int)
markets={"Over 0.5":(hg+ag>=1),"Over 1.5":(hg+ag>=2),"Over 2.5":(hg+ag>=3),
"Home scores":hg>=1,"Away scores":ag>=1,"Both score":(hg>=1)&(ag>=1),
"Home wins":hg>ag,"Draw":hg==ag,"Away wins":hg<ag}
for name,y in markets.items():df[name]=y.astype(int)
train=df[df.match_date<"2026-01-01"].reset_index(drop=True)
test=df[df.match_date>="2026-01-01"].reset_index(drop=True)
output=[]
for tolerance in (0.2,0.3,0.5):
    predictions={name:[] for name in markets}
    targets={name:[] for name in markets}
    samples=[]
    for (h,a),group in test.groupby(["h","a"]):
        historical=train[(train.h==h)&(train.a==a)]
        if historical.empty:continue
        hx=historical.home_ht_xg.to_numpy()
        ax=historical.away_ht_xg.to_numpy()
        for row in group.itertuples(index=False,name=None):
            # Use named dataframe columns instead of positional tuple indices.
            pass
        for _,match in group.iterrows():
            mask=(np.abs(hx-match.home_ht_xg)<=tolerance)&(np.abs(ax-match.away_ht_xg)<=tolerance)
            n=int(mask.sum())
            if n<30:continue
            samples.append(n)
            for name in markets:
                prior=float(train[name].mean())
                p=(float(historical.loc[mask,name].sum())+2*prior)/(n+2)
                predictions[name].append(np.clip(p,1e-8,1-1e-8))
                targets[name].append(int(match[name]))
    for name in markets:
        p=np.array(predictions[name],dtype=float);y=np.array(targets[name],dtype=float)
        if len(p)==0:continue
        output.append({"tolerance":tolerance,"market":name,"test_n":len(p),
            "mean_training_matches":round(float(np.mean(samples)),1),
            "brier":round(float(np.mean((p-y)**2)),6),
            "logloss":round(float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),6)})
result=pd.DataFrame(output)
os.makedirs("research_results",exist_ok=True)
result.to_csv("research_results/ht_xg_tolerance_comparison.csv",index=False)
print("Train:",len(train),"Test:",len(test))
print(result.to_string(index=False))
