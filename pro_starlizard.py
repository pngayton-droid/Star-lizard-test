
import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title='PRO STARLIZARD', page_icon='⚽', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
.stApp{background-color:#0b1220;color:#e8eef8}
.block-container{padding-top:.5rem;padding-bottom:2rem;max-width:1100px}
h1,h2,h3{color:#f8fafc!important}
label,[data-testid="stWidgetLabel"],[data-testid="stWidgetLabel"] p{color:#e8eef8!important;font-weight:600!important}
div[data-testid="stMetric"]{background:#172338;border:1px solid #293a53;border-radius:12px;padding:12px}
div[data-testid="stMetricValue"],div[data-testid="stMetricValue"] *,div[data-testid="stMetricLabel"],div[data-testid="stMetricLabel"] *{color:#f8fafc!important;opacity:1!important}
div.stButton>button{width:100%;min-height:3.2rem;border-radius:12px;font-size:1rem;font-weight:700;border:1px solid #41536c}
div.stButton>button[kind="primary"]{background-color:#b91c38;border-color:#ef4766;color:white}
div.stButton>button[kind="secondary"]{background-color:#172338;color:#f8fafc}
div.stButton>button p{color:inherit!important}
@media(max-width:640px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:1.8rem!important}h2{font-size:1.4rem!important}}
</style>''', unsafe_allow_html=True)
st.image('pro_starlizard_header_correct-1.png', width='stretch')

@st.cache_resource
def get_supabase():
    return create_client(st.secrets['SUPABASE_URL'], st.secrets['SUPABASE_SECRET_KEY'])

@st.cache_data(ttl=120, show_spinner=False)
def get_database_stats():
    db = get_supabase()
    checks = [
        ('Historical xG records','historical_xg',None,None),
        ('Match event records collected','historical_match_events',None,None),
        ('Match statistics received','historical_match_events','stats_status',200),
        ('Goal/event timelines received','historical_match_events','timeline_status',200),
        ('Corners matched','historical_match_events','corners_match',True),
        ('Yellow cards matched','historical_match_events','yellow_cards_match',True),
        ('Red cards matched','historical_match_events','red_cards_match',True),
    ]
    results, errors = {}, {}
    for label, table, column, value in checks:
        try:
            q = db.table(table).select('match_id', count='exact')
            if column is not None:
                q = q.eq(column, value)
            results[label] = q.limit(1).execute().count
        except Exception as e:
            results[label] = None
            errors[label] = type(e).__name__
    return results, errors

# Query only the selected team's matches, not the full database.
# Two separately ordered requests keep API usage modest.
@st.cache_data(ttl=300, show_spinner=False)
def get_team_matches(team, sample):
    db = get_supabase()
    fields = ('match_id,match_date,home_team,away_team,'
              'home_goals,away_goals,home_ht_goals,away_ht_goals,'
              'home_xg,away_xg,home_ht_xg,away_ht_xg')
    rows = []
    for field in ('home_team', 'away_team'):
        response = (db.table('historical_xg')
                    .select(fields)
                    .eq(field, team)
                    .order('match_date', desc=True)
                    .limit(sample).execute())
        rows.extend(response.data or [])
    unique = {}
    for row in rows:
        unique[row['match_id']] = row
    return sorted(unique.values(), key=lambda r: (r.get('match_date') or '', str(r.get('match_id') or '')), reverse=True)[:sample]

@st.cache_data(ttl=3600, show_spinner=False)
def find_team_names(fragment):
    db = get_supabase()
    found = set()
    # Suggestions use at most 50 rows per side, not a full table download.
    for field in ('home_team', 'away_team'):
        resp = (db.table('historical_xg')
                .select(field)
                .ilike(field, '%' + fragment + '%')
                .limit(50).execute())
        found.update(r[field] for r in (resp.data or []) if r.get(field))
    return sorted(found, key=str.casefold)

def number(value):
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None

def show_team_analysis(team, matches):
    data = []
    for r in matches:
        home = r.get('home_team') == team
        gf = r.get('home_goals') if home else r.get('away_goals')
        ga = r.get('away_goals') if home else r.get('home_goals')
        ht_gf = r.get('home_ht_goals') if home else r.get('away_ht_goals')
        ht_ga = r.get('away_ht_goals') if home else r.get('home_ht_goals')
        xgf = number(r.get('home_xg') if home else r.get('away_xg'))
        xga = number(r.get('away_xg') if home else r.get('home_xg'))
        htxgf = number(r.get('home_ht_xg') if home else r.get('away_ht_xg'))
        htxga = number(r.get('away_ht_xg') if home else r.get('home_ht_xg'))
        valid_score = gf is not None and ga is not None
        data.append({
            'Date':r.get('match_date'), 'Venue':'Home' if home else 'Away',
            'Opponent':r.get('away_team') if home else r.get('home_team'),
            'GF':gf,'GA':ga,'HT GF':ht_gf,'HT GA':ht_ga,
            'xGF':xgf,'xGA':xga,'HT xGF':htxgf,'HT xGA':htxga,
            'Result':('W' if gf > ga else 'D' if gf == ga else 'L') if valid_score else '—',
        })
    df = pd.DataFrame(data)
    if df.empty:
        st.info('No matches found for this team.')
        return
    st.success(f'Found {len(df)} recent matches for {team}.')
    st.subheader('Recent performance')
    scored = df[df['Result'].isin(['W','D','L'])]
    wins = int((scored['Result'] == 'W').sum())
    draws = int((scored['Result'] == 'D').sum())
    losses = int((scored['Result'] == 'L').sum())
    c1,c2,c3 = st.columns(3)
    c1.metric('Wins',wins)
    c2.metric('Draws',draws)
    c3.metric('Losses',losses)
    st.caption('Averages use only rows with the relevant data available.')
    def metric_summary(frame, title):
        st.markdown(f'**{title} — {len(frame)} matches**')
        if frame.empty:
            st.info('No matches in this split.')
            return
        for label, col in [('Goals scored','GF'),('Goals conceded','GA'),('xG for','xGF'),('xG against','xGA'),('HT goals for','HT GF'),('HT goals against','HT GA'),('HT xG for','HT xGF'),('HT xG against','HT xGA')]:
            values = pd.to_numeric(frame[col], errors='coerce').dropna()
            if not values.empty:
                st.metric(label, f'{values.mean():.2f}')
    tab1,tab2,tab3 = st.tabs(['All matches','Home','Away'])
    with tab1: metric_summary(df,'All')
    with tab2: metric_summary(df[df['Venue']=='Home'],'Home')
    with tab3: metric_summary(df[df['Venue']=='Away'],'Away')
    st.subheader('Match-by-match results')
    st.dataframe(df, hide_index=True, width='stretch')
    st.caption('The match list is the most recent available by match date. Missing data is excluded from averages; xG is not a prediction or a verified betting edge.')

if 'active_page' not in st.session_state:
    st.session_state.active_page = 'Match Pricing'
for page, icon in [('Match Pricing','⚽'),('Historical Research','📊'),('Database Health','🗄️')]:
    if st.button(f'{icon}  {page}', key=f'nav_{page}', width='stretch', type='primary' if st.session_state.active_page == page else 'secondary'):
        st.session_state.active_page = page
        st.rerun()
st.divider()

if st.session_state.active_page == 'Match Pricing':
    st.header('Match Pricing')
    st.caption('Pre-match and in-play football pricing terminal')
    st.text_input('Home team', placeholder='Enter home team')
    st.text_input('Away team', placeholder='Enter away team')
    st.selectbox('Select market',['Match Goals','Second-Half Goals','Match Corners','Second-Half Corners','Cards','Asian Handicap','Asian Goal Totals','Correct Score','Next Goal','Both Teams To Score'])
    st.info('Pricing engine not connected yet. This is our dashboard preview.')

elif st.session_state.active_page == 'Historical Research':
    st.header('Historical Research')
    st.caption('Real historical football data from Supabase — no StatsAPI calls')
    fragment = st.text_input('Find a team', placeholder='e.g. Newcastle', max_chars=60).strip()
    if fragment:
        if len(fragment) < 3:
            st.info('Type at least three letters to search for a team.')
        elif '%' in fragment or '_' in fragment:
            st.warning('Please enter ordinary team-name letters rather than % or _.')
        else:
            try:
                teams = find_team_names(fragment)
                if not teams:
                    st.warning('No matching team names found. Try another spelling.')
                else:
                    if len(teams) == 50:
                        st.caption('Showing a limited set of matches. Type more letters if your team is missing.')
                    team = st.selectbox('Choose team', teams)
                    sample = st.select_slider('Recent matches', options=[5,10,15,20,30,50], value=20)
                    if st.button('📊 Analyse team', type='primary', width='stretch'):
                        st.session_state['research_selection'] = (team, sample)
                    selection = st.session_state.get('research_selection')
                    if selection and selection[0] == team and selection[1] == sample:
                        with st.spinner('Loading historical matches...'):
                            matches = get_team_matches(team, sample)
                        show_team_analysis(team, matches)
            except Exception as e:
                st.error(f'Research request failed ({type(e).__name__}). No data has been changed.')
    st.caption('Corners, cards and goal timings will follow once the event-data joins and verification filters are implemented.')

elif st.session_state.active_page == 'Database Health':
    st.header('Database Health')
    st.caption('Live historical collection statistics from Supabase')
    if st.button('🔄 Refresh database figures', width='stretch'):
        get_database_stats.clear()
    try:
        with st.spinner('Checking database tables...'):
            results, errors = get_database_stats()
        passed = sum(v is not None for v in results.values())
        if passed == 7:
            st.success('All seven database checks succeeded.')
        else:
            st.warning(f'{passed} of 7 database checks succeeded.')
        groups = [
            ('Historical Database',['Historical xG records','Match event records collected']),
            ('Collection Status',['Match statistics received','Goal/event timelines received']),
            ('Verified Markets',['Corners matched','Yellow cards matched','Red cards matched']),
        ]
        for heading, labels in groups:
            st.subheader(heading)
            for label in labels:
                value = results.get(label)
                st.metric(label, f'{value:,}' if value is not None else 'Unavailable')
        total = results.get('Match event records collected')
        verified = results.get('Corners matched')
        if total and verified is not None:
            st.metric('Corner verification rate',f'{100*verified/total:.1f}%')
        st.subheader('Database Diagnostics')
        if errors:
            for label, kind in errors.items():
                st.error(f'{label}: {kind}')
        else:
            st.success('No database query errors detected.')
        st.caption('Read-only queries. Figures are cached for two minutes. Received timelines are not independently goal-verified by this dashboard.')
    except Exception as e:
        st.error(f'Database connection failed ({type(e).__name__}).')

st.divider()
st.caption('PRO STARLIZARD | Research and model estimates only. No automated betting.')
st.caption('🦎 Scrumpy & Lady Sally — Data Acquisition Team')
