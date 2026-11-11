"""Independent holdout significance audit of exploratory scanner results.

Discovery is performed by the existing scanner on chronological training data.
This audit tests the already-discovered segments against the remainder of
the later holdout period, and applies BH adjustment across all audited segments.
Not a prospective test, market-price validation, or evidence of profit.
"""
from math import erfc, sqrt
import numpy as np
import pandas as pd
from pattern_intelligence_engine import run_pattern_scan

OUTCOME_COLUMNS={
    "Over 2.5 goals":"total_goals",
    "Both teams score":"total_goals",
    "Over 9.5 corners":"total_corners",
    "Over 4.5 yellow cards":"total_yellows",
}
def _pvalue(a,n,b,m):
    if n<=0 or m<=0: return float("nan")
    pooled=(a+b)/(n+m)
    se=sqrt(pooled*(1-pooled)*(1/n+1/m)) if 0<pooled<1 else 0
    return erfc(abs(a/n-b/m)/(se*sqrt(2))) if se else 1.0

def _bh(values):
    p=np.asarray(values,dtype=float)
    out=np.full(len(p),np.nan)
    valid=np.flatnonzero(np.isfinite(p))
    if not len(valid): return out
    idx=valid[np.argsort(p[valid])]
    q=np.minimum.accumulate((p[idx]*len(idx)/np.arange(1,len(idx)+1))[::-1])[::-1]
    out[idx]=np.clip(q,0,1)
    return out

def validate_patterns(raw,min_n=80,split=0.7):
    findings=run_pattern_scan(raw,min_n=min_n,split=split)
    if findings.empty: return findings
    df=raw.copy().drop_duplicates("understat_id")
    df["match_date"]=pd.to_datetime(df.match_date,errors="coerce")
    for name in ["ft_home","ft_away","corners_home","corners_away",
                 "yellows_home","yellows_away","b365_home","b365_away"]:
        df[name]=pd.to_numeric(df[name],errors="coerce")
    df=df.dropna(subset=["match_date"]).sort_values("match_date").copy()
    df["total_goals"]=df.ft_home+df.ft_away
    df["total_corners"]=df.corners_home+df.corners_away
    df["total_yellows"]=df.yellows_home+df.yellows_away
    df["home_price_band"]=pd.cut(df.b365_home,[0,1.5,2,3,5,np.inf],right=False,
        labels=["<1.50","1.50–1.99","2.00–2.99","3.00–4.99","5+"])
    df["away_price_band"]=pd.cut(df.b365_away,[0,2,3,5,np.inf],right=False,
        labels=["<2.00","2.00–2.99","3.00–4.99","5+"])
    audits=[]
    for _,row in findings.iterrows():
        market=row["market"]
        col=OUTCOME_COLUMNS[market]
        valid=df[col].notna()&df.ft_home.notna()&df.ft_away.notna()
        if market=="Over 9.5 corners":
            valid &= df.has_corners.fillna(False).astype(bool)
        if market=="Over 4.5 yellow cards":
            valid &= df.has_yellows.fillna(False).astype(bool)
        subset=df.loc[valid]
        held=subset.iloc[int(len(subset)*split):].copy()
        if market=="Both teams score":
            hits=(held.ft_home>0)&(held.ft_away>0)
        elif market=="Over 2.5 goals": hits=held.total_goals>2.5
        elif market=="Over 9.5 corners": hits=held.total_corners>9.5
        else: hits=held.total_yellows>4.5
        selection=held[row["segment"]].astype(str)==str(row["value"])
        a=int(hits[selection].sum()); n=int(selection.sum())
        b=int(hits[~selection].sum()); m=int((~selection).sum())
        p=_pvalue(a,n,b,m)
        audits.append({"holdout_rest_n":m,"holdout_rest_rate":b/m if m else np.nan,
                       "holdout_p":p,"holdout_segment_hits":a})
    result=findings.copy()
    for field in audits[0]:
        result[field]=[item[field] for item in audits]
    result["holdout_q"]=_bh(result.holdout_p)
    result["holdout_confirmed"]=(result.holdout_q<0.05)&result.replicated_direction
    # A finding should be treated as 'candidate for further study' only.
    return result.sort_values(["holdout_confirmed","holdout_q"],ascending=[False,True]).reset_index(drop=True)
