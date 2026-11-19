"""Break down the unchanged chronological Asian goals selections by line and odds band."""
import pandas as pd
from pathlib import Path
p=Path("research_results/asian_goals_full_chrono_bets.csv")
df=pd.read_csv(p)
a=df[(df.bookmaker=="Bet365")&(df.role=="Bet365 anchor")].copy()
assert len(a)>=5000, f"Expected full 2020-2026 audit; got {len(a)}"
a["year"]=a["year"].astype(str)
a["odds_band"]=pd.cut(a.price,[1.5,1.75,2,2.25,2.5,2.75,3.00001],right=False,include_lowest=True).astype(str)
a["goal_line"]=a.line.map(lambda v:f"Under {v:g}")
def summary(cols):
 return a.groupby(cols,dropna=False,observed=True).agg(bets=("profit","size"),roi=("profit","mean"),profit_units=("profit","sum"),predicted_roi=("predicted_roi","mean"),mean_price=("price","mean"),winning_bets=("profit",lambda x:int((x>0).sum()))).reset_index()
frames=[]
for name,cols in [("line",["goal_line"]),("odds",["odds_band"]),("line_and_odds",["goal_line","odds_band"]),("line_by_year",["year","goal_line"]),("odds_by_year",["year","odds_band"])]:
 x=summary(cols);x.insert(0,"breakdown",name);frames.append(x)
out=pd.concat(frames,ignore_index=True)
out.to_csv("research_results/asian_goals_line_odds_breakdown.csv",index=False)
print(out.to_string(index=False),flush=True)
