"""Halftime market research workspace — historical and non-actionable."""
import streamlit as st
from halftime_research_engine import halftime_sample
from halftime_snapshot_pricing import OUTCOMES,snapshot_research,quote_break_even

st.set_page_config(page_title="Halftime Pricing Lab",layout="wide")
st.title("🦎 Halftime Pricing Lab")
st.caption("A research bridge from the actual halftime state to historical second-half outcomes. No invented market prices.")
st.warning("This is not yet a calibrated fixture-specific pricing model. Use only to explore historical conditional rates.")

a,b=st.columns(2)
with a:
    home_score=st.number_input("Home goals at HT",0,10,0)
    home_xg=st.number_input("Home HT xG",0.0,8.0,0.8,0.05)
with b:
    away_score=st.number_input("Away goals at HT",0,10,0)
    away_xg=st.number_input("Away HT xG",0.0,8.0,0.6,0.05)
market=st.selectbox("Historical outcome to investigate",list(OUTCOMES))
tolerance=st.slider("xG matching tolerance (each team)",0.1,1.5,0.5,0.1)
comp=st.text_input("Optional StatsAPI competition ID (blank = all historical leagues)",placeholder="comp_3039")
st.caption("Exact halftime score and approximate home/away xG. Earlier 70% of match dates used for estimation, later 30% reported separately.")
if st.button("Calculate halftime historical estimate",type="primary"):
    try:
        data=halftime_sample(comp.strip() or None)
        result=snapshot_research(data,int(home_score),int(away_score),
            float(home_xg),float(away_xg),market,float(tolerance))
        if result["status"]!="Research estimate available":
            st.info(result["status"])
            if "train_n" in result:
                st.write("Earlier sample:",result["train_n"],"Later sample:",result["later_n"])
            st.caption("Broaden xG tolerance or choose a more common halftime score to inspect more matches.")
        else:
            st.session_state["ht_snapshot_result"]=result
            st.session_state["ht_snapshot_market"]=market
    except Exception as exc:
        st.error("Unable to calculate the halftime research estimate.")
        st.code(type(exc).__name__+": "+str(exc)[:200])
result=st.session_state.get("ht_snapshot_result")
if result and result.get("status")=="Research estimate available":
    st.subheader("Historical estimate")
    x,y,z=st.columns(3)
    x.metric("Earlier-period frequency",f'{100*result["train_rate"]:.1f}%')
    y.metric("Later-period frequency",f'{100*result["later_rate"]:.1f}%')
    z.metric("Descriptive 95% interval",f'{100*result["lower"]:.1f}–{100*result["upper"]:.1f}%')
    st.caption(f'Earlier: {result["train_hits"]}/{result["train_n"]}; later: {result["later_hits"]}/{result["later_n"]}; date split: {result["cutoff"]}.')
    st.caption("Results remain on screen after editing inputs until recalculated; they describe the last submitted snapshot.")
    st.subheader("Optional real market quote")
    odds=st.number_input("Actual decimal odds (enter manually)",1.01,1000.0,2.0,0.05)
    fee=st.number_input("Commission on net winnings (%)",0.0,30.0,0.0,0.5)
    threshold=quote_break_even(odds,fee)
    st.metric("Market break-even probability",f"{100*threshold:.2f}%")
    st.write(f'Historical estimate minus break-even: **{100*(result["train_rate"]-threshold):+.1f} percentage points**')
    st.warning("A difference from the market break-even rate is NOT a proven value opportunity. Historical state matching does not incorporate fixture strength, lineup, live events, bookmaker margin or prospective calibration.")
st.subheader("Next steps")
st.caption("Combine this historical conditional prior with a calibrated pre-match strength model, real halftime match data, verified next-goal ordering, and timestamped market odds.")
