"""PRO STARLIZARD: read-only, pre-match anomaly hunter. No external API requests."""
import math
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Scrumpy's Anomaly Hunter", page_icon="🔎", layout="wide")
st.title("🔎 Scrumpy's Anomaly Hunter")
st.caption("Pre-match 1X2 research · chronological validation · no API calls · no betting recommendations")
st.warning("Exploratory research only. Last-seen bookmaker prices are not proven executable, and discoveries are not confirmed edges.")

@st.cache_data(ttl=3600)
def load():
    db = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])
    out = []
    for offset in range(0, 50000, 1000):
        rows = (db.table("starlizard_backtest_1x2")
                .select("match_id,match_date,home_goals,away_goals,home_price,draw_price,away_price")
                .order("match_date").range(offset, offset+999).execute()).data or []
        out.extend(rows)
        if len(rows)<1000: break
    df=pd.DataFrame(out)
    if df.empty: return df
    for c in ["home_goals","away_goals","home_price","draw_price","away_price"]:
        df[c]=pd.to_numeric(df[c],errors="coerce")
    df["match_date"]=pd.to_datetime(df["match_date"],errors="coerce")
    return df.dropna(subset=["match_date","home_goals","away_goals","home_price","draw_price","away_price"]).sort_values(["match_date","match_id"])

df=load()
if df.empty:
    st.error("No complete matches with prices and outcomes found.")
    st.stop()
st.metric("Matches available",f"{len(df):,}")
st.markdown("### 1. Market calibration and anomalous odds bands")
st.caption("These are descriptive pre-match price bands. The discovery and later validation samples are separated by date.")
cut=df["match_date"].quantile(.7)
st.write(f"Discovery: matches before {cut.date()} · Validation: matches on/after {cut.date()}")
records=[]
for side,price_col in [("Home","home_price"),("Draw","draw_price"),("Away","away_price")]:
    for lo,hi in [(1.01,1.5),(1.5,2),(2,3),(3,5),(5,10),(10,1000)]:
        part=df[(df[price_col]>=lo)&(df[price_col]<hi)].copy()
        if side=="Home": part["win"]=(part.home_goals>part.away_goals).astype(int)
        elif side=="Away": part["win"]=(part.away_goals>part.home_goals).astype(int)
        else: part["win"]=(part.home_goals==part.away_goals).astype(int)
        for period,subset in [("Discovery",part[part.match_date<cut]),("Validation",part[part.match_date>=cut])]:
            if subset.empty: continue
            roi=((subset["win"]*subset[price_col]-1).mean()*100)
            records.append({"Side":side,"Opening band proxy":f"{lo:g}–{hi:g}","Period":period,
                            "Bets":len(subset),"Win %":round(subset.win.mean()*100,1),
                            "Market implied %":round((100/subset[price_col]).mean(),1),
                            "ROI %":round(roi,1)})
res=pd.DataFrame(records)
st.dataframe(res,use_container_width=True,hide_index=True)
st.caption("Band prices use stored home_price/draw_price/away_price, not verified opening prices. This is NOT a strategy based on future shortening.")
st.markdown("### 2. Candidate patterns surviving the chronological split")
a=res[res.Period=="Discovery"].rename(columns={"ROI %":"Discovery ROI %","Bets":"Discovery bets"})
b=res[res.Period=="Validation"].rename(columns={"ROI %":"Validation ROI %","Bets":"Validation bets"})
merged=a.merge(b[["Side","Opening band proxy","Validation ROI %","Validation bets"]],on=["Side","Opening band proxy"])
candidates=merged[(merged["Discovery bets"]>=100)&(merged["Validation bets"]>=50)&(merged["Discovery ROI %"]>0)&(merged["Validation ROI %"]>0)]
if candidates.empty: st.info("No simple 1X2 price-band pattern passed both samples with the minimum bet counts.")
else: st.dataframe(candidates[["Side","Opening band proxy","Discovery bets","Discovery ROI %","Validation bets","Validation ROI %"]],use_container_width=True,hide_index=True)
st.markdown("### 3. Five research tracks")
st.write("**Market mispricing by match type:** requires genuine pre-match rolling team features; final-match xG is excluded.")
st.write("**Dangerous 15 minutes:** goal event timing is stored, but timestamped in-play prices must be verified before ROI testing.")
st.write("**Comeback that never arrives:** halftime scores and halftime xG are available; halftime betting prices must be verified.")
st.write("**Bookmaker disagreement:** compare identical market, line, and observation time; snapshots alone cannot establish simultaneous availability.")
st.write("**Anomaly hunter:** this first screen tests pre-match 1X2 price bands on an untouched later chronological split.")
st.caption("No paid StatsAPI requests. No trades or bets placed.")
