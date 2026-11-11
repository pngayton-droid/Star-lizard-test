"""Shared, deterministic exploratory pattern scan for both Streamlit pages."""
import numpy as np
import pandas as pd
from math import erfc, sqrt

SCAN_FIELDS=["league","home_price_band","away_price_band"]

def run_pattern_scan(raw, min_n=80, split=0.7, chosen=None):
    df=raw.copy().drop_duplicates(subset=["understat_id"])
    if chosen is None: chosen=SCAN_FIELDS
    df["match_date"]=pd.to_datetime(df["match_date"],errors="coerce")
    fields=["ft_home","ft_away","corners_home","corners_away","yellows_home","yellows_away","b365_home","b365_away"]
    for field in fields:
        df[field]=pd.to_numeric(df[field],errors="coerce")
    df=df.dropna(subset=["match_date"]).sort_values("match_date").copy()
    df["year"]=df.match_date.dt.year
    df["home_price_band"]=pd.cut(df.b365_home,bins=[0,1.5,2,3,5,np.inf],right=False,
        labels=["<1.50","1.50–1.99","2.00–2.99","3.00–4.99","5+"])
    df["away_price_band"]=pd.cut(df.b365_away,bins=[0,2,3,5,np.inf],right=False,
        labels=["<2.00","2.00–2.99","3.00–4.99","5+"])
    df["total_goals"]=df.ft_home+df.ft_away
    df["total_corners"]=df.corners_home+df.corners_away
    df["total_yellows"]=df.yellows_home+df.yellows_away
    
    outcomes={
        "Over 2.5 goals": ("total_goals",lambda x:x>2.5),
        "Both teams score": ("total_goals",lambda x:(df.ft_home>0)&(df.ft_away>0)),
        "Over 9.5 corners": ("total_corners",lambda x:x>9.5),
        "Over 4.5 yellow cards": ("total_yellows",lambda x:x>4.5),
    }
    
    def bh_qvalues(p):
        p=np.asarray(p,dtype=float)
        order=np.argsort(p)
        ranked=p[order]
        q=np.minimum.accumulate((ranked*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
        result=np.empty(len(p))
        result[order]=np.minimum(q,1)
        return result
    
    # Conservative approximate two-sided normal test; no scipy dependency.
    
    def compare(a,n,b,m):
        pooled=(a+b)/(n+m)
        se=sqrt(max(pooled*(1-pooled)*(1/n+1/m),1e-15))
        return erfc(abs(a/n-b/m)/(se*sqrt(2)))
    
    rows=[]
    for label,(column,fn) in outcomes.items():
        valid=df[column].notna() & df.ft_home.notna() & df.ft_away.notna()
        if label=="Over 9.5 corners":
            valid &= df["has_corners"].fillna(False).astype(bool)
        if label=="Over 4.5 yellow cards":
            valid &= df["has_yellows"].fillna(False).astype(bool)
        subset=df.loc[valid].copy()
        if len(subset)<2*min_n:
            continue
        subset["hit"]=fn(subset[column]).loc[subset.index].astype(int)
        cut=int(len(subset)*split)
        train,test=subset.iloc[:cut],subset.iloc[cut:]
        if len(test)<min_n:
            continue
        baseline=train.hit.mean()
        for field in chosen:
            for value,part in train.groupby(field,observed=True,dropna=True):
                held=test[test[field]==value]
                if len(part)<min_n or len(held)<min_n:
                    continue
                train_hits=int(part.hit.sum())
                held_hits=int(held.hit.sum())
                # Compare a segment to the rest of training, not to the inclusive baseline.
                rest=train[train[field]!=value]
                if len(rest)<min_n:
                    continue
                p=compare(train_hits,len(part),int(rest.hit.sum()),len(rest))
                rows.append(dict(market=label,segment=field,value=str(value),
                    train_n=len(part),train_rate=train_hits/len(part),
                    train_baseline=baseline,train_lift=train_hits/len(part)-baseline,
                    holdout_n=len(held),holdout_rate=held_hits/len(held),
                    holdout_baseline=test.hit.mean(),holdout_lift=held_hits/len(held)-test.hit.mean(),
                    p_value=p))
    result=pd.DataFrame(rows)
    
    if result.empty:
        return result
    result["fdr_q"]=bh_qvalues(result.p_value.to_numpy())
    result["replicated_direction"]=(result.train_lift*result.holdout_lift)>0
    result["screen_flag"]=(result.fdr_q<0.05)&result.replicated_direction
    result=result.sort_values(["screen_flag","fdr_q","holdout_n"],ascending=[False,True,False])
    
    return result.reset_index(drop=True)
