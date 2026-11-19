"""Audit calibration of previously saved historical forecasts; no new API calls."""
import json, pandas as pd
p="research_results/matching_optimization_detail.csv"
df=pd.read_csv(p)
df=df[(df.market.isin(["Over 2.5 goals","BTTS Yes"])) & (df.model=="Nearest 250")].copy()
if df.empty:raise RuntimeError("Missing existing predictions")
df["month"]=pd.to_datetime(df["period"].astype(str)+"-01-01").dt.year
out=df.groupby(["period","market"],as_index=False).agg(matches=("actual","size"),predicted=("predicted","mean"),actual=("actual","mean"),observed_hits=("actual","sum"))
out["bias_pp"]=(out["predicted"]-out["actual"])*100
overall=df.groupby("market",as_index=False).agg(matches=("actual","size"),predicted=("predicted","mean"),actual=("actual","mean"),observed_hits=("actual","sum"))
overall["bias_pp"]=(overall["predicted"]-overall["actual"])*100
out.to_csv("research_results/goals_bias_by_year.csv",index=False)
overall.to_csv("research_results/goals_bias_overall.csv",index=False)
print("BY YEAR\n",out.to_string(index=False))
print("OVERALL\n",overall.to_string(index=False))
