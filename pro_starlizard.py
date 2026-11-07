
import streamlit as st
from supabase import create_client

# ==========================================
# PRO STARLIZARD
# ==========================================

st.set_page_config(
    page_title="PRO STARLIZARD",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==========================================
# DARK MOBILE THEME
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

div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] *,
div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] * {
    color: #f8fafc !important;
    opacity: 1 !important;
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
# SCRUMPY AND LADY SALLY
# ==========================================

st.image(
    "pro_starlizard_header_correct-1.png",
    width="stretch",
)

# ==========================================
# DATABASE FUNCTIONS
# ==========================================

@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )


@st.cache_data(ttl=120, show_spinner=False)
def get_database_stats():
    db = get_supabase()

    def count_rows(table, column=None, value=None):
        query = (
            db.table(table)
            .select("match_id", count="exact")
        )

        if column is not None:
            query = query.eq(column, value)

        result = query.limit(1).execute()
        return result.count or 0

    xg_total = count_rows("historical_xg")

    events_total = count_rows(
        "historical_match_events"
    )

    stats_success = count_rows(
        "historical_match_events",
        "stats_status",
        200,
    )

    timelines_success = count_rows(
        "historical_match_events",
        "timeline_status",
        200,
    )

    corners_verified = count_rows(
        "historical_match_events",
        "corners_match",
        True,
    )

    yellow_verified = count_rows(
        "historical_match_events",
        "yellow_cards_match",
        True,
    )

    red_verified = count_rows(
        "historical_match_events",
        "red_cards_match",
        True,
    )

    return {
        "xg_total": xg_total,
        "events_total": events_total,
        "stats_success": stats_success,
        "timelines_success": timelines_success,
        "corners_verified": corners_verified,
        "yellow_verified": yellow_verified,
        "red_verified": red_verified,
    }


# ==========================================
# NAVIGATION
# ==========================================

if "active_page" not in st.session_state:
    st.session_state.active_page = "Match Pricing"

pages = [
    ("Match Pricing", "⚽"),
    ("Historical Research", "📊"),
    ("Database Health", "🗄️"),
]

for page_name, page_icon in pages:
    selected = (
        st.session_state.active_page == page_name
    )

    if st.button(
        f"{page_icon}  {page_name}",
        key=f"nav_{page_name}",
        width="stretch",
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
        "This is our dashboard preview."
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
    - Backtesting and calibration
    """)

    st.info(
        "Historical research tools will be connected "
        "to our existing data."
    )

# ==========================================
# LIVE DATABASE HEALTH
# ==========================================

elif st.session_state.active_page == "Database Health":

    st.header("Database Health")

    st.caption(
        "Live historical collection statistics from Supabase"
    )

    if st.button(
        "🔄 Refresh database figures",
        width="stretch",
    ):
        get_database_stats.clear()

    try:
        with st.spinner("Reading Supabase database..."):
            data = get_database_stats()

        st.success("Connected to Supabase")

        st.subheader("Historical Database")

        st.metric(
            "Historical xG records",
            f"{data['xg_total']:,}",
        )

        st.metric(
            "Match event records collected",
            f"{data['events_total']:,}",
        )

        st.subheader("Collection Status")

        st.metric(
            "Match statistics received",
            f"{data['stats_success']:,}",
        )

        st.metric(
            "Goal/event timelines received",
            f"{data['timelines_success']:,}",
        )

        st.subheader("Verified Markets")

        st.metric(
            "Corners matched",
            f"{data['corners_verified']:,}",
        )

        st.metric(
            "Yellow cards matched",
            f"{data['yellow_verified']:,}",
        )

        st.metric(
            "Red cards matched",
            f"{data['red_verified']:,}",
        )

        if data["events_total"] > 0:
            corner_rate = (
                100 * data["corners_verified"]
                / data["events_total"]
            )

            st.metric(
                "Corner verification rate",
                f"{corner_rate:.1f}%",
            )

        st.caption(
            "Matched means event totals agree with "
            "the provider's match statistics. "
            "Received timelines are not independently "
            "goal-verified by this dashboard."
        )

        st.caption(
            "Figures are cached for two minutes. "
            "Use Refresh to request current totals."
        )

    except Exception as e:
        st.warning(
            f"Database error type: {type(e).__name__}"
        )

        st.error(
            "Unable to read Supabase. "
            "We are identifying the connection problem."
        )

        st.caption(
            "This diagnostic deliberately hides "
            "credentials and detailed error messages."
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
