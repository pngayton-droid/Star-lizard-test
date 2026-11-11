"""PRO STARLIZARD halftime research workspace."""
import streamlit as st
from halftime_research_engine import halftime_sample,rates

st.set_page_config(page_title="Halftime Intelligence",layout="wide")
st.title("🦎 Halftime Intelligence")
st.caption("Dedicated second-half research. Historical outcomes, not live odds or a calibrated halftime pricing model.")
st.markdown("### Trailing-team halftime xG")
competition=st.text_input("Optional StatsAPI competition ID (blank = all leagues)",placeholder="comp_3039")
deficit=st.selectbox("Halftime deficit",[1,2,3])
threshold=st.number_input("Minimum trailing-team HT xG",min_value=0.0,max_value=4.0,value=0.20,step=0.05)
if st.button("Analyse historical halftime situations"):
    try:
        rows=halftime_sample(competition.strip() or None)
        result=rates(rows,threshold,deficit)
        if not result["n"]:
            st.info("No matches meet these conditions.")
        else:
            st.metric("Historical qualifying matches",result["n"])
            a,b=st.columns(2)
            a.metric("Trailing team scored in second half",f'{result["scored_rate"]*100:.1f}%')
            b.metric("Trailing team avoided defeat",f'{result["avoid_rate"]*100:.1f}%')
            st.caption(f'{result["trailing_scored"]} of {result["n"]} scored; {result["avoided_defeat"]} avoided defeat.')
            st.warning("Scored in second half is NOT the same as scored the NEXT goal. The latter requires verified goal-event ordering. These are descriptive historical frequencies, not market fair odds.")
    except Exception as exc:
        st.error("Halftime research could not be completed.")
        st.code(type(exc).__name__+": "+str(exc)[:250])
st.subheader("Planned halftime pricing inputs")
st.write("Actual HT score, home/away HT xG, pre-match baseline, verified goal timeline, red cards, and timestamped halftime market odds.")
st.info("Next-goal pricing, Asian second-half totals, correct-score paths and halftime market comparisons must be built and validated separately.")
