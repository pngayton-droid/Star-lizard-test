"""PRO STARLIZARD halftime research workspace."""
import streamlit as st
from halftime_state_scanner import scan_halftime_states
from halftime_interaction_engine import scan_interactions
from halftime_research_engine import halftime_sample,rates

st.set_page_config(page_title="Halftime Intelligence",layout="wide")
st.title("🦎 Halftime Intelligence")
st.caption("Dedicated second-half research. Historical outcomes, not live odds or a calibrated halftime pricing model.")
st.subheader("All halftime situations")
st.caption("Scan 0–0, draws, leading and trailing scores, xG dominance and second-half outcomes across the archive.")
min_sample=st.number_input("Minimum matches per historical segment",min_value=30,max_value=1000,value=100,step=10)
if st.button("Scan all halftime situations",type="primary"):
    try:
        full_sample=halftime_sample()
        results=scan_halftime_states(full_sample,min_n=min_sample)
        st.metric("Historical matches scanned",len(full_sample))
        st.metric("Historical segments meeting threshold",len(results))
        if not results.empty:
            st.dataframe(results,hide_index=True,use_container_width=True)
            st.download_button("Download halftime scan",results.to_csv(index=False).encode("utf-8"),
                "starlizard_halftime_states.csv",mime="text/csv")
            st.caption("Percentages describe second-half outcomes within each halftime segment; overlapping segments are not independent. No multiple-testing adjustment or prospective validation yet.")
        else:
            st.info("No historical segments meet this minimum sample size.")
    except Exception as exc:
        st.error("Broad halftime scan unavailable.")
        st.code(type(exc).__name__+": "+str(exc)[:250])
st.subheader("Automatic halftime interaction discovery")
st.caption("Checks pairs of halftime conditions, ranking patterns by their earlier-period deviation and reporting later-period frequencies separately.")
min_interaction=st.number_input("Minimum earlier-period sample per combination",min_value=50,max_value=1000,value=120,step=10)
if st.button("Discover combined halftime patterns"):
    try:
        rows=halftime_sample()
        found=scan_interactions(rows,minimum=min_interaction)
        st.metric("Combined outcome segments inspected",len(found))
        if found.empty:
            st.info("No combinations met the sample requirements.")
        else:
            st.dataframe(found,hide_index=True,use_container_width=True)
            st.download_button("Export halftime combinations",found.to_csv(index=False).encode("utf-8"),
                "starlizard_halftime_interactions.csv",mime="text/csv")
            st.warning("Exploratory ranking only. Multiple comparisons, selection bias, correlated outcomes and repeated research can create false discoveries. Later-period rates are not proven out-of-sample betting edges or fair odds.")
    except Exception as exc:
        st.error("Combined halftime research unavailable.")
        st.code(type(exc).__name__+": "+str(exc)[:250])
st.divider()
st.markdown("### Specific strategy research: trailing-team halftime xG")
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
