"""PRO STARLIZARD — one manual fixture analysis workspace. No API calls."""
import math
import pandas as pd
import streamlit as st

st.set_page_config(page_title="PRO STARLIZARD | Match Analysis",page_icon="⚽",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>
.stApp{background:linear-gradient(145deg,#0a1220,#101f31);color:#eaf2f9}
.block-container{max-width:1100px;padding-top:1.2rem}
h1,h2,h3{letter-spacing:-.035em}
[data-testid="stSidebar"],[data-testid="stSidebarNav"],[data-testid="stToolbar"]{display:none}
div[data-testid="stMetric"]{background:#172b3c;border:1px solid #345267;border-radius:12px;padding:12px}
.stButton button[kind="primary"]{background:#35bba5;color:#061b21;border:0;font-weight:800}
@media(max-width:640px){.block-container{padding:.8rem .6rem 3rem}}
</style>""",unsafe_allow_html=True)
try:st.image("pro_starlizard_header_correct-1.png",use_container_width=True)
except Exception:pass
st.title("⚽ Match Intelligence")
st.caption("One workspace. Enter individual matches, review form and calculate transparent fair odds. No API charges.")
c1,c2=st.columns(2)
with c1:home=st.text_input("Home team","Manchester City")
with c2:away=st.text_input("Away team","Fulham")
n=st.selectbox("Recent matches for each team",[5,10,15,20],index=0)
st.info("Enter the HOME team's latest home matches and the AWAY team's latest away matches. One row per match, newest first. Totals are for the whole match. Leave unknown statistics blank.")

cols=["Date / opponent","Goals for","Goals against","xG for","xG against","Corners for","Corners against","Yellow cards for","Yellow cards against","Shots for","Shots against","Fouls for","Fouls against"]
numeric=cols[1:]
def editor(label,key):
    st.subheader(label)
    if key not in st.session_state or len(st.session_state[key])!=n:
        st.session_state[key]=pd.DataFrame([{"Date / opponent":""} for _ in range(n)],columns=cols)
    return st.data_editor(st.session_state[key],num_rows="fixed",use_container_width=True,hide_index=True,key="grid_"+key,column_config={"Date / opponent":st.column_config.TextColumn("Date / opponent",width="medium"),**{x:st.column_config.NumberColumn(x,min_value=0,step=1 if "xG" not in x else .1,format="%.2f" if "xG" in x else "%.0f") for x in numeric}})
h=editor(f"🏠 {home} — last {n} home matches","home_rows")
a=editor(f"✈️ {away} — last {n} away matches","away_rows")
st.subheader("🏟️ Last five meetings at this ground")
st.caption("Enter the score from the home team's perspective. These results are shown separately, not double-counted in recent form.")
h2h=st.data_editor(pd.DataFrame([{"Date":"","Home goals":None,"Away goals":None} for _ in range(5)]),num_rows="fixed",hide_index=True,use_container_width=True,key="h2h")
st.subheader("🟨 Referee (optional)")
rc1,rc2,rc3=st.columns(3)
with rc1:ref=st.text_input("Referee")
with rc2:ref_cards=st.number_input("Average total yellow cards",min_value=0.0,max_value=12.0,value=0.0,step=.1)
with rc3:ref_fouls=st.number_input("Average fouls",min_value=0.0,max_value=50.0,value=0.0,step=.5)
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
if st.button("🎯 ANALYSE MATCH & CALCULATE FAIR ODDS",type="primary",use_container_width=True):
    st.divider()
    st.header(f"{home} v {away} — Match dossier")
    stat=[]
    for label,df in [(home+" home",h),(away+" away",a)]:
        for metric in numeric:
            x,nobs=avg(df,metric)
            if x is not None:stat.append({"Team / venue":label,"Statistic":metric,"Average":round(x,2),"Matches":nobs})
    if stat:
        st.subheader("Recent form — recorded averages")
        st.dataframe(pd.DataFrame(stat),hide_index=True,use_container_width=True)
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
        st.dataframe(pd.DataFrame(results),hide_index=True,use_container_width=True)
        st.download_button("Download fair odds CSV",pd.DataFrame(results).to_csv(index=False),file_name="starlizard_fair_odds.csv",mime="text/csv",use_container_width=True)
    else:st.warning("Enter goals or xG, plus matching opponent figures, to calculate odds.")
    st.subheader("Shots and fouls")
    for market,for_col,against_col in [("Shots","Shots for","Shots against"),("Fouls","Fouls for","Fouls against")]:
        p1,n1=expectation(h,for_col,a,against_col);p2,n2=expectation(a,for_col,h,against_col)
        if p1 is not None and p2 is not None:
            st.write(f"**{market}:** {home} {p1:.1f} · {away} {p2:.1f} · projected match total {p1+p2:.1f}")
        else:st.caption(f"{market}: insufficient entered match data")
    if ref_fouls>0:st.caption(f"Referee fouls average: {ref_fouls:.1f} (context only)")
    st.warning("Model prices are illustrative, not validated betting edges. Assumes independent Poisson counts; corners and cards can be overdispersed. Small samples and unadjusted opponent strength create uncertainty. Missing data never counts as zero.")
st.caption("All inputs remain in this browser session only. No paid API or live data feed is used; historical database and keys remain untouched.")
