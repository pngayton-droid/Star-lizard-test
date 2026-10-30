"""Separate experimental pricing UI; does not alter existing scanner."""
import datetime
import pandas as pd
import streamlit as st
from model import load, Model
from score_pricer import price, edge

st.set_page_config(page_title='Football pricing lab', layout='wide')
st.title('Football pricing lab — experimental')
st.warning('Research tool only. Prices are model estimates, not verified market edges. No automatic bets.')

@st.cache_data(show_spinner='Loading historical matches…')
def historical(path):
    return load(path)

@st.cache_resource(show_spinner='Training historical team ratings…')
def fit(path, asof):
    data=historical(path)
    data=data[data.date < pd.Timestamp(asof)]
    m=Model()
    for date, group in data.groupby('date', sort=True):
        for r in group.itertuples(index=False):
            m.update(str(r.Div),str(r.HomeTeam),str(r.AwayTeam),int(r.FTHG),int(r.FTAG))
    return m, int(len(data))

st.caption('Data available only through the selected as-of date. Historical score results are never used to price matches on or before that date.')
path=st.text_input('Historical CSV path', 'https://raw.githubusercontent.com/pngayton-droid/football-value-scanner/main/football_merged_32653.csv')
asof=st.date_input('Price matches as of (training strictly before this date)',value=datetime.date(2026,10,30))
try:
    m, n=fit(path,asof.isoformat())
except Exception as ex:
    st.error(f'Could not load historical data: {ex}')
    st.stop()
st.caption(f'{n:,} prior matches used to build ratings. Bookmaker odds are not used to calculate the model price.')
leagues=sorted({key for key in m.league if len(m.league[key]['hg'])>=60})
if not leagues:
    st.error('Insufficient historical league data'); st.stop()
league=st.selectbox('League',leagues)
teams=sorted({team for div,team in m.team if div==league})
if len(teams)<2: st.stop()
a,b=st.columns(2)
with a: home=st.selectbox('Home team',teams,index=0)
with b: away=st.selectbox('Away team',teams,index=min(1,len(teams)-1))
if home==away:
    st.warning('Choose two different teams');st.stop()
pred=m.predict(league,home,away)
if pred is None:
    st.warning('Not enough team history for this fixture');st.stop()
lh,la,_=pred
st.write(f'Estimated full-match goals: **{home} {lh:.2f} — {la:.2f} {away}**')
st.subheader('Full-time fair prices')
res=price(lh,la)
labels={'home':'Home win','draw':'Draw','away':'Away win','over25':'Over 2.5','under25':'Under 2.5','btts_yes':'BTTS Yes','btts_no':'BTTS No'}
rows=[{'Market':labels[k],'Probability':f'{p:.1%}','Fair decimal':round(res['fair_odds'][k],2)} for k,p in res['probabilities'].items()]
st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
st.subheader('Correct-score prices')
scores=sorted(res['scores'].items(),key=lambda x:x[1],reverse=True)[:15]
st.dataframe(pd.DataFrame([{'Score':s,'Probability':f'{p:.2%}','Fair decimal':round(1/p,2)} for s,p in scores]),hide_index=True,use_container_width=True)
st.subheader('Compare with an actual market quote')
market=st.selectbox('Market',list(labels),format_func=lambda k:labels[k])
col1,col2=st.columns(2)
with col1: odds=st.number_input('Available decimal odds',min_value=1.01,max_value=1000.,value=2.00,step=.05)
with col2: commission=st.number_input('Exchange commission (%)',min_value=0.,max_value=30.,value=0.,step=.5)
p=res['probabilities'][market]
ev=edge(p,odds,commission/100)
st.metric('Estimated expected return per £1 staked',f'{ev:+.1%}')
st.caption('This is theoretical EV from an unvalidated model. It excludes slippage and price availability; a positive value is NOT proof of value.')
st.subheader('In-play sandbox (unvalidated)')
st.caption('Simple time-scaled Poisson only. It does NOT use live xG, red cards, substitutions or score-dependent goal rates.')
c1,c2,c3=st.columns(3)
with c1: minute=st.slider('Minute',0,90,45)
with c2: sh=st.number_input('Current home goals',0,15,0)
with c3: sa=st.number_input('Current away goals',0,15,0)
live=price(lh,la,sh,sa,(90-minute)/90)
st.dataframe(pd.DataFrame([{'Market':labels[k],'Probability':f'{p:.1%}','Fair decimal':round(live['fair_odds'][k],2) if live['fair_odds'][k] else None} for k,p in live['probabilities'].items()]),hide_index=True,use_container_width=True)


st.divider()
st.header('TheStatsAPI — fixture and odds connection (experimental)')
st.caption('Live data comes from TheStatsAPI; no automated betting or model-to-team matching. Fixture/odds requests are cached for 5 minutes.')

@st.cache_data(ttl=300, show_spinner='Contacting TheStatsAPI…')
def api_get(endpoint, params, secret):
    import json
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    url = 'https://api.thestatsapi.com/api' + endpoint
    if params:
        url += '?' + urlencode(params)
    req = Request(url, headers={'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=18) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'TheStatsAPI returned HTTP {exc.code}. Check subscription, key and coverage.') from None
    except URLError:
        raise RuntimeError('Could not connect to TheStatsAPI.') from None

api_key = st.secrets.get('STATS_API_KEY', '')
if not api_key:
    st.info('Set STATS_API_KEY in this app’s Streamlit Secrets to enable API requests.')
else:
    st.success('API key found in Streamlit Secrets (not displayed).')
    comp = st.text_input('Competition ID', 'comp_3039', help='Example ID for Premier League from provider documentation.')
    date1 = st.date_input('Fixtures from', value=datetime.date.today(), key='api_from')
    date2 = st.date_input('Fixtures to', value=datetime.date.today() + datetime.timedelta(days=2), key='api_to')
    if st.button('Fetch fixtures from TheStatsAPI'):
        if date2 < date1:
            st.error('End date must not be earlier than start date.')
        else:
            try:
                result = api_get('/football/matches', {'competition_id':comp, 'date_from':date1.isoformat(), 'date_to':date2.isoformat(), 'per_page':50}, api_key)
                items = result.get('data', [])
                if not isinstance(items, list):
                    raise ValueError('Unexpected match data format')
                st.session_state['api_matches'] = items
                st.session_state['api_comp'] = comp
                st.caption(f'{len(items)} fixtures returned on first page. More pages may exist.')
            except Exception as exc:
                st.error(str(exc))
    matches = st.session_state.get('api_matches', [])
    if matches:
        choices = {}
        for match in matches:
            mid = str(match.get('id',''))
            if not mid.startswith('mt_'):
                continue
            h = match.get('home_team') or {}
            a = match.get('away_team') or {}
            label = f"{match.get('utc_date','')} | {h.get('name','?')} vs {a.get('name','?')} | {match.get('status','')} | {mid}"
            choices[label] = mid
        if choices:
            selected = st.selectbox('Select an API fixture', list(choices))
            if st.button('Fetch bookmaker odds for this fixture'):
                try:
                    result = api_get('/football/matches/' + choices[selected] + '/odds', {}, api_key)
                    st.session_state['api_odds'] = result.get('data', {})
                    st.session_state['api_odds_match'] = choices[selected]
                except Exception as exc:
                    st.error(str(exc))
    if st.session_state.get('api_odds') is not None and st.session_state.get('api_odds_match'):
        st.subheader('Provider odds response')
        st.caption('Inspect bookmaker market structure here. Automatic odds comparisons will be enabled only after confirming the returned format and mapping teams correctly.')
        st.json(st.session_state['api_odds'], expanded=False)
