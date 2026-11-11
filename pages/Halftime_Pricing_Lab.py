"""Halftime market research workspace — historical and non-actionable."""
import streamlit as st
from halftime_research_engine import halftime_sample
from halftime_snapshot_pricing import OUTCOMES,snapshot_research,quote_break_even
from halftime_fixture_scenario import second_half_scenario

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
current_inputs=(int(home_score),int(away_score),float(home_xg),float(away_xg),market,float(tolerance),comp.strip())
if st.session_state.get("ht_snapshot_inputs")!=current_inputs:
    st.session_state.pop("ht_snapshot_result",None)
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
            st.session_state["ht_snapshot_inputs"]=current_inputs
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
    st.caption("Results are cleared when halftime inputs change; recalculate for the new situation.")
    st.subheader("Optional real market quote")
    odds=st.number_input("Actual decimal odds (enter manually)",1.01,1000.0,2.0,0.05)
    fee=st.number_input("Commission on net winnings (%)",0.0,30.0,0.0,0.5)
    threshold=quote_break_even(odds,fee)
    st.metric("Market break-even probability",f"{100*threshold:.2f}%")
    st.write(f'Uncalibrated historical frequency minus break-even: **{100*(result["train_rate"]-threshold):+.1f} percentage points**')
    st.warning("A difference from the market break-even rate is NOT a proven value opportunity. Historical state matching does not incorporate fixture strength, lineup, live events, bookmaker margin or prospective calibration.")
st.subheader("Next steps")
st.caption("Combine this historical conditional prior with a calibrated pre-match strength model, real halftime match data, verified next-goal ordering, and timestamped market odds.")

st.divider()
st.subheader("Fixture-strength second-half scenario")
st.caption("Enter pre-match expected FULL-TIME goals from your fixture model. This is a separate illustrative Poisson scenario, not calibrated halftime fair odds.")
l,r=st.columns(2)
with l:
    pre_home=st.number_input("Home pre-match expected full-time goals",0.0,8.0,1.5,0.05)
with r:
    pre_away=st.number_input("Away pre-match expected full-time goals",0.0,8.0,1.1,0.05)
share=st.slider("Expected share of goals after halftime",0.35,0.70,0.50,0.01)
adjust=st.slider("Exploratory HT xG share adjustment",0.0,1.0,0.0,0.05)
st.caption("Adjustment 0 = pre-match prior only; above zero reallocates the remaining total between teams based on HT xG share. It is a user-controlled heuristic, not a learned parameter.")
if st.button("Run second-half fixture scenario"):
    try:
        scenario=second_half_scenario(pre_home,pre_away,home_xg,away_xg,int(home_score),int(away_score),share,adjust)
        st.write(f'Illustrative second-half expected goals: home {scenario["home_2h_mu"]:.2f}, away {scenario["away_2h_mu"]:.2f}')
        import pandas as pd
        st.dataframe(pd.DataFrame([{"Outcome":k,"Scenario probability":f"{v*100:.1f}%","Mechanical decimal price":f"{1/v:.2f}" if v>0 else "N/A"} for k,v in scenario["probabilities"].items()]),hide_index=True,use_container_width=True)
        st.warning("These are mechanical scenario prices, NOT validated fair odds or betting signals. No halftime live odds, red cards, opposition adjustment, lineup or event timing incorporated.")
    except Exception as exc:
        st.error("Scenario unavailable")
        st.code(type(exc).__name__+": "+str(exc)[:200])
