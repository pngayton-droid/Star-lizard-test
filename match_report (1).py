import datetime as dt
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st

st.set_page_config(page_title='Starlizard Match Report', layout='wide')
st.title('Starlizard — Detailed Match Report')
st.caption('Research only. Uses your existing STATS_API_KEY; no credentials are included in exports.')

KEY = st.secrets.get('STATS_API_KEY', '')
if not KEY:
    st.error('STATS_API_KEY is missing from Streamlit Secrets.')
    st.stop()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch(endpoint, params, key):
    url = 'https://api.thestatsapi.com/api' + endpoint
    if params:
        url += '?' + urlencode(params)
    request = Request(url, headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'API HTTP {exc.code} on {endpoint}') from None
    except URLError:
        raise RuntimeError('Unable to connect to TheStatsAPI') from None

def payload(response):
    return response.get('data', response) if isinstance(response, dict) else response

comp = st.text_input('Competition ID', 'comp_3039')
col1, col2 = st.columns(2)
with col1:
    start = st.date_input('From', dt.date.today())
with col2:
    end = st.date_input('To', dt.date.today())

if st.button('Find fixtures'):
    if end < start:
        st.error('End date cannot be before start date.')
    else:
        try:
            response = fetch('/football/matches', {'competition_id':comp.strip(), 'date_from':start.isoformat(), 'date_to':end.isoformat(), 'per_page':100}, KEY)
            matches = payload(response)
            if not isinstance(matches, list):
                raise ValueError('Unexpected fixture response format')
            st.session_state['report_matches'] = matches
            st.success(f'{len(matches)} fixtures on first page. More pages may exist.')
        except Exception as exc:
            st.error(str(exc))

matches = st.session_state.get('report_matches', [])
choices = {}
for item in matches:
    if not isinstance(item, dict):
        continue
    mid = str(item.get('id', ''))
    if not mid.startswith('mt_'):
        continue
    home = item.get('home_team') or {}
    away = item.get('away_team') or {}
    if not isinstance(home, dict) or not isinstance(away, dict):
        continue
    label = f"{item.get('utc_date','')} | {home.get('name','?')} v {away.get('name','?')} | {mid}"
    choices[label] = item

if choices:
    chosen = st.selectbox('Fixture', list(choices))
    match = choices[chosen]
    mid = str(match['id'])
    if st.button('Retrieve detailed report data'):
        bundle = {'fixture': match, 'retrieved_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'sources': {}, 'errors': {}}
        endpoints = {
            'match_detail': f'/football/matches/{mid}',
            'match_stats': f'/football/matches/{mid}/stats',
            'events': f'/football/matches/{mid}/events',
            'player_stats': f'/football/matches/{mid}/player-stats',
            'odds': f'/football/matches/{mid}/odds',
        }
        with st.spinner('Retrieving available match data…'):
            for name, endpoint in endpoints.items():
                try:
                    bundle['sources'][name] = payload(fetch(endpoint, {}, KEY))
                except Exception as exc:
                    bundle['errors'][name] = str(exc)
                time.sleep(0.3)
        st.session_state['report_bundle'] = bundle

bundle = st.session_state.get('report_bundle')
if bundle:
    st.subheader('Retrieved data')
    st.caption('Upcoming matches may not have statistics, events or player statistics yet. Missing data is not estimated.')
    st.write('Available sections:', ', '.join(bundle['sources']) or 'None')
    if bundle['errors']:
        st.warning('Some endpoints were unavailable: ' + '; '.join(f'{k}: {v}' for k,v in bundle['errors'].items()))
    with st.expander('Inspect data', expanded=False):
        st.json(bundle)
    st.download_button('Download report data (JSON)', data=json.dumps(bundle, indent=2, ensure_ascii=False, default=str), file_name='starlizard_match_report.json', mime='application/json')
    st.info('This first-stage export is the foundation. Next we will add recent form, head-to-head comparisons, referee and player trends using historical match and team endpoints, without inventing missing statistics.')
