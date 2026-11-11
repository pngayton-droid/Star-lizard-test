"""Exploratory historical pattern discovery with temporal holdout and FDR correction.
No market-price edge claims: these are outcome-rate shifts only.
"""
import numpy as np
import pandas as pd
import streamlit as st
from archive_data_engine import load_research

st.set_page_config(page_title="Automatic Pattern Scanner", layout="wide")
st.title("🦎 Automatic Pattern Scanner")
st.caption("Research-only discovery. Historical patterns are not betting edges without market prices, costs and out-of-sample validation.")

@st.cache_data(ttl=900, show_spinner="Loading historical matches…")
def get_matches():
    return load_research()

try:
    df=get_matches()
except Exception as exc:
    st.error("Private archive data unavailable.")
    st.code(str(exc))
    st.stop()
if df.empty:
    st.warning("No historical matches available.")
    st.stop()

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
st.metric("Unique linked historical matches",f"{len(df):,}")
min_n=st.slider("Minimum matches per segment in each period",30,250,80,10)
split=st.slider("Training period fraction (chronological)",0.5,0.85,0.7,0.05)
group_choices=["league","home_price_band","away_price_band"]
chosen=st.multiselect("Scan segments",group_choices,default=group_choices)
st.caption("Data is split chronologically. Segments are discovered in the earlier period and checked on later matches. Results depend on available fields.")

def bh_qvalues(p):
    p=np.asarray(p,dtype=float)
    order=np.argsort(p)
    ranked=p[order]
    q=np.minimum.accumulate((ranked*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
    result=np.empty(len(p))
    result[order]=np.minimum(q,1)
    return result

# Conservative approximate two-sided normal test; no scipy dependency.
from math import erfc,sqrt
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
    st.info("No segments have enough matches in both periods. Reduce the minimum sample size or select more segments.")
    st.stop()
result["fdr_q"]=bh_qvalues(result.p_value.to_numpy())
result["replicated_direction"]=(result.train_lift*result.holdout_lift)>0
result["screen_flag"]=(result.fdr_q<0.05)&result.replicated_direction
result=result.sort_values(["screen_flag","fdr_q","holdout_n"],ascending=[False,True,False])
c1,c2,c3=st.columns(3)
c1.metric("Segments tested",len(result))
c2.metric("Replicated direction",int(result.replicated_direction.sum()))
c3.metric("Statistical screen flags",int(result.screen_flag.sum()))
st.caption("Screen flags require training FDR q < 0.05 and the same directional lift in holdout. They are exploratory, not validated profitable strategies.")
for field in ["train_rate","train_baseline","train_lift","holdout_rate","holdout_baseline","holdout_lift","p_value","fdr_q"]:
    result[field]=result[field].round(4)
st.dataframe(result,use_container_width=True,hide_index=True)
st.download_button("Export pattern scan CSV",result.to_csv(index=False).encode("utf-8"),
    "starlizard_pattern_scan.csv","text/csv")
st.info("Limits: Calendar-time split is not a fully independent prospective test. Group searches and outcomes are correlated; FDR is approximate. Goals/corners/cards results lack market odds, bookmaker margin and commission. Only linked matches are scanned, which may introduce selection bias.")
