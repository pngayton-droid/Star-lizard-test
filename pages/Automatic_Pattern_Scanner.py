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

from pattern_intelligence_engine import run_pattern_scan, SCAN_FIELDS

st.metric("Unique linked historical matches",f"{len(df):,}")
min_n=st.slider("Minimum matches per segment in each period",30,250,80,10)
split=st.slider("Training period fraction (chronological)",0.5,0.85,0.7,0.05)
group_choices=SCAN_FIELDS
chosen=st.multiselect("Scan segments",group_choices,default=group_choices)
st.caption("Data is split chronologically. Segments are discovered in the earlier period and checked on later matches. Results depend on available fields.")

result=run_pattern_scan(df,min_n=min_n,split=split,chosen=chosen)
if result.empty:
    st.info("No segments have enough matches in both periods. Reduce the minimum sample size or select more segments.")
    st.stop()
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
