"""Mobile-first halftime scanner. Read-only API; existing pricing page stays unchanged."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import joblib
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import streamlit as st
from lightweight_fixture_feed import get_key, fixtures_for_day, fixture_label, team_name, API_BASE
from statsapi_refresh import LEAGUES
from fixture_live_status import fixture_status

st.set_page_config(page_title="The Match Matrix | Live Scanner", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {background:linear-gradient(160deg,rgba(218,41,28,.13),transparent 340px)}
h1,h2,h3{letter-spacing:-.025em} h1{color:#da291c!important}
div.stButton>button[kind="primary"]{background-color:#da291c;color:white}
.hero{background:linear-gradient(110deg,#8b1114,#da291c 72%,#a41918);color:white;
border-left:6px solid #fbe122;border-bottom:3px solid #da291c;
padding:18px 16px;border-radius:10px;margin-bottom:14px}
.hero h2{color:white!important;margin:0 0 14px!important;
font-size:clamp(1.55rem,6.2vw,2.7rem)!important;line-height:1.18!important;
letter-spacing:-.025em;white-space:normal}
.hero-content{display:grid;grid-template-columns:minmax(0,1fr) minmax(140px,48%);
align-items:center;gap:10px}
.hero p{color:#fff4df;margin:0;font-size:clamp(.82rem,2.7vw,1rem);
line-height:1.6;font-weight:600;overflow-wrap:normal}
.hero img{display:block;width:100%;max-width:245px;height:auto;
max-height:245px;object-fit:contain;justify-self:center}
@media(max-width:420px){.hero{padding:16px 12px}
.hero h2{font-size:1.55rem!important;margin-bottom:12px!important}
.hero-content{grid-template-columns:minmax(0,1fr) minmax(150px,49%);gap:8px}
.hero p{font-size:.79rem;line-height:1.5}
.hero img{max-height:205px}}
</style>
<div class="hero"><h2>THE MATCH MATRIX</h2><div class="hero-content"><p>HALF-TIME BETTING INTELLIGENCE<br>GOALS · NEXT GOAL<br>SECOND-HALF RESULT</p><img src="https://en.wikinews.org/wiki/Special:FilePath/Manchester_United_F.C._logo.svg" alt="Manchester United crest" /></div></div>
""",unsafe_allow_html=True)
st.markdown("""<style>
/* Keep the title BELOW Streamlit's fixed Share/Edit toolbar on phones. */
.block-container{max-width:1080px;padding-top:5rem!important}
@media(max-width:640px){.block-container{padding:5rem .6rem 3rem!important}}
div[data-testid="stNumberInput"] label p{font-size:.78rem}
h2,h3{font-size:1.15rem!important}
</style>""",unsafe_allow_html=True)
with st.expander("Other analysis tools",expanded=False):
    st.page_link("pages/96_Legacy_Match_Analysis.py",label="Original match analysis (archive)")
    st.page_link("pages/95_Half_Time_Fair_Odds.py",label="Original halftime calculator (archive)")
key = get_key()
if not key:
    st.error("Missing TheStatsAPI key in Streamlit secrets.")
    st.stop()
day = st.date_input("Match date", datetime.now(ZoneInfo("Europe/London")).date(),
                    min_value=datetime.now(ZoneInfo("Europe/London")).date()-timedelta(days=7),
                    max_value=datetime.now(ZoneInfo("Europe/London")).date()+timedelta(days=14))
try:
    all_fixtures = fixtures_for_day(key, day.isoformat())
except Exception as exc:
    st.error(f"Fixture feed unavailable: {type(exc).__name__}")
    st.stop()
allowed = set(LEAGUES.values())
def comp_id(f):
    c=f.get("competition") or {}
    return str(f.get("competition_id") or (c.get("id") if isinstance(c,dict) else "") or "")
fixtures = sorted([f for f in all_fixtures if comp_id(f) in allowed], key=fixture_label)

if not fixtures:
    st.info("No selected-league fixtures today.")
    st.stop()
status_filter = st.radio("Show", ["All", "Half-time / live", "Finished"], horizontal=True)
def phase(f):
    status = fixture_status(f)
    if status == "Live": return "Half-time / live"
    if status == "Finished / not active": return "Finished"
    return "Scheduled / unknown"
visible=[f for f in fixtures if status_filter=="All" or phase(f)==status_filter]

labels=[fixture_label(f) for f in visible]
if not visible:
    st.info("No fixtures in this filter.")
    st.stop()
with st.expander(f"Fixture list ({len(visible)})",expanded=False):
    st.dataframe(pd.DataFrame([{"Fixture":fixture_label(f),"Phase":phase(f)} for f in visible]),
                 hide_index=True, use_container_width=True, height=min(300,38*(len(visible)+1)))
selected=st.selectbox("Open a match", range(len(visible)), format_func=lambda i:labels[i])
f=visible[selected]
mid=str(f.get("id") or "")
st.subheader(f"{team_name(f,'home')} v {team_name(f,'away')}")
price_slot=st.container()
@st.cache_data(ttl=90, show_spinner=False)
def fetch_stats(api_key,match_id):
    r=requests.get(f"{API_BASE}/football/matches/{match_id}/stats",
        headers={"Authorization":f"Bearer {api_key}"},timeout=25)
    r.raise_for_status()
    return r.json().get("data") or {}
@st.cache_resource(show_spinner=False)
def model_bundle():
    model_path = Path(__file__).resolve().parents[1] / "model_artifacts" / "halftime_second_half_models.joblib"
    return joblib.load(model_path)
# Prefer the permanently archived first-half snapshot before making a live API call.
@st.cache_data(ttl=120,show_spinner=False)
def stored_first_half(match_id):
    import os
    from supabase import create_client
    url=os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    secret=os.environ.get("SUPABASE_SECRET_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")
    if not url or not secret:return None
    rows=(create_client(url,secret).table("match_matrix_halftime_stats")
          .select("stats_payload,first_half_stats,half_time_score,observed_at")
          .eq("match_id",match_id).limit(1).execute().data or [])
    return rows[0] if rows else None
try:
    archived=stored_first_half(mid)
except Exception as exc:
    archived=None
    st.caption("Saved halftime statistics lookup unavailable: "+type(exc).__name__)
if archived:
    # Convert the archived live-stats snapshot to the scanner's existing
    # first_half overview shape. Preserve the exact archived raw response in DB.
    raw=archived.get("stats_payload") or {}
    live_stats=(raw.get("data") or raw).get("stats") or {}
    adapted={"overview":{metric:{"first_half":pair.get("all")}
        for metric,pair in live_stats.items()
        if isinstance(pair,dict) and isinstance(pair.get("all"),dict)}}
    for metric,pair in (archived.get("first_half_stats") or {}).items():
        if isinstance(pair,dict) and all(pair.get(side) is not None for side in ("home","away")):
            adapted["overview"][metric]={"first_half":pair}
    for metric,name in (("expected_goals","hx"),("total_shots","shots"),("shots_on_target","sot"),("corner_kicks","corners"),("red_cards","red")):
        for side in ("home","away"):
            v=((adapted["overview"].get(metric) or {}).get("first_half") or {}).get(side)
            widget=f"sc_{name}_{side}_{mid}" if name!="hx" else f"sc_{'hx' if side=='home' else 'ax'}_{mid}"
            if v is not None and st.session_state.get(widget) is None:
                try: st.session_state[widget]=float(v) if name=="hx" else int(float(v))
                except (ValueError,TypeError): pass
    st.session_state["scanner_stats"]=adapted
    st.session_state["scanner_stats_id"]=mid
    
    saved_score=archived.get("half_time_score") or {}
    for side,short in (("home","hg"),("away","ag")):
        if saved_score.get(side) is not None and st.session_state.get(f"sc_{short}_{mid}") is None:
            st.session_state[f"sc_{short}_{mid}"]=int(saved_score[side])
# Automatically request verified first-half stats only for an explicitly
# halftime fixture. Cached per match to avoid repeated API calls on reruns.
raw_status=str(f.get("status") or "").lower().replace(" ","_").replace("-","_")
is_halftime=raw_status in {"ht","half_time","halftime"}
if False and is_halftime and not archived and st.session_state.get("scanner_auto_ht_id") != mid:
    st.session_state["scanner_auto_ht_id"]=mid
    try:
        st.session_state["scanner_stats"]=fetch_stats(key,mid)
        st.session_state["scanner_stats_id"]=mid
        st.caption("First-half statistics fetched automatically at confirmed halftime.")
    except Exception as exc:
        st.session_state["scanner_stats"]={}
        st.session_state["scanner_stats_id"]=mid
        st.warning("Automatic halftime statistics unavailable: "+type(exc).__name__)
if not archived and st.button("Fetch first-half stats",type="primary",use_container_width=True):
    fetch_stats.clear()
    st.session_state["scanner_stats_id"]=mid
    try:
        st.session_state["scanner_stats"]=fetch_stats(key,mid)
        # Streamlit widget keys persist between reruns: explicitly hydrate empty fields.
        payload=st.session_state["scanner_stats"]
        ov=payload.get("overview",{}) if isinstance(payload,dict) else {}
        for metric,name in (("expected_goals","hx"),("total_shots","shots"),("shots_on_target","sot"),("corner_kicks","corners"),("red_cards","red")):
            half=(ov.get(metric) or {}).get("first_half") or {}
            for side in ("home","away"):
                v=half.get(side) if isinstance(half,dict) else None
                widget=f"sc_{name}_{side}_{mid}" if name!="hx" else f"sc_{'hx' if side=='home' else 'ax'}_{mid}"
                if v is not None and st.session_state.get(widget) is None:
                    try:st.session_state[widget]=float(v) if name=="hx" else int(float(v))
                    except (ValueError,TypeError):pass
    except Exception as exc:
        st.session_state["scanner_stats"]={}
        st.error(f"Stats unavailable: {type(exc).__name__}. No substitute values used.")
data=st.session_state.get("scanner_stats",{}) if st.session_state.get("scanner_stats_id")==mid else {}
overview=data.get("overview",{}) if isinstance(data,dict) else {}
def half_stat(name,side):
    block=(overview.get(name) or {}).get("first_half") or {}
    value=block.get(side) if isinstance(block,dict) else None
    try: return float(value) if value is not None else None
    except (ValueError,TypeError): return None
def score_half(side):
    score=f.get("score") or {}
    # Do not treat current score as halftime score.
    for container in (score.get("half_time"),score.get("halftime"),score.get("halfTime"),f.get("half_time_score"),f.get("halfTime")):
        if isinstance(container,dict) and container.get(side) is not None:
            try:return int(container[side])
            except (ValueError,TypeError):pass
    return None
# Never use the current fixture score as a halftime score.
# A verified explicit halftime score may be supplied by the fixture feed.
for side,short in (("home","hg"),("away","ag")):
    widget=f"sc_{short}_{mid}"
    verified=score_half(side)
    if verified is not None and st.session_state.get(widget) is None:
        st.session_state[widget]=verified
if data:
    found=sum(half_stat(m,side) is not None for m in ("expected_goals","total_shots","shots_on_target","corner_kicks","red_cards") for side in ("home","away"))
    
    if found==0:
        st.warning("No recognised first-half fields in this response. We must inspect its structure before claiming automatic population.")
else:
    st.info("Fetch stats when the match reaches halftime. Blank fields mean unverified data.")
missing_red=[side for side in ("home","away") if half_stat("red_cards",side) is None and st.session_state.get(f"sc_red_{side}_{mid}") is None]
if missing_red:
    st.warning("Red-card counts were omitted by the feed. Confirm the actual halftime counts below; do not assume zero.")
    if st.button("Confirm no first-half red cards",key=f"confirm_no_red_{mid}",use_container_width=True):
        for side in missing_red:
            st.session_state[f"sc_red_{side}_{mid}"]=0
with st.expander("Edit missing half-time facts",expanded=False):
    st.caption("Enter the confirmed half-time score; current live score is not used as a substitute.")
    a,b=st.columns(2)
    with a:
        hg=st.number_input("Home HT goals",0,12,value=score_half("home"),placeholder="Required",key=f"sc_hg_{mid}")
        hx=st.number_input("Home HT xG",0.0,10.0,value=half_stat("expected_goals","home"),placeholder="Required",key=f"sc_hx_{mid}")
    with b:
        ag=st.number_input("Away HT goals",0,12,value=score_half("away"),placeholder="Required",key=f"sc_ag_{mid}")
        ax=st.number_input("Away HT xG",0.0,10.0,value=half_stat("expected_goals","away"),placeholder="Required",key=f"sc_ax_{mid}")
    fields={}
    for name,metric in [("shots","total_shots"),("sot","shots_on_target"),("corners","corner_kicks"),("red","red_cards")]:
        c1,c2=st.columns(2)
        for side,col in (("home",c1),("away",c2)):
            with col:
                v=half_stat(metric,side)
                fields[(name,side)]=st.number_input(f"{side.title()} {name}",0,80,value=int(v) if v is not None else None,
                                                    placeholder="Required",key=f"sc_{name}_{side}_{mid}")
# Historical stored pre-match odds: never substitute halftime/live prices.
@st.cache_data(ttl=300,show_spinner=False)
def stored_prematch(match_id):
    import os
    from supabase import create_client
    url=os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    secret=os.environ.get("SUPABASE_SECRET_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")
    if not url or not secret:return None
    db=create_client(url,secret)
    # Snapshot and historical stores are independent: one failing query must
    # never hide a valid price from the other source.
    errors = []
    try:
        snapshots=(db.table("ht_odds_trial_20261120")
                   .select("bookmaker,markets,observed_at")
                   .eq("match_id",match_id)
                   .eq("snapshot_kind","prematch_within_20m")
                   .order("observed_at",desc=True).limit(12).execute().data or [])
    except Exception as exc:
        snapshots=[]
        errors.append("snapshot: "+type(exc).__name__+" "+str(exc)[:220])
    for preferred in ("Bet365","Betfair Exchange","William Hill","Pinnacle"):
        for row in snapshots:
            if str(row.get("bookmaker") or "").casefold()!=preferred.casefold():continue
            market=(row.get("markets") or {}).get("match_odds") or {}
            try:
                prices=[float((market.get(side) or {}).get("last_seen")) for side in ("home","draw","away")]
                if all(p>1 for p in prices):
                    return (prices,preferred+" · prematch snapshot "+str(row.get("observed_at") or ""))
            except (TypeError,ValueError):pass
    try:
        records=(db.table("historical_match_odds").select("odds_payload")
                 .eq("match_id",match_id).limit(1).execute().data or [])
    except Exception as exc:
        records=[]
        errors.append("historical: "+type(exc).__name__+" "+str(exc)[:220])
    if records:
        payload=records[0].get("odds_payload") or {}
        bookmakers=(payload.get("data") or {}).get("bookmakers") or []
        for preferred in ("Bet365","Betfair Exchange","William Hill","Pinnacle"):
            for book in bookmakers:
                if str(book.get("bookmaker") or "").casefold()!=preferred.casefold():continue
                market=(book.get("markets") or {}).get("match_odds") or {}
                try:
                    prices=[float((market.get(side) or {}).get("last_seen")) for side in ("home","draw","away")]
                    if all(p>1 for p in prices):return (prices,preferred)
                except (ValueError,TypeError):pass
    if errors:
        # No credentials or authorization headers are included in these messages.
        st.session_state["scanner_odds_lookup_error"]="; ".join(errors)
    return None

try:
    stored=stored_prematch(mid)
except Exception as exc:
    stored=None
    st.caption("Stored pre-match odds lookup unavailable: "+type(exc).__name__+" "+str(exc)[:220])
if not stored and st.session_state.get("scanner_odds_lookup_error"):
    with st.expander("Odds database diagnostic",expanded=False):
        st.code(st.session_state["scanner_odds_lookup_error"])
if stored:
    st.session_state.pop("scanner_odds_lookup_error",None)
    prices,source=stored
    for side,v in zip(("hp","dp","ap"),prices):
        widget=f"sc_{side}_{mid}"
        if st.session_state.get(widget) is None:st.session_state[widget]=v
    
with st.expander("Edit missing pre-match 1X2 odds",expanded=False):
    st.caption("Only enter genuine pre-kickoff prices; not live or halftime odds.")
    c1,c2,c3=st.columns(3)
    with c1:hp=st.number_input("Home",min_value=1.01,value=None,placeholder="Odds",key=f"sc_hp_{mid}")
    with c2:dp=st.number_input("Draw",min_value=1.01,value=None,placeholder="Odds",key=f"sc_dp_{mid}")
    with c3:ap=st.number_input("Away",min_value=1.01,value=None,placeholder="Odds",key=f"sc_ap_{mid}")

@st.cache_data(ttl=90,show_spinner=False)
def stored_halftime_odds(match_id):
    import os
    from supabase import create_client
    url=os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    secret=os.environ.get("SUPABASE_SECRET_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")
    if not url or not secret:return []
    return (create_client(url,secret).table("match_matrix_halftime_odds")
            .select("bookmaker,markets,observed_at,provenance")
            .eq("match_id",match_id).execute().data or [])


try:
    ht_books=stored_halftime_odds(mid)
except Exception as exc:
    ht_books=[]
    st.caption("Half-time odds database unavailable: "+type(exc).__name__)
with st.expander("Bookmaker details",expanded=False):
    if ht_books:
        display=[]
        for book in ht_books:
            market=(book.get("markets") or {}).get("match_odds") or {}
            prices={}
            for side in ("home","draw","away"):
                item=market.get(side) or {}
                if isinstance(item,dict):
                    prices[side]=item.get("live") or item.get("price") or item.get("current") or item.get("decimal")
            display.append({"Bookmaker":book.get("bookmaker"),
                            "Captured (UTC)":str(book.get("observed_at") or "")[:19],
                            "Home":prices.get("home"),"Draw":prices.get("draw"),
                            "Away":prices.get("away")})
        st.dataframe(pd.DataFrame(display),hide_index=True,use_container_width=True)
        st.caption("Source: dedicated /odds/live endpoint for new captures. Blank prices mean the response format needs inspection; pre-match last_seen is never substituted.")
        with st.expander("Inspect raw halftime odds response",expanded=False):
            st.json([{"bookmaker":b.get("bookmaker"),"provenance":b.get("provenance"),"markets":b.get("markets")} for b in ht_books])
        st.warning("Live endpoint requested, but quote freshness and market mapping are not yet validated. No automatic value claims.")
    else:
        st.caption("No bookmaker odds captured at halftime for this match yet.")
    
required=[hg,ag,hx,ax,hp,dp,ap,*fields.values()]
if any(v is None for v in required):
    st.warning("Missing verified inputs: "+", ".join(name for name,v in zip(["Home HT goals","Away HT goals","Home xG","Away xG","Home pre-match odds","Draw pre-match odds","Away pre-match odds",*[f"{side} {name}" for name,side in fields]],required) if v is None)+". No fair prices calculated.")
elif fields[("sot","home")]>fields[("shots","home")] or fields[("sot","away")]>fields[("shots","away")]:
    st.error("Shots on target cannot exceed total shots.")
else:
    try:
        model=model_bundle()
        inv=np.array([1/hp,1/dp,1/ap],dtype=float)
        ph,pdraw,pa=inv/inv.sum()
        diff=hg-ag
        feat={"home_ht_goals":hg,"away_ht_goals":ag,"p_home":ph,"p_draw":pdraw,"p_away":pa,
              "ht_diff":diff,"ht_total":hg+ag,"score_strength":diff*(ph-pa),
              "h_shots":fields[("shots","home")],"a_shots":fields[("shots","away")],
              "h_sot":fields[("sot","home")],"a_sot":fields[("sot","away")],
              "h_corners":fields[("corners","home")],"a_corners":fields[("corners","away")],
              "h_red":fields[("red","home")],"a_red":fields[("red","away")],
              "home_ht_xg":hx,"away_ht_xg":ax}
        x=model["scaler"].transform(pd.DataFrame([feat])[model["feature_columns"]])
        raw={market:{str(k):float(v) for k,v in zip(clf.classes_,clf.predict_proba(x)[0])}
             for market,clf in model["models"].items()}
        # Match the original dashboard's reconciliation logic.
        o05=raw["over_0_5_2h"]["1"];o15=min(raw["over_1_5_2h"]["1"],o05)
        o25=min(raw["over_2_5_2h"]["1"],o15)
        nextp=raw["next_goal"]
        hshare=nextp["home"]/max(nextp["home"]+nextp["away"],1e-12)
        both=min(raw["both_score_2h"]["1"],raw["home_scores_2h"]["1"],raw["away_scores_2h"]["1"],o15)
        h=raw["home_scores_2h"]["1"];a=raw["away_scores_2h"]["1"]
        excess=max(0,h+a-both-o05)
        if excess:
            room_h=max(0,h-both);room_a=max(0,a-both)
            take_h=min(room_h,excess*room_h/max(room_h+room_a,1e-12))
            h-=take_h;a-=min(room_a,excess-take_h)
        result=raw["second_half_result"].copy()
        if result["draw"]<1-o05:
            factor=o05/max(result["home"]+result["away"],1e-12)
            result={"home":result["home"]*factor,"away":result["away"]*factor,"draw":1-o05}
        markets=[("Over 0.5 2H",o05),("Over 1.5 2H",o15),("Over 2.5 2H",o25),
                 ("Home scores 2H",h),("Away scores 2H",a),("Both score 2H",both),
                 ("Next goal home",o05*hshare),("Next goal away",o05*(1-hshare)),
                 ("No next goal",1-o05),("2H home win",result["home"]),
                 ("2H draw",result["draw"]),("2H away win",result["away"])]

        # Only compare identical second-half markets. Never confuse full-match
        # totals or match 1X2 with second-half-specific markets.
        def live_quote(book,market_name):
            if book.get("provenance")!="live_odds_endpoint":
                return None
            all_markets=book.get("markets") or {}
            mappings={
                "Over 0.5 2H":("second_half_total_goals","0.5","over"),
                "Over 1.5 2H":("second_half_total_goals","1.5","over"),
                "Over 2.5 2H":("second_half_total_goals","2.5","over"),
                "Both score 2H":("btts_second_half",None,"yes"),
                "2H home win":("second_half_result",None,"home"),
                "2H draw":("second_half_result",None,"draw"),
                "2H away win":("second_half_result",None,"away"),
                "Next goal home":("next_goal",None,"home"),
                "Next goal away":("next_goal",None,"away"),
                "No next goal":("next_goal",None,"none")}
            spec=mappings.get(market_name)
            if not spec:return None
            group,line,selection=spec
            block=all_markets.get(group) or {}
            if line is not None:
                block=block.get(line) or {}
                if not block and group=="second_half_total_goals" and archived:
                    score=archived.get("half_time_score") or {}
                    if score.get("home") is not None and score.get("away") is not None and int(score["home"])==hg and int(score["away"])==ag:
                        full_line=str(float(line)+hg+ag)
                        block=(all_markets.get("total_goals") or {}).get(full_line) or {}
            item=block.get(selection) if isinstance(block,dict) else None
            # Accept only an explicit quote field; never opening/last_seen.
            if not isinstance(item,dict):return None
            try:
                price=float(item.get("live"))
                return price if 1.01<=price<=1000 else None
            except (ValueError,TypeError):return None

        rows=[]
        for name,p in markets:
            fair=1/p if p>0 else None
            offers=[(float(q),str(b.get("bookmaker") or ""))
                    for b in ht_books if (q:=live_quote(b,name)) is not None]
            best_price,best_book=max(offers,key=lambda t:t[0]) if offers else (None,None)
            edge=(p*best_price-1)*100 if best_price is not None else None
            # At least 2% theoretical EV to reduce highlighting marginal noise.
            value=edge is not None and edge>=2
            rows.append({"Market":name,"Model %":f"{100*p:.1f}%",
                         "Fair odds":f"{fair:.2f}" if fair else "—",
                         "HT odds":f"{best_price:.2f}" if best_price else "—",
                         "Book":best_book or "—",
                         "Model EV":f"{edge:+.1f}%" if edge is not None else "—",
                         "Flag":"VALUE?" if value else ("—" if edge is None else "No value"),
                         "_highlight":value})
        view=pd.DataFrame(rows)[["Market","Fair odds","HT odds","Model EV","_highlight"]]
        flags=view.pop("_highlight")
        def highlight_value(row):
            styles=[""]*len(row)
            # Always distinguish the model's fair price in green.
            fair_col=row.index.get_loc("Fair odds")
            if row["Fair odds"]!="—":
                styles[fair_col]="background-color:#147d43;color:#ffffff;font-weight:700"
            # Yellow highlights potential value without obscuring green fair odds.
            if flags.iloc[row.name]:
                for field in ("HT odds","Model EV"):
                    styles[row.index.get_loc(field)]="background-color:#fbe122;color:#171717;font-weight:700"
            return styles
        with price_slot:
            st.markdown(f"**HT {hg}–{ag} · xG {hx:.2f} / {ax:.2f}**")
            st.subheader("Second-half prices")
            from html import escape
            html='<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px"><thead><tr><th style="width:40%">Market</th><th>Fair</th><th>Book</th><th>EV</th></tr></thead><tbody>'
            for row in rows:
                yellow="background:#fbe122;color:#171717;font-weight:bold" if row["_highlight"] else ""
                html+='<tr>'
                for field in ("Market","Fair odds","HT odds","Model EV"):
                    style="background:#147d43;color:white;font-weight:bold" if field=="Fair odds" else yellow if field in ("HT odds","Model EV") else ""
                    html+=f'<td style="padding:6px 3px;overflow-wrap:anywhere;{style}">{escape(row[field])}</td>'
                html+='</tr>'
            st.markdown(html+'</tbody></table>',unsafe_allow_html=True)
            st.caption("Green: fair odds. Yellow: model EV ≥2%. Archived quote freshness and exchange commission not verified.")
            with st.expander("Price sources",expanded=False):
                st.dataframe(pd.DataFrame(rows)[["Market","Book","HT odds","Model %"]],hide_index=True,use_container_width=True)
    except Exception as exc:
        st.error(f"Pricing unavailable: {type(exc).__name__}: {str(exc)[:130]}")

