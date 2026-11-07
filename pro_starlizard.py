
import streamlit as st

# ==========================================
# PRO STARLIZARD — MOBILE DASHBOARD
# ==========================================

st.set_page_config(
    page_title="PRO STARLIZARD",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==========================================
# PROFESSIONAL DARK THEME
# ==========================================

st.markdown("""
<style>
.stApp {
    background-color: #0b1220;
    color: #e8eef8;
}

.block-container {
    padding-top: 0.5rem;
    padding-bottom: 2rem;
    max-width: 1100px;
}

h1, h2, h3 {
    color: #f8fafc !important;
}

h2 {
    font-size: 1.6rem !important;
}

label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p {
    color: #e8eef8 !important;
    font-weight: 600 !important;
}

div[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #293a53;
    border-radius: 12px;
    padding: 12px;
}

div.stButton > button {
    width: 100%;
    min-height: 3.2rem;
    border-radius: 12px;
    font-size: 1rem;
    font-weight: 700;
    border: 1px solid #41536c;
}

div.stButton > button[kind="primary"] {
    background-color: #b91c38;
    border-color: #ef4766;
    color: white;
}

div.stButton > button[kind="secondary"] {
    background-color: #172338;
    color: #f8fafc;
}

div.stButton > button p {
    color: inherit !important;
}

@media (max-width: 640px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    h1 {
        font-size: 1.8rem !important;
    }

    h2 {
        font-size: 1.4rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# SCRUMPY AND LADY SALLY HEADER
# ==========================================

st.image(
    "pro_starlizard_header_correct-1.png",
    use_container_width=True,
)

# ==========================================
# MAIN NAVIGATION
# ==========================================

if "active_page" not in st.session_state:
    st.session_state.active_page = "Match Pricing"

pages = [
    ("Match Pricing", "⚽"),
    ("Historical Research", "📊"),
    ("Database Health", "🗄️"),
]

for page_name, page_icon in pages:
    selected = st.session_state.active_page == page_name

    if st.button(
        f"{page_icon}  {page_name}",
        key=f"nav_{page_name}",
        use_container_width=True,
        type="primary" if selected else "secondary",
    ):
        st.session_state.active_page = page_name
        st.rerun()

st.divider()

# ==========================================
# MATCH PRICING
# ==========================================

if st.session_state.active_page == "Match Pricing":

    st.header("Match Pricing")

    st.caption(
        "Pre-match and in-play football pricing terminal"
    )

    home = st.text_input(
        "Home team",
        placeholder="Enter home team",
    )

    away = st.text_input(
        "Away team",
        placeholder="Enter away team",
    )

    market = st.selectbox(
        "Select market",
        [
            "Match Goals",
            "Second-Half Goals",
            "Match Corners",
            "Second-Half Corners",
            "Cards",
            "Asian Handicap",
            "Asian Goal Totals",
            "Correct Score",
            "Next Goal",
            "Both Teams To Score",
        ],
    )

    st.info(
        "Pricing engine not connected yet. "
        "This is our new dashboard preview."
    )

# ==========================================
# HISTORICAL RESEARCH
# ==========================================

elif st.session_state.active_page == "Historical Research":

    st.header("Historical Research")

    st.caption(
        "Investigate historical football statistics"
    )

    st.markdown("""
    **Research tools planned**

    - Historical expected goals (xG)
    - Halftime match situations
    - Second-half goal patterns
    - Goal and corner timings
    - Yellow and red cards
    - Referee research
    - Opposition-adjusted statistics
    - Backtesting and model calibration
    """)

    st.info(
        "Historical research tools will be connected "
        "to our existing data."
    )

# ==========================================
# DATABASE HEALTH
# ==========================================

elif st.session_state.active_page == "Database Health":

    st.header("Database Health")

    st.caption(
        "Historical match collection and verification"
    )

    st.metric(
        "Matches collected",
        "Not connected",
    )

    st.metric(
        "Verified goals",
        "Not connected",
    )

    st.metric(
        "Verified corners",
        "Not connected",
    )

    st.info(
        "Live Supabase database statistics "
        "will be connected next."
    )

# ==========================================
# FOOTER
# ==========================================

st.divider()

st.caption(
    "PRO STARLIZARD | Research and model estimates only. "
    "No automated betting."
)

st.caption(
    "🦎 Scrumpy & Lady Sally — Data Acquisition Team"
)
