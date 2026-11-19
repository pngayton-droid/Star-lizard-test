"""Predeclared coverage audit: compare Betfair-covered vs other Bet365 under selections.
Descriptive analysis only; never select profitable subgroups as a new strategy.
"""
import os
import numpy as np
import pandas as pd
from supabase import create_client

db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
bets=pd.read_csv("research_results/asian_goals_full_chrono_bets.csv")
bets=bets[bets.year==2026].copy()
anchor=bets[bets.bookmaker=="Bet365"].copy()
betfair=bets[bets.bookmaker=="Betfair Exchange"].copy()
covered=set(betfair.match_id)
anchor["betfair_covered"]=anchor.match_id.isin(covered)
assert len(anchor)==875 and anchor.match_id.nunique()==875, "Unexpected anchor count"
assert anchor.betfair_covered.sum()==len(betfair)==164, "Unexpected match coverage"

records=[]
for start in range(0,100000,1000):
    batch=db.table("historical_xg").select("*").range(start,start+999).execute().data or []
    records.extend(batch)
    if len(batch)<1000:break
hist=pd.DataFrame(records)
assert "match_id" in hist.columns
hist=hist.drop_duplicates("match_id")
keep=["match_id"]+[x for x in ["match_date","league","competition","home_goals","away_goals","home_team","away_team"] if x in hist.columns]
anchor=anchor.merge(hist[keep],on="match_id",how="left",validate="one_to_one")
anchor["date"]=pd.to_datetime(anchor.get("match_date"),errors="coerce")
anchor["month"]=anchor.date.dt.to_period("M").astype(str)
anchor["line_group"]=anchor.line.map(lambda x:f"Under {x:g}")
anchor["odds_band"]=pd.cut(anchor.price,[1.5,1.75,2.0,2.25,2.5,2.75,3.001],right=False)
anchor["actual_total"]=pd.to_numeric(anchor.get("home_goals"),errors="coerce")+pd.to_numeric(anchor.get("away_goals"),errors="coerce")
anchor.to_csv("research_results/asian_goals_coverage_match_details.csv",index=False)

def grouped(cols):
    return anchor.groupby(cols,dropna=False,observed=True).agg(
        bets=("match_id","size"),
        roi=("profit","mean"),
        average_odds=("price","mean"),
        model_expected_roi=("predicted_roi","mean"),
        baseline_expected_roi=("baseline_roi","mean"),
        average_goals=("actual_total","mean")
    ).reset_index()

out=[]
for dim in ["betfair_covered","line_group","odds_band","month"]+([x for x in ["league","competition"] if x in anchor.columns]):
    g=grouped(["betfair_covered"] if dim=="betfair_covered" else ["betfair_covered",dim])
    g.insert(0,"dimension",dim)
    g["group"]=g[dim].astype(str) if dim!="betfair_covered" else "all"
    out.append(g[["dimension","group","betfair_covered","bets","roi","average_odds","model_expected_roi","baseline_expected_roi","average_goals"]])
summary=pd.concat(out,ignore_index=True)
summary.to_csv("research_results/asian_goals_coverage_breakdown.csv",index=False)

# Compare each 2026 Betfair-covered bet against a noncovered Bet365 bet
# on the same goal line and closest odds, without using the match outcome.
noncovered=anchor[~anchor.betfair_covered].copy()
matched=[]
for r in anchor[anchor.betfair_covered].itertuples():
    candidates=noncovered[noncovered.line==r.line]
    if candidates.empty:continue
    idx=(candidates.price-r.price).abs().idxmin()
    q=candidates.loc[idx]
    matched.append(dict(covered_match=r.match_id,control_match=q.match_id,line=r.line,
        covered_odds=r.price,control_odds=q.price,covered_profit=r.profit,
        control_profit=q.profit,odds_difference=r.price-q.price))
    noncovered=noncovered.drop(index=idx)
matched=pd.DataFrame(matched)
matched.to_csv("research_results/asian_goals_coverage_odds_matched.csv",index=False)
print("COVERAGE SUMMARY")
print(grouped(["betfair_covered"]).to_string(index=False))
print("ODDS/LINE MATCHED",len(matched))
if len(matched):
    print("COVERED ROI",matched.covered_profit.mean(),"CONTROL ROI",matched.control_profit.mean())
print("BREAKDOWN")
print(summary.to_string(index=False))
