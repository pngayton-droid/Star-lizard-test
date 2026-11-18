"""PRO STARLIZARD — clean manual research home.

The historical research scripts and database are preserved, but legacy test
pages are deliberately removed from the visible interface.
"""
import streamlit as st

st.set_page_config(
    page_title="PRO STARLIZARD | Football Intelligence",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
:root {color-scheme: dark;}
.stApp {background:linear-gradient(155deg,#09101c 0%,#101d2d 58%,#0c1422 100%);color:#eef4fb;}
.block-container {max-width:1050px;padding-top:2.5rem;padding-bottom:4rem;}
h1,h2,h3 {color:#f5f8fd!important;letter-spacing:-.035em;}
p,li {line-height:1.65;}
[data-testid="stSidebar"] {background:#101b2a;}
[data-testid="stSidebarNav"] {display:none;}
[data-testid="stPageLink"] a {
    display:flex;align-items:center;justify-content:center;min-height:4.2rem;
    background:#192a3e;border:1px solid #34506b;border-radius:14px;
    text-decoration:none!important;color:#f8fbff!important;font-weight:700;
    padding:1rem;transition:background .2s ease;
}
[data-testid="stPageLink"] a:hover {background:#233d57;border-color:#55c3b1;}
[data-testid="stPageLink"] a p {color:#f8fbff!important;font-size:1.04rem;}
.stButton>button {border-radius:12px;}
.hero {padding:2.2rem 2rem;border:1px solid #28445b;border-radius:22px;
       background:linear-gradient(120deg,#183347,#152236 75%);margin:1rem 0 1.8rem;}
.eyebrow {color:#74e0ca;font-size:.78rem;letter-spacing:.14em;font-weight:800;}
.hero-title {font-size:clamp(2rem,5vw,3.2rem);font-weight:800;line-height:1.15;
             letter-spacing:-.045em;color:#fff;margin:.6rem 0;}
.hero-sub {color:#c4d5e5;font-size:1.08rem;max-width:670px;}
.feature {padding:1.3rem 1.4rem;border-radius:15px;border:1px solid #2c4057;
          background:#142337;min-height:145px;margin-bottom:1rem;}
.feature-title {color:#f4f8ff;font-weight:750;font-size:1.08rem;margin-bottom:.5rem;}
.feature-copy {color:#b9cbdd;font-size:.94rem;}
.note {color:#9fb3c9;font-size:.86rem;margin-top:1.3rem;}
@media(max-width:640px) {
 .block-container {padding:1.1rem .85rem 2.5rem;}
 .hero {padding:1.6rem 1.2rem;border-radius:16px;}
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚽ PRO STARLIZARD")
    st.caption("FOOTBALL INTELLIGENCE")
    st.page_link("pro_starlizard.py",label="🏠 Home",use_container_width=True)
    st.page_link("pages/Manual_Fair_Odds.py",label="🎯 Manual fair odds",use_container_width=True)
    st.page_link("pages/Paste_Research.py",label="📋 Paste research & odds",use_container_width=True)
    st.divider()
    st.caption("Historical data retained. Legacy experiments hidden.")

try:
    st.image("pro_starlizard_header_correct-1.png",use_container_width=True)
except Exception:
    pass

st.markdown("""
<div class="hero">
 <div class="eyebrow">PRO STARLIZARD · RESEARCH DESK</div>
 <div class="hero-title">Football intelligence.<br>Without the clutter.</div>
 <div class="hero-sub">Select a fixture, explore historical outcomes and calculate
 evidence-based fair odds. Built around your saved match database — no live API
 subscription required.</div>
</div>
""",unsafe_allow_html=True)

st.markdown("### Your workspace")
st.page_link("pages/Manual_Fair_Odds.py",label="🎯 OPEN MANUAL FAIR ODDS",use_container_width=True)
st.caption("Pre-match and half-time pricing · Historical frequencies · Exact score outcomes")
st.page_link("pages/Paste_Research.py",label="📋 PASTE RECENT FORM OR FAIR ODDS",use_container_width=True)

left,right=st.columns(2,gap="medium")
with left:
    st.markdown("""<div class="feature">
    <div class="feature-title">⚽ Pre-match research</div>
    <div class="feature-copy">Compare recent home and away performances,
    match outcomes, goal totals and both-teams-to-score frequencies.</div>
    </div>""",unsafe_allow_html=True)
with right:
    st.markdown("""<div class="feature">
    <div class="feature-title">⏱️ Half-time research</div>
    <div class="feature-copy">Enter the half-time score to examine comparable
    match states, second-half goals and full-time results.</div>
    </div>""",unsafe_allow_html=True)

st.markdown("### How to use it")
st.markdown("**1.** Open Manual Fair Odds.  **2.** Choose your fixture and sample size.  **3.** Review frequencies, implied odds and sample sizes.")
st.markdown("""<div class="note">Historical frequencies are descriptive estimates,
not guaranteed probabilities or evidence of a profitable betting strategy.
More detailed fixture dossiers, referee research, cards, corners and fouls
pricing will be added only where reliable data supports them.</div>""",unsafe_allow_html=True)
