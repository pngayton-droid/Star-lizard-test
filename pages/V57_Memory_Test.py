
import streamlit as st
from supabase import create_client

from starlizard_halftime_markets_v57 import render_halftime_markets

st.set_page_config(
    page_title="PRO STARLIZARD V5.7 Test",
    page_icon="🦎",
    layout="wide",
)

@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )

st.title("🦎 PRO STARLIZARD — V5.7 TEST")

st.info(
    "Independent test of the memory-efficient "
    "halftime corners and cards pricing engine."
)

render_halftime_markets(get_supabase())
