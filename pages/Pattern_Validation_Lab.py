"""PRO STARLIZARD — additional out-of-sample research checks."""
import pandas as pd
import streamlit as st
from archive_data_engine import load_research
from pattern_validation_engine import validate_patterns

st.set_page_config(page_title="Pattern Validation Lab",layout="wide")
st.title("🦎 Pattern Validation Lab")
st.caption("Training discovery followed by later-period confirmation. No profitability claims.")

@st.cache_data(ttl=900)
def get_matches():
    return load_research()

try:
    matches=get_matches()
except Exception as exc:
    st.error("Could not load private historical archive.")
    st.code(str(exc))
    st.stop()
if matches.empty:
    st.warning("No archive matches available.")
    st.stop()

minimum=st.slider("Minimum matches in each period",30,250,80,10)
split=st.slider("Chronological training fraction",0.5,0.85,0.7,0.05)
@st.cache_data(ttl=900)
def audit(frame,min_n,split_value):
    return validate_patterns(frame,min_n=min_n,split=split_value)

with st.spinner("Auditing historical patterns…"):
    try:
        findings=audit(matches,minimum,split)
    except Exception as exc:
        st.error("Validation could not be completed.")
        st.code(str(exc))
        st.stop()
if findings.empty:
    st.info("No segments met the minimum training and holdout sample sizes.")
    st.stop()
a,b,c=st.columns(3)
a.metric("Segments audited",len(findings))
b.metric("Training-screen flags",int(findings.screen_flag.sum()))
c.metric("Later-period confirmations",int(findings.holdout_confirmed.sum()))
st.caption("Later-period confirmation requires the same direction of effect and holdout BH-adjusted q < 0.05. Holdout is only used once for this audit; repeated tuning on it invalidates its independence.")
confirmed=findings[findings.holdout_confirmed]
if confirmed.empty:
    st.info("No segments passed the stricter later-period confirmation check.")
else:
    st.subheader("Confirmed historical differences")
    st.dataframe(confirmed,hide_index=True,use_container_width=True)
st.subheader("All audited segments")
st.dataframe(findings,hide_index=True,use_container_width=True)
st.download_button("Download validation results",findings.to_csv(index=False).encode("utf-8"),
                   "starlizard_validation_audit.csv",mime="text/csv")
st.warning("This is retrospective historical validation, not a prospective betting trial. The holdout can become contaminated by repeated selection or parameter changes. Market prices, margin, commissions, execution and live-data timing remain untested.")
