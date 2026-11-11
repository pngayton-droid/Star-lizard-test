"""PRO STARLIZARD central mobile-first dashboard.

Read-only fixtures and coverage. No fictitious prices or value flags.
"""
from datetime import datetime,timedelta
import csv
import io
from zoneinfo import ZoneInfo
import streamlit as st
from lightweight_fixture_feed import get_key,fixtures_for_day,fixture_label
from fixture_live_status import live_fixture_rows,fixture_status
from statsapi_competition_coverage import statsapi_coverage
from statsapi_team_coverage import team_venue_coverage
from fixture_team_readiness import venue_readiness
from statsapi_recent_venue_xg import recent_venue_xg
from fixture_goals_baseline import baseline
from fixture_market_pricing import price_goals
from fixture_asian_pricing import asian_market
from fixture_forensic_dossier import venue_dossier
from fixture_quote_comparison import compare_quote
from fixture_snapshot import build_snapshot,snapshot_json
from fixture_input_audit import baseline_input_audit
from halftime_fixture_scenario import second_half_scenario
from halftime_snapshot_pricing import quote_break_even,snapshot_research
from halftime_research_engine import halftime_sample
from halftime_next_goal_research import labelled_next_goal_rows,trailing_three_way_summary,trailing_three_way_holdout,three_way_holdout_scores

st.set_page_config(page_title="PRO STARLIZARD | Match Intelligence",layout="wide",page_icon="🦎")
st.markdown("""
<style>
:root { --sl-green:#14b88a; --sl-navy:#10243a; }
.block-container {max-width:1180px; padding-top:1.3rem; padding-bottom:4rem;}
h1,h2,h3 {letter-spacing:-.025em;}
h1 {font-weight:800!important;}
[data-testid="stMetric"] {border:1px solid rgba(128,145,160,.22);border-radius:14px;padding:14px 16px;background:rgba(128,145,160,.055);}
[data-testid="stMetricValue"] {font-size:1.65rem;}
[data-testid="stAlert"] {border-radius:12px;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:15px;}
.stButton>button[kind="primary"] {border-radius:10px;font-weight:700;}
[data-testid="stDataFrame"] {border-radius:10px;overflow:hidden;}
.sl-hero {padding:24px 25px;border-radius:19px;background:linear-gradient(115deg,#10243a,#174c53);color:white;margin-bottom:16px;}
.sl-kicker {font-size:.76rem;letter-spacing:.14em;text-transform:uppercase;color:#8ce9c7;font-weight:750;margin-bottom:6px;}
.sl-hero h1 {color:white!important;font-size:clamp(1.7rem,4vw,2.65rem);margin:0 0 7px 0;}
.sl-hero p {color:#d7e8e9;margin:0;font-size:.98rem;line-height:1.5;}
.sl-note {padding:11px 15px;border-left:3px solid #14b88a;background:rgba(20,184,138,.08);border-radius:0 10px 10px 0;margin:12px 0 19px;}
@media(max-width:640px) {
 .block-container {padding:0.75rem .8rem 3rem;}
 .sl-hero {padding:18px 17px;border-radius:14px;}
 .sl-hero h1 {font-size:1.75rem;}
 [data-testid="stMetric"] {padding:10px;}
 [data-testid="stMetricValue"] {font-size:1.35rem;}
 h2 {font-size:1.3rem!important;}
}
</style>
""",unsafe_allow_html=True)
st.markdown("""<div class="sl-hero">
<div class="sl-kicker">Match intelligence · Research terminal</div>
<h1>🦎 PRO STARLIZARD</h1>
<p>Find a fixture. Check the evidence. Explore the prices.<br>Built for clear decisions, not invented betting signals.</p>
</div>""",unsafe_allow_html=True)
st.markdown('<div class="sl-note"><strong>Data status:</strong> Fixture and historical research available. Live halftime xG, verified next-goal prices and live bookmaker quotes are not connected yet.</div>',unsafe_allow_html=True)
st.subheader("Choose your workspace")
a,b,c=st.columns(3)
with a:
    st.page_link("pages/Halftime_Pricing_Lab.py",label="🧠 Halftime Pricing Lab")
with b:
    st.page_link("pages/Halftime_Intelligence.py",label="🔎 Halftime Pattern Scanner")
with c:
    st.page_link("pages/Live_Fixture_Bridge.py",label="📅 Live Fixture Bridge")

st.subheader("Quick price calculator")
st.caption("Enter your own expected goals to get immediate research prices. No fixture feed, venue history or live odds required.")
with st.expander("⚽ Enter expected goals and calculate prices",expanded=False):
    quick_home,quick_away=st.columns(2)
    with quick_home:
        manual_home=st.number_input("Home expected goals",min_value=0.0,max_value=8.0,value=1.40,step=0.05,key="quick_home_xg")
    with quick_away:
        manual_away=st.number_input("Away expected goals",min_value=0.0,max_value=8.0,value=1.10,step=0.05,key="quick_away_xg")
    quick=price_goals(manual_home,manual_away)
    quick_names={"home_win":"Home win","draw":"Draw","away_win":"Away win",
                 "over_1_5":"Over 1.5","under_1_5":"Under 1.5",
                 "over_2_5":"Over 2.5","under_2_5":"Under 2.5",
                 "btts_yes":"BTTS Yes","btts_no":"BTTS No"}
    st.dataframe([{"Market":name,"Probability":f'{quick["probabilities"][key]*100:.1f}%',
                   "Model decimal":f'{quick["decimal_prices"][key]:.2f}' if quick["decimal_prices"][key] is not None else "N/A"}
                  for key,name in quick_names.items()],hide_index=True,use_container_width=True)
    st.dataframe([{"Score":score["score"],"Probability":f'{score["probability"]*100:.1f}%',
                   "Model decimal":f'{score["decimal_price"]:.2f}' if score["decimal_price"] is not None else "N/A"}
                  for score in quick["top_scores"][:5]],hide_index=True,use_container_width=True)
    quick_line=st.selectbox("Asian total", [1.5,1.75,2.0,2.25,2.5,2.75,3.0,3.25,3.5],index=4,key="quick_total")
    quick_prices=[asian_market(manual_home,manual_away,"total",quick_line,side) for side in ("over","under")]
    st.dataframe([{"Market":f'{p["side"].title()} {quick_line:g}',
                   "Model decimal":f'{p["fair_decimal"]:.2f}' if p["fair_decimal"] else "N/A"}
                  for p in quick_prices],hide_index=True,use_container_width=True)
    st.caption("Inputs are manually supplied assumptions, not data-derived or calibrated predictions.")

key=get_key()
if not key:
    st.error("TheStatsAPI key not configured.")
    st.stop()
today=datetime.now(ZoneInfo("Europe/London")).date()
st.subheader("Find a match")
day=st.date_input("Fixture date (UK)",value=today,
    min_value=today-timedelta(days=7),max_value=today+timedelta(days=21))
search=st.text_input("Find team or fixture",placeholder="Search fixtures")
refresh=st.button("↻ Refresh live fixtures",key="refresh_fixture_feed")
if refresh:
    fixtures_for_day.clear(key,day.isoformat())
try:
    fixtures=fixtures_for_day(key,day.isoformat())
except Exception as exc:
    st.error("Fixture feed temporarily unavailable.")
    st.code(type(exc).__name__)
    st.stop()
st.subheader("Live fixtures")
live_matches=live_fixture_rows(fixtures)
a,b=st.columns(2)
a.metric("Live now (API status)",len(live_matches))
b.metric("Fixtures on selected date",len(fixtures))
st.caption("TheStatsAPI match statuses and scores, refreshed on demand or when the 60-second cache expires. This is not a streaming connection.")
if live_matches:
    st.dataframe([{"Match":fixture_label(f),"Status":str(f.get("status") or "Unknown"),
                   "Competition ID":str(f.get("competition_id") or "")}
                  for f in live_matches],hide_index=True,use_container_width=True)
else:
    st.info("No fixtures currently marked live by the API for this date. Scheduled fixtures are listed below.")
try:
    competitions=statsapi_coverage()
except Exception:
    competitions={}
    st.warning("Historical competition coverage unavailable")
try:
    team_rows=team_venue_coverage()
except Exception:
    team_rows=[]
    st.warning("Team venue coverage unavailable")
ready=[]
covered=[]
for fixture in fixtures:
    history=competitions.get(str(fixture.get("competition_id") or ""))
    if history and int(history.get("matches") or 0)>=500:
        covered.append(fixture)
        if team_rows and venue_readiness(fixture,team_rows).get("status")=="Venue xG sample ready":
            ready.append(fixture)
m1,m2,m3=st.columns(3)
m1.metric("Scheduled fixtures",len(fixtures))
m2.metric("History-covered",len(covered))
m3.metric("Venue xG ready",len(ready))
st.caption("History-covered means at least 500 StatsAPI historical league matches. Venue-ready requires sufficient home and away xG observations.")
st.subheader("Platform details")
st.caption("Live view of what the platform can actually provide today; this is a build-status panel, not a claim that all pricing engines are calibrated.")
with st.expander("View platform coverage and development status",expanded=False):
    left,middle,right=st.columns(3)
    left.metric("Fixtures with league history",len(covered))
    middle.metric("Fixtures with venue xG",len(ready))
    right.metric("Venue coverage",f"{len(ready)/len(covered)*100:.0f}%" if covered else "N/A")
    st.caption("Ready = historical venue xG sample available. This does not mean that a match is live or that market odds have been collected.")
    st.write("**Available now:** fixture discovery, venue data checks, baseline goals scenarios, manual halftime scenario, historical halftime research.")
    st.write("**In development:** calibrated multi-market pricing, automatic live halftime state, verified market odds, referee/corners/cards integration, automated value alerts.")
    st.page_link("pages/Live_Fixture_Bridge.py",label="Open fixture ingestion and coverage workspace")
st.subheader("Match explorer")
st.caption("Select a fixture below to open its halftime scenario workspace.")
try:
    recent_rows=recent_venue_xg() if ready else []
except Exception:
    recent_rows=[]
    st.warning("Recent xG summary unavailable; match queue remains accessible.")

queue_filter=st.selectbox("Fixture view",["All fixtures","Live only","Venue xG ready"],key="fixture_view")
show=live_matches if queue_filter=="Live only" else ready if queue_filter=="Venue xG ready" else fixtures
if search.strip():
    show=[f for f in show if search.lower() in fixture_label(f).lower()]
st.caption(f"Showing {len(show)} matching fixtures. Select any match to inspect available data.")
if show:
    queue_rows=[]
    for fixture in show:
        queue_rows.append({
            "Fixture":fixture_label(fixture),
            "Competition ID":str(fixture.get("competition_id") or ""),
            "Venue xG":venue_readiness(fixture,team_rows).get("status") if team_rows else "Unavailable",
            "Historical league matches":int((competitions.get(str(fixture.get("competition_id") or "")) or {}).get("matches") or 0),
        })
    st.dataframe(queue_rows,hide_index=True,use_container_width=True,height=min(390,40+len(queue_rows)*35))
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=list(queue_rows[0]))
    writer.writeheader()
    writer.writerows(queue_rows)
    st.download_button("Export matching fixture queue (CSV)",output.getvalue(),
        file_name=f"starlizard_fixture_queue_{day.isoformat()}.csv",mime="text/csv")
if not show:
    st.info("No fixtures match these filters. Try another date, search or turn off the venue-ready filter.")
if show:
    fixture_index=st.selectbox("Open fixture dossier",range(len(show)),
        format_func=lambda i:fixture_label(show[i]),key="selected_dossier_fixture")
    fixture=show[fixture_index]
    label=fixture_label(fixture)
    st.markdown(f"#### {label}")
    st.write("Competition ID:",str(fixture.get("competition_id") or "Unavailable"))
    st.write("Venue xG:",venue_readiness(fixture,team_rows).get("status") if team_rows else "Unavailable")
    if fixture in ready and recent_rows:
        dossier=venue_dossier(fixture,recent_rows,as_of=day.isoformat())
        st.markdown("**Venue forensic snapshot**")
        if dossier["teams"]:
            st.dataframe([{"Team":v["team"],"Venue":v["venue"].title(),
                "Sample":v["matches"],"xG for":round(v["xg_for"],2),
                "xG against":round(v["xg_against"],2),
                "xG difference":round(v["xg_difference"],2),
                "Latest match":v["latest"]}
                for v in dossier["teams"].values()],hide_index=True,use_container_width=True)
        for warning in dossier["warnings"]:
            st.warning(warning)
        st.caption("Venue aggregates from stored historical match data; not opponent-adjusted, and not a substitute for recent form, referee, corners or cards analysis.")
        provenance=baseline_input_audit(fixture,recent_rows,day.isoformat())
        for warning in provenance["warnings"]:
            st.warning("Input provenance: "+warning)
        st.caption("Venue aggregates have not been reconstructed point-in-time. Historical results are not valid backtests.")
        research=baseline(fixture,recent_rows) if provenance["eligible_for_current_pricing"] else None
        if research:
            st.write(f'Pre-match baseline xG: home **{research["home_xg"]:.2f}**, away **{research["away_xg"]:.2f}**')
            st.write(f'Mechanical pre-match Over 2.5 probability: **{research["over_2_5"]*100:.1f}%**')
            st.caption(f'Home venue sample: {research["home_n"]}; away venue sample: {research["away_n"]}. Simple Poisson baseline, not calibrated fair odds.')
            with st.container(border=True):
                st.markdown("**Pre-match research pricing**")
                prices=price_goals(research["home_xg"],research["away_xg"])
                market_labels={"home_win":"Home win","draw":"Draw","away_win":"Away win",
                               "over_1_5":"Over 1.5","under_1_5":"Under 1.5",
                               "over_2_5":"Over 2.5","under_2_5":"Under 2.5",
                               "btts_yes":"BTTS Yes","btts_no":"BTTS No"}
                st.dataframe([{"Market":market_labels[k],
                               "Probability":f"{prices['probabilities'][k]*100:.1f}%",
                               "Research decimal":f"{prices['decimal_prices'][k]:.2f}" if prices["decimal_prices"][k] is not None else "N/A"}
                              for k in market_labels],hide_index=True,use_container_width=True)
                st.write("**Most likely correct scores**")
                st.dataframe([{"Score":s["score"],"Probability":f'{s["probability"]*100:.1f}%',
                               "Research decimal":f'{s["decimal_price"]:.2f}'}
                              for s in prices["top_scores"][:5]],hide_index=True,use_container_width=True)
                st.caption(f'Independent-Poisson research baseline. Unmodelled score-grid mass: {prices["missing_mass"]*100:.4f}%. Not calibrated; no actual market odds.')
                st.markdown("**Asian lines — model research prices**")
                total_line=st.selectbox("Asian total goals",[1.5,1.75,2.0,2.25,2.5,2.75,3.0,3.25,3.5],index=4,
                                        key=f"total_{fixture.get('id') or label}")
                handicap_line=st.selectbox("Home Asian handicap",[-2.0,-1.75,-1.5,-1.25,-1.0,-0.75,-0.5,-0.25,0.0,0.25,0.5,0.75,1.0,1.25,1.5,1.75,2.0],
                                           index=8,key=f"handicap_{fixture.get('id') or label}")
                asian_rows=[]
                for market,side,line in [("total","over",total_line),("total","under",total_line),
                                          ("handicap","home",handicap_line),
                                          ("handicap","away",-handicap_line)]:
                    p=asian_market(research["home_xg"],research["away_xg"],market,line,side)
                    asian_rows.append({"Market":f"{side.title()} {line:+g}" if market=="handicap" else f"{side.title()} {line:g}",
                                       "Research decimal":f'{p["fair_decimal"]:.2f}' if p["fair_decimal"] else "N/A",
                                       "Stake won":f'{p["win_stake"]*100:.1f}%',
                                       "Stake pushed":f'{p["push_stake"]*100:.1f}%'})
                st.dataframe(asian_rows,hide_index=True,use_container_width=True)
                st.caption("Quarter-lines settle as two equal half-stakes. Handicap is added to the named team's score; away handicap is the opposite of the selected home line. Not bookmaker prices.")
                st.markdown("**Compare an observed market quote**")
                st.caption("Manual quote entry only. No bookmaker feed is connected and this baseline has not been calibrated.")
                options=list(market_labels)+[f"asian_{i}" for i in range(len(asian_rows))]
                quote_key=st.selectbox("Market for comparison",options,
                    format_func=lambda k:market_labels[k] if k in market_labels else asian_rows[int(k.split("_")[1])]["Market"],
                    key="dash_quote_market")
                quoted=st.number_input("Observed decimal odds",min_value=1.01,max_value=1000.0,
                    value=2.0,step=0.05,key="dash_quote_odds")
                fee=st.number_input("Commission on winnings (%)",min_value=0.0,max_value=20.0,
                    value=0.0,step=0.5,key="dash_quote_fee")
                if quote_key in market_labels:
                    probability=prices["probabilities"][quote_key]
                    win_stake,lose_stake,push_stake=probability,1-probability,0.0
                else:
                    idx=int(quote_key.split("_")[1])
                    m,s,l=[("total","over",total_line),("total","under",total_line),
                           ("handicap","home",handicap_line),("handicap","away",-handicap_line)][idx]
                    settlement=asian_market(research["home_xg"],research["away_xg"],m,l,s)
                    win_stake=settlement["win_stake"]
                    lose_stake=settlement["lose_stake"]
                    push_stake=settlement["push_stake"]
                comparison=compare_quote(quoted,win_stake,lose_stake,push_stake,fee/100)
                st.write(f'Mechanical break-even decimal: **{comparison["break_even_decimal"]:.2f}**' if comparison["break_even_decimal"] else "No winning settlement probability")
                st.write(f'Mechanical expected return per £1 staked: **{comparison["expected_roi"]*100:+.2f}%**')
                st.warning("Scenario calculation only — not a verified value alert. Requires independently calibrated probabilities, genuine timestamped odds and trading-cost checks.")
                snapshot=build_snapshot(
                    label,day.isoformat(),fixture.get("competition_id") or "",
                    research,dossier,prices,
                    {"total_line":total_line,"home_handicap":handicap_line,"rows":asian_rows},
                    observed_quote={"source":"manual_user_entry","market":quote_key,
                        "decimal_odds":quoted,"commission_percent":fee,
                        "mechanical_comparison":comparison})
                if not snapshot["model"]["no_known_future_observations"]:
                    st.warning("Snapshot contains venue observations dated after this fixture.")
                st.caption("Snapshot is not point-in-time backtest verified; the latest-date check alone cannot establish historical data availability.")
                st.download_button("Export complete fixture research snapshot (JSON)",
                    data=snapshot_json(snapshot),file_name="starlizard_fixture_snapshot.json",
                    mime="application/json",key="dash_snapshot_export")



    st.caption("Live halftime state and market odds: not yet connected. No value inference.")
st.divider()
st.subheader("Halftime scenario lab")
st.caption("Select a venue-ready fixture and enter its observed halftime score and xG. No live halftime observations are assumed.")
if ready and recent_rows:
    choices=[]
    for f in ready:
        b=baseline(f,recent_rows)
        if b: choices.append((f,b))
    if choices:
        preferred=next((i for i,(f,_) in enumerate(choices) if show and f==show[fixture_index]),0)
        index=st.selectbox("Fixture for halftime scenario",range(len(choices)),index=preferred,
            format_func=lambda i:fixture_label(choices[i][0]))
        selected,prior=choices[index]
        st.write(f'Pre-match venue xG baseline: **{prior["home_xg"]:.2f} – {prior["away_xg"]:.2f}**')
        left,right=st.columns(2)
        with left:
            h_goals=st.number_input("Home HT goals",0,10,0,key="dash_hg")
            h_xg=st.number_input("Home HT xG observed",0.0,8.0,0.8,0.05,key="dash_hx")
        with right:
            a_goals=st.number_input("Away HT goals",0,10,0,key="dash_ag")
            a_xg=st.number_input("Away HT xG observed",0.0,8.0,0.6,0.05,key="dash_ax")
        share=st.slider("Second-half goal share (assumed)",0.35,0.70,0.50,0.01,key="dash_share")
        adjustment=st.slider("Exploratory xG redistribution",0.0,1.0,0.0,0.05,key="dash_adj")
        state=(str(selected.get("id") or fixture_label(selected)),h_goals,a_goals,h_xg,a_xg,share,adjustment)
        if st.session_state.get("dashboard_state")!=state:
            st.session_state.pop("dashboard_scenario",None)
            st.session_state.pop("dashboard_hist_result",None)
        if st.button("Calculate fixture halftime scenario",type="primary"):
            try:
                st.session_state["dashboard_scenario"]=second_half_scenario(
                    prior["home_xg"],prior["away_xg"],h_xg,a_xg,h_goals,a_goals,share,adjustment)
                st.session_state["dashboard_state"]=state
            except Exception as exc:
                st.error("Scenario unavailable: "+type(exc).__name__)
        scenario=st.session_state.get("dashboard_scenario")
        if scenario:
            st.caption(f'Scenario second-half goal intensity: home {scenario["home_2h_mu"]:.2f}, away {scenario["away_2h_mu"]:.2f}.')
            for outcome,probability in scenario["probabilities"].items():
                if probability>0:
                    st.write(f'{outcome}: **{probability*100:.1f}%** · mechanical decimal {1/probability:.2f}')
            st.warning("Exploratory independent-Poisson scenario only. Not calibrated, not verified value, and no actual bookmaker odds.")
        st.markdown("#### Historical halftime cross-check")
        st.caption("Compare this exact halftime score and approximate xG with actual historical second-half outcomes. Earlier and later periods are shown separately.")
        outcome=st.selectbox("Historical second-half outcome",[
            "Second half: at least 1 goal","Second half: at least 2 goals",
            "Home scores in second half","Away scores in second half",
            "Home wins second half","Away wins second half",
            "Both teams score in second half"],key="dash_hist_outcome")
        tolerance=st.slider("Historical xG tolerance per team",0.1,1.5,0.5,0.1,key="dash_hist_tol")
        hist_state=(state,outcome,tolerance)
        if st.session_state.get("dashboard_hist_state")!=hist_state:
            st.session_state.pop("dashboard_hist_result",None)
        if st.button("Check historical halftime outcomes"):
            try:
                rows=halftime_sample()
                st.session_state["dashboard_hist_result"]=snapshot_research(
                    rows,int(h_goals),int(a_goals),float(h_xg),float(a_xg),outcome,tolerance)
                st.session_state["dashboard_hist_state"]=hist_state
            except Exception as exc:
                st.error("Historical query unavailable: "+type(exc).__name__)
        hist=st.session_state.get("dashboard_hist_result")
        if hist:
            if hist.get("status")=="Research estimate available":
                m,n=st.columns(2)
                m.metric("Earlier historical frequency",f'{hist["train_rate"]*100:.1f}%')
                n.metric("Later historical frequency",f'{hist["later_rate"]*100:.1f}%')
                st.caption(f'Earlier: {hist["train_hits"]}/{hist["train_n"]}; later: {hist["later_hits"]}/{hist["later_n"]}; date cutoff {hist["cutoff"]}. Descriptive only.')
                if scenario and outcome in {"Second half: at least 1 goal","Second half: at least 2 goals","Home scores in second half","Away scores in second half","Home wins second half","Away wins second half","Both teams score in second half"}:
                    key_map={"Second half: at least 1 goal":"2H at least 1 goals",
                        "Second half: at least 2 goals":"2H at least 2 goals",
                        "Home scores in second half":"Home scores 2H",
                        "Away scores in second half":"Away scores 2H",
                        "Home wins second half":"Home wins 2H",
                        "Away wins second half":"Away wins 2H",
                        "Both teams score in second half":"Both score 2H"}
                    model_p=scenario["probabilities"][key_map[outcome]]
                    st.write(f'Mechanical scenario: **{model_p*100:.1f}%**; later-period observed: **{hist["later_rate"]*100:.1f}%**.')
                    st.caption("Not a matched backtest: the historical comparison uses a broader pooled match sample, not this fixture's model predictions.")
            else:
                st.info(hist["status"])
                st.caption(f'Earlier matching matches: {hist.get("train_n",0)}; later: {hist.get("later_n",0)}. Try a wider tolerance.')

    else:
        st.info("No venue-ready fixture has a matching recent-xG baseline.")
else:
    st.info("Halftime workspace needs a venue-ready fixture and recent-xG data.")
st.divider()
st.subheader("Audited next-goal research")
st.caption("Three-way outcomes checked against scoring events and final scores for trailing-at-HT matches. Separate VAR anomaly audit remains outstanding.")
with st.expander("Explore trailing-team next-goal history"):
    xg_floor=st.slider("Trailing team's HT xG minimum",0.0,2.0,0.2,0.05,key="ng_xg")
    deficit=st.selectbox("Halftime deficit",[1,2,3],key="ng_deficit")
    side=st.selectbox("Trailing team location",["both","home","away"],key="ng_side")
    if st.button("Analyse next-goal history"):
        try:
            records=labelled_next_goal_rows()
            result=trailing_three_way_summary(records,xg_floor,deficit,side)
            st.metric("Qualifying historical matches",result["n"])
            if result["n"]:
                st.write(f'Trailing team first: **{result["trailing_rate"]*100:.1f}%** ({result["trailing_first"]}/{result["n"]})')
                st.write(f'Leading team first: **{result["leader_rate"]*100:.1f}%** ({result["leader_first"]}/{result["n"]})')
                st.write(f'No second-half goal: **{result["no_goal_rate"]*100:.1f}%** ({result["no_goal"]}/{result["n"]})')
                st.caption("Observed three-way frequencies only. Not fixture-calibrated fair odds; separate VAR anomaly audit remains outstanding.")
                holdout=trailing_three_way_holdout(records,xg_floor,deficit,side)
                if holdout["status"]=="ok":
                    earlier,later=holdout["train"],holdout["later"]
                    st.markdown("**Chronological stability check**")
                    st.caption(f'Earlier matches before {holdout["cutoff"]}; later matches from this date onward. Match dates are never split between periods.')
                    for label,group in [("Earlier",earlier),("Later",later)]:
                        if group["n"]:
                            st.write(f'{label} ({group["n"]}): trailing first **{group["trailing_rate"]*100:.1f}%**, leader first **{group["leader_rate"]*100:.1f}%**, no goal **{group["no_goal_rate"]*100:.1f}%**')
                        else:
                            st.write(f'{label}: no qualifying matches')
                    st.caption("This is a chronological descriptive comparison, not an odds-based betting backtest.")
                    quality=three_way_holdout_scores(records,xg_floor,deficit,side)
                    if quality["status"]=="ok":
                        st.markdown("**Later-period probability quality**")
                        lcol,rcol=st.columns(2)
                        lcol.metric("Multiclass Brier (lower better)",f'{quality["brier"]:.3f}')
                        rcol.metric("Log loss (lower better)",f'{quality["log_loss"]:.3f}')
                        st.write(f'Baseline Brier: **{quality["baseline_brier"]:.3f}**, baseline log loss: **{quality["baseline_log_loss"]:.3f}** (trained on {quality["baseline_n"]} earlier matches).')
                        st.write(f'Brier improvement versus baseline: **{quality["brier_improvement"]:+.3f}** (positive is better).')
                        if quality["brier_improvement"]<=0:
                            st.warning("Conditional pattern did not outperform the simple earlier-only baseline on later matches.")
                        st.caption(f'Earlier rates frozen before {quality["cutoff"]}; evaluated against {quality["later_n"]} later matches. Baseline uses earlier matches with the same deficit, ignoring xG and location filters. Neither is a betting backtest.')
                    else:
                        st.caption("Probability scoring unavailable: "+quality["status"]+".")
                else:
                    st.info("Not enough distinct match dates for a chronological comparison.")
            else:
                st.info("No observations match these filters.")
        except Exception as exc:
            st.error("Next-goal research temporarily unavailable: "+type(exc).__name__)
st.divider()
st.subheader("Model build status")
st.write("**Working:** fixture discovery, historical coverage, venue sample checks, halftime outcome research, conditional scenario estimates.")
st.write("**In progress:** fixture-calibrated halftime probabilities, verified goal sequence markets, real-time halftime feed, timestamped bookmaker/exchange odds and validated alert ranking.")
st.caption("No opportunities are labelled value until live prices and prospective validation are available.")
