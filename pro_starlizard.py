"""PRO STARLIZARD — single-click database-backed match analysis."""
import math
import pandas as pd
import streamlit as st
from supabase import create_client
from statsapi_refresh import LEAGUES,settings,refresh

st.set_page_config(page_title="PRO STARLIZARD | Match Intelligence",page_icon="⚽",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>
.stApp{background:linear-gradient(145deg,#0a1220,#101f31);color:#eaf2f9}
.block-container{max-width:1080px;padding-top:1.1rem}
[data-testid="stSidebar"],[data-testid="stSidebarNav"]{display:none}
.stButton button[kind="primary"]{background:#35bba5;color:#061b21;border:0;font-weight:800}
@media(max-width:640px){.block-container{padding:.8rem .6rem 3rem}}
</style>""",unsafe_allow_html=True)
try:st.image("pro_starlizard_header_correct-1.png",use_container_width=True)
except Exception:pass
st.title("⚽ PRO STARLIZARD")
st.caption("Enter a fixture. We retrieve individual match records from our saved TheStatsAPI database and calculate the fair odds.")
@st.cache_data(ttl=3600,show_spinner=False)
def team_options():
    client=create_client(st.secrets["SUPABASE_URL"],st.secrets["SUPABASE_SECRET_KEY"])
    records=client.table("starlizard_team_options").select("team_name").order("team_name").limit(1000).execute().data or []
    return sorted({r["team_name"] for r in records if r.get("team_name")},key=str.casefold)

try:
    teams=team_options()
except Exception as exc:
    st.error(f"Couldn't load team choices: {exc}")
    st.stop()
if not teams:
    st.warning("No team names found in the saved database.")
    st.stop()
c1,c2=st.columns(2)
with c1:
    home=st.selectbox("🏠 Home team",teams,index=teams.index("Manchester City") if "Manchester City" in teams else 0)
with c2:
    away=st.selectbox("✈️ Away team",teams,index=teams.index("Fulham") if "Fulham" in teams else 0)

n=st.selectbox("Recent matches per team at the relevant venue",[5,10,15,20],index=0)
cols=["Date / opponent","Goals for","Goals against","xG for","xG against","Corners for","Corners against","Yellow cards for","Yellow cards against","Shots for","Shots against","Fouls for","Fouls against"]
numeric=cols[1:]

@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"],st.secrets["SUPABASE_SECRET_KEY"])

def load_saved_team(team,venue,count):
    client=db()
    col="home_team" if venue=="home" else "away_team"
    rows=(client.table("historical_xg").select("match_id,match_date,home_team,away_team,home_goals,away_goals,home_xg,away_xg")
          .ilike(col,team.strip()).not_.is_("home_goals","null").not_.is_("away_goals","null")
          .order("match_date",desc=True).limit(count).execute().data or [])
    ids=[r["match_id"] for r in rows]
    events={}
    if ids:
        for e in (client.table("historical_match_events").select("match_id,stats_data").in_("match_id",ids).execute().data or []):
            events[e["match_id"]]=e.get("stats_data") or {}
    out=[]
    for r in rows:
        own="home" if venue=="home" else "away"
        opp="away" if venue=="home" else "home"
        s=(events.get(r["match_id"]) or {}).get("overview") or {}
        def get(key,side):
            val=((s.get(key) or {}).get("all") or {}).get(side)
            return float(val) if val is not None else None
        entry={"Date / opponent":str(r["match_date"])+" "+str(r[opp+"_team"]),"Goals for":r[own+"_goals"],"Goals against":r[opp+"_goals"],
               "xG for":r[own+"_xg"],"xG against":r[opp+"_xg"]}
        for dest,key,side in [
            ("Corners for","corner_kicks",own),("Corners against","corner_kicks",opp),
            ("Yellow cards for","yellow_cards",own),("Yellow cards against","yellow_cards",opp),
            ("Shots for","total_shots",own),("Shots against","total_shots",opp),
            ("Fouls for","fouls",own),("Fouls against","fouls",opp)]:
            entry[dest]=get(key,side)
        out.append(entry)
    return pd.DataFrame(out,columns=cols)

def load_h2h(home,away):
    rows=(db().table("historical_xg").select("match_date,home_goals,away_goals")
          .ilike("home_team",home.strip()).ilike("away_team",away.strip())
          .not_.is_("home_goals","null").not_.is_("away_goals","null")
          .order("match_date",desc=True).limit(5).execute().data or [])
    return pd.DataFrame([{"Date":r["match_date"],"Home goals":r["home_goals"],"Away goals":r["away_goals"]} for r in rows],columns=["Date","Home goals","Away goals"])

analyse=st.button("🎯 ANALYSE MATCH",type="primary",use_container_width=True)
if analyse:
    if not home.strip() or not away.strip() or home.strip().casefold()==away.strip().casefold():
        st.error("Enter two different team names.");st.stop()
    try:
        with st.spinner("Loading latest saved match records…"):
            h=load_saved_team(home,"home",n)
            a=load_saved_team(away,"away",n)
            h2h=load_h2h(home,away)
    except Exception as exc:
        st.error(f"Could not load match data: {exc}");st.stop()
    st.info(f"Loaded {len(h)} {home} home matches and {len(a)} {away} away matches. Latest saved date: "+
            str(max([str(x)[:10] for x in pd.concat([h,a])["Date / opponent"].dropna()] or ["unknown"])))
    if len(h)<3 or len(a)<3:
        st.warning("Fewer than three saved venue matches for one or both teams. Check team names or refresh the database.")
    with st.expander("View individual matches and statistics"):
        st.markdown(f"**{home} — home matches**")
        st.dataframe(h,hide_index=True,use_container_width=True)
        st.markdown(f"**{away} — away matches**")
        st.dataframe(a,hide_index=True,use_container_width=True)
    with st.expander("Last five head-to-head meetings at this ground"):
        st.dataframe(h2h,hide_index=True,use_container_width=True)
    ref=""
    ref_cards=0.0
    ref_fouls=0.0
with st.expander("🔄 Update the database from TheStatsAPI (optional)"):
    st.caption("Only use when recent results are missing. This consumes API requests.")
    league=st.selectbox("League",list(LEAGUES),key="api_league")
    days=st.selectbox("Look back (days)",[7,14,21,30],index=2)
    limit=st.selectbox("Maximum fixtures to refresh",[5,10,25],index=1)
    key,url,secret=settings()
    if not key:st.warning("TheStatsAPI key is not configured in Streamlit secrets.")
    if st.button("Refresh recent fixtures",disabled=not all((key,url,secret)),use_container_width=True):
        try:
            with st.spinner("Refreshing recent fixtures…"):report=refresh(league,days,limit)
            st.success(f"Saved {report['saved_stats']} matches · {report['api_calls']} API requests.")
            if report["errors"]:st.warning("; ".join(report["errors"][:3]))
        except Exception as exc:st.error(f"Refresh failed: {exc}")

def avg(df,key):
    v=pd.to_numeric(df[key],errors="coerce").dropna()
    return (float(v.mean()),len(v)) if len(v) else (None,0)
def expectation(df1,for1,df2,against2):
    x,n=avg(df1,for1);y,m=avg(df2,against2)
    if x is None or y is None:return None,min(n,m)
    return (x+y)/2,min(n,m)
def poisson_cdf(k,lam):
    if lam<0:return 0
    term=math.exp(-lam);total=term
    for i in range(1,k+1):
        term*=lam/i;total+=term
    return min(1.0,total)
def row(name,p,source):
    p=max(0,min(1,p))
    return {"Market":name,"Probability":f"{p:.1%}","Fair odds":f"{1/p:.2f}" if p>0 else "—","Basis":source}
if analyse:
    st.divider()
    st.header(f"{home} v {away} — Match dossier")
    stat=[]
    for label,df in [(home+" home",h),(away+" away",a)]:
        for metric in numeric:
            x,nobs=avg(df,metric)
            if x is not None:stat.append({"Team / venue":label,"Statistic":metric,"Average":round(x,2),"Matches":nobs})
    if stat:
        st.subheader("Recent form — recorded averages")
        with st.expander("See all recent averages"):
            st.dataframe(pd.DataFrame(stat),hide_index=True,use_container_width=True)
        st.caption("Recent averages are available above; the fair-odds cards below fit mobile screens.")
    else:st.warning("No numerical match data entered yet.")
    valid=h2h.dropna(subset=["Home goals","Away goals"])
    if len(valid):
        wins=int((valid["Home goals"]>valid["Away goals"]).sum())
        st.write(f"**Venue head-to-head:** {len(valid)} entered · {wins} {home} wins · {int((valid['Home goals']+valid['Away goals']>2.5).sum())} over 2.5 goals.")
    if ref:st.caption(f"Referee: {ref}")
    results=[]
    # Match result / goal prices from independent Poisson rates.
    hx,nh=expectation(h,"xG for",a,"xG against")
    ax,na=expectation(a,"xG for",h,"xG against")
    basis="xG blend"
    if hx is None or ax is None:
        hx,nh=expectation(h,"Goals for",a,"Goals against")
        ax,na=expectation(a,"Goals for",h,"Goals against")
        basis="goals blend"
    if hx is not None and ax is not None:
        st.subheader("Expected goals — simple venue-form model")
        x1,x2=st.columns(2)
        x1.metric(home,round(hx,2));x2.metric(away,round(ax,2))
        p_home=p_draw=p_away=p_btts=0
        probs1=[math.exp(-hx)*hx**i/math.factorial(i) for i in range(22)]
        probs2=[math.exp(-ax)*ax**i/math.factorial(i) for i in range(22)]
        for i,pi in enumerate(probs1):
            for j,pj in enumerate(probs2):
                if i>j:p_home+=pi*pj
                elif i==j:p_draw+=pi*pj
                else:p_away+=pi*pj
        for name,p in [("Home win",p_home),("Draw",p_draw),("Away win",p_away)]:results.append(row(name,p,basis))
        for line in [1.5,2.5,3.5,4.5]:results.append(row(f"Over {line} goals",1-poisson_cdf(int(line),hx+ax),basis))
        results.append(row("Both teams to score",(1-math.exp(-hx))*(1-math.exp(-ax)),basis))
    # Corners/cards: only price when both for/against records exist.
    for market,for_col,against_col,lines in [
        ("corners","Corners for","Corners against",[7.5,8.5,9.5,10.5,11.5,12.5]),
        ("yellow cards","Yellow cards for","Yellow cards against",[2.5,3.5,4.5,5.5,6.5])]:
        l1,n1=expectation(h,for_col,a,against_col)
        l2,n2=expectation(a,for_col,h,against_col)
        if l1 is None or l2 is None:continue
        lam=l1+l2
        source=f"recent {market} averages"
        if market=="yellow cards" and ref_cards>0:
            lam=(lam+ref_cards)/2;source+=" + referee"
        st.caption(f"Projected total {market}: {lam:.2f} · data coverage: {min(n1,n2)} matching records per side")
        for line in lines:results.append(row(f"Over {line} {market}",1-poisson_cdf(int(line),lam),source))
    st.subheader("Fair-odds board")
    if results:
        board=pd.DataFrame(results)
        st.caption("Historical figures below are whole-league baseline frequencies, NOT matches selected for similar pre-match form. ROI is flat-stake Bet365 last-seen odds for all historically priced selections; it is NOT the ROI of this fixture model.")
        try:
            history=(db().table("starlizard_market_history").select("competition_id,market,sample_size,wins,priced_bets,priced_wins,roi_pct").execute().data or [])
            # Prefer league-specific baseline when both clubs share a saved competition.
            home_leagues=(db().table("historical_xg").select("competition_id").ilike("home_team",home.strip()).order("match_date",desc=True).limit(1).execute().data or [])
            away_leagues=(db().table("historical_xg").select("competition_id").ilike("away_team",away.strip()).order("match_date",desc=True).limit(1).execute().data or [])
            league=(home_leagues[0].get("competition_id") if home_leagues and away_leagues and home_leagues[0].get("competition_id")==away_leagues[0].get("competition_id") else None)
            relevant=[r for r in history if r["competition_id"]==league] if league else []
            if not relevant:st.info("No shared competition found. Showing model estimates only; historical baseline is unavailable.")
            lookup={r["market"]:r for r in relevant}
            board["Historical wins / matches"]=board["Market"].map(lambda name:f"{lookup[name]['wins']}/{lookup[name]['sample_size']}" if name in lookup else "—")
            board["Historical hit rate"]=board["Market"].map(lambda name:f"{100*lookup[name]['wins']/lookup[name]['sample_size']:.1f}%" if name in lookup and lookup[name]["sample_size"] else "—")
            board["Bet365 ROI"]=board["Market"].map(lambda name:f"{float(lookup[name]['roi_pct']):+.1f}%" if name in lookup and lookup[name].get("roi_pct") is not None and lookup[name]["priced_bets"]>=30 else "—")
            board["ROI bets"]=board["Market"].map(lambda name:lookup[name]["priced_bets"] if name in lookup else "—")
            st.caption("ROI shown only when at least 30 historical Bet365 quotes exist. Even then, it may be noisy and does not establish a profitable strategy.")
        except Exception as exc:
            st.warning(f"Historical baseline unavailable: {exc}")
        st.markdown("""<style>
        .odds-card{border:1px solid #345267;background:#142536;border-radius:12px;padding:10px 12px;margin:7px 0}
        .odds-title{font-size:15px;font-weight:750;color:#f1f7ff;margin-bottom:5px}
        .odds-line{display:flex;justify-content:space-between;gap:8px;font-size:13px;line-height:1.65;color:#c8d6e3}
        .odds-line strong{color:#ffffff;white-space:nowrap}
        </style>""",unsafe_allow_html=True)
        from html import escape
        for group,pattern in [("Match result & goals",lambda x:"corners" not in x and "cards" not in x),
                              ("Corners",lambda x:"corners" in x),
                              ("Yellow cards",lambda x:"cards" in x)]:
            subset=board[board["Market"].map(pattern)]
            if subset.empty:continue
            st.markdown(f"#### {group}")
            for _,r in subset.iterrows():
                def val(k):return escape(str(r.get(k,"—")))
                st.markdown(
                    '<div class="odds-card"><div class="odds-title">'+val("Market")+'</div>'
                    '<div class="odds-line"><span>Fair odds</span><strong>'+val("Fair odds")+'</strong></div>'
                    '<div class="odds-line"><span>Model probability</span><strong>'+val("Probability")+'</strong></div>'
                    '<div class="odds-line"><span>Historical hit rate</span><strong>'+val("Historical hit rate")+'</strong></div>'
                    '<div class="odds-line"><span>Historical wins</span><strong>'+val("Historical wins / matches")+'</strong></div>'
                    '<div class="odds-line"><span>Bet365 ROI ('+val("ROI bets")+' bets)</span><strong>'+val("Bet365 ROI")+'</strong></div>'
                    '</div>',unsafe_allow_html=True)
        with st.expander("Full detailed table"):
            st.dataframe(board,hide_index=True,use_container_width=True)
        st.download_button("Download fair odds CSV",board.to_csv(index=False),file_name="starlizard_fair_odds.csv",mime="text/csv",use_container_width=True)
    else:st.warning("Enter goals or xG, plus matching opponent figures, to calculate odds.")
    st.subheader("Shots and fouls")
    for market,for_col,against_col in [("Shots","Shots for","Shots against"),("Fouls","Fouls for","Fouls against")]:
        p1,n1=expectation(h,for_col,a,against_col);p2,n2=expectation(a,for_col,h,against_col)
        if p1 is not None and p2 is not None:
            st.write(f"**{market}:** {home} {p1:.1f} · {away} {p2:.1f} · projected match total {p1+p2:.1f}")
        else:st.caption(f"{market}: insufficient entered match data")
    if ref_fouls>0:st.caption(f"Referee fouls average: {ref_fouls:.1f} (context only)")
    st.warning("Model prices are illustrative, not validated betting edges. Assumes independent Poisson counts; corners and cards can be overdispersed. Small samples and unadjusted opponent strength create uncertainty. Missing data never counts as zero.")
st.caption("Historical figures come from Supabase, collected using TheStatsAPI. The model is experimental; no API requests are made by Analyse.")
