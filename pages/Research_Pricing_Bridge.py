"""Exploratory odds comparison for historically validated pattern segments.
Not a calibrated pre-match pricing model or a betting recommendation.
"""
import math
import pandas as pd
import streamlit as st
from archive_data_engine import load_research
from pattern_validation_engine import validate_patterns

st.set_page_config(page_title="Research Pricing Bridge",layout="wide")
st.title("🦎 Research Pricing Bridge")
st.caption("Connect later-period historical outcome rates to user-entered market quotes. Research only.")

@st.cache_data(ttl=900)
def research():
    return load_research()

@st.cache_data(ttl=900)
def audit(frame):
    return validate_patterns(frame,min_n=80,split=0.7)

try:
    matches=research()
    findings=audit(matches)
except Exception as exc:
    st.error("Unable to load the archive or validation results.")
    st.code(str(exc))
    st.stop()
if findings.empty:
    st.info("There are no historical segments meeting the minimum sample sizes.")
    st.stop()

confirmed=findings[findings.holdout_confirmed.fillna(False).astype(bool)].copy()
st.metric("Historically confirmed segments",len(confirmed))
if confirmed.empty:
    st.warning("No segments passed the later-period statistical check. Showing all audited segments for inspection only.")
    available=findings.copy()
else:
    show_all=st.checkbox("Include unconfirmed research segments",value=False)
    available=findings if show_all else confirmed
available=available.reset_index(drop=True)
available["label"]=available.apply(lambda r:
    str(r["market"])+" | "+str(r["segment"])+" = "+str(r["value"])+
    " | later sample "+str(int(r["holdout_n"])),axis=1)
chosen=st.selectbox("Historical segment",range(len(available)),
                    format_func=lambda i:available.iloc[i]["label"])
record=available.iloc[chosen]
n=int(record["holdout_n"])
hits=int(record["holdout_segment_hits"])
p=hits/n if n else 0
# Wilson 95% interval; descriptive uncertainty, not full model uncertainty.
z=1.959963984540054
den=1+z*z/n if n else 1
center=(p+z*z/(2*n))/den if n else 0
radius=(z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/den if n else 0
low=max(0,center-radius)
high=min(1,center+radius)

a,b,c=st.columns(3)
a.metric("Later-period outcomes",f"{hits:,} / {n:,}")
b.metric("Observed hit rate",f"{100*p:.1f}%")
c.metric("95% Wilson interval",f"{100*low:.1f}–{100*high:.1f}%")
st.caption("Observed outcome rate in the historical segment. This is NOT a calibrated probability for any particular future fixture.")

st.subheader("Compare with a market quote")
quote=st.number_input("Decimal odds offered",min_value=1.01,max_value=1000.0,value=2.00,step=0.05)
fee=st.number_input("Commission on net winnings (%)",min_value=0.0,max_value=30.0,value=0.0,step=0.5)
# Exchange commission approximation: only net winnings charged, no other slippage.
net_win=(quote-1)*(1-fee/100)
break_even=1/(1+net_win)
empirical_ev=p*net_win-(1-p)
lower_ev=low*net_win-(1-low)
d,e,f=st.columns(3)
d.metric("Quote break-even probability",f"{100*break_even:.2f}%")
e.metric("Historical-rate return estimate",f"{100*empirical_ev:+.2f}%")
f.metric("Lower-bound return estimate",f"{100*lower_ev:+.2f}%")
st.caption("Illustrative return per unit staked, before slippage, limits and model error. Commission is applied to net winnings only. These figures are NOT verified expected value.")

if not bool(record["holdout_confirmed"]):
    st.warning("This segment did not pass the stricter holdout confirmation test.")
else:
    st.info("This segment passed a retrospective statistical screen, not a market-value or prospective profitability test.")
if break_even < low:
    st.warning("Even if the quote beats the descriptive Wilson lower bound, it does NOT establish an edge. The selected historical segment may not represent the offered fixture or market.")
st.subheader("Research details")
details=["market","segment","value","train_n","train_rate","holdout_n","holdout_rate",
         "holdout_rest_n","holdout_rest_rate","fdr_q","holdout_q","holdout_confirmed"]
st.dataframe(pd.DataFrame({"metric":details,"value":[record.get(k) for k in details]}),
             hide_index=True,use_container_width=True)
st.download_button("Export audited segments",findings.to_csv(index=False).encode("utf-8"),
                   "starlizard_pricing_research.csv",mime="text/csv")
st.error("Research limitation: these are selected historical subgroup frequencies, not fixture-level fair odds. Historical market quotes, bookmaker margins, execution costs, data leakage controls and prospective calibration are still required before automated value flags.")
