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


# Automatic parsing of the confirmed provider match_odds schema.
# Team-to-model mapping remains explicit: no silent guesses.
if st.session_state.get('api_odds') and st.session_state.get('api_odds_match'):
    st.subheader('Bookmaker 1X2 prices')
    st.caption('Odds for match ID: ' + str(st.session_state['api_odds_match']))
    odds_payload = st.session_state['api_odds']
    bookmaker_rows = []
    for bk in odds_payload.get('bookmakers', []):
        if not isinstance(bk, dict):
            continue
        market_prices = bk.get('markets', {}).get('match_odds', {})
        row = {'Bookmaker': bk.get('bookmaker', 'Unknown')}
        valid = True
        for outcome in ('home', 'draw', 'away'):
            selection = market_prices.get(outcome, {})
            if not isinstance(selection, dict):
                valid = False
                break
            for quote_type in ('opening', 'last_seen'):
                try:
                    quote = float(selection.get(quote_type))
                    if not (1.0 < quote < 10000.0):
                        raise ValueError('Invalid quote')
                    row[f'{outcome}_{quote_type}'] = quote
                except (TypeError, ValueError):
                    row[f'{outcome}_{quote_type}'] = None
        if valid:
            prices = [row.get(f'{x}_last_seen') for x in ('home', 'draw', 'away')]
            row['Overround %'] = round(100 * (sum(1 / x for x in prices) - 1), 2) if all(prices) else None
            bookmaker_rows.append(row)
    if bookmaker_rows:
        st.dataframe(pd.DataFrame(bookmaker_rows), hide_index=True, use_container_width=True)
        st.caption('Last seen means last recorded by the provider, not guaranteed live or currently available.')
        st.subheader('Compare 1X2 prices to the model (manual fixture matching)')
        st.warning('Confirm the selected league and both teams are the SAME fixture as the API match. Do not compare prices from different matches.')
        compare_league = st.selectbox('Model league for API fixture', leagues, key='api_compare_league')
        compare_teams = sorted({team for div, team in m.team if div == compare_league})
        if len(compare_teams) >= 2:
            model_home = st.selectbox('API home team in historical database', compare_teams, key='api_compare_home')
            model_away = st.selectbox('API away team in historical database', compare_teams, index=1, key='api_compare_away')
            selected_bk = st.selectbox('Bookmaker to compare', [row['Bookmaker'] for row in bookmaker_rows], key='api_compare_bookmaker')
            quote_kind = st.radio('Which prices?', ['last_seen', 'opening'], horizontal=True, key='api_quote_kind')
            confirmed = st.checkbox('I have verified the home and away teams match the selected API fixture', key='api_teams_confirmed')
            if confirmed:
                if model_home == model_away:
                    st.error('Home and away cannot be the same team.')
                else:
                    match_pred = m.predict(compare_league, model_home, model_away)
                    if match_pred is None:
                        st.error('Not enough historical matches for these teams.')
                    else:
                        match_prices = price(match_pred[0], match_pred[1])
                        selected_row = next(row for row in bookmaker_rows if row['Bookmaker'] == selected_bk)
                        comparison = []
                        for outcome, name in [('home', 'Home win'), ('draw', 'Draw'), ('away', 'Away win')]:
                            offered = selected_row.get(f'{outcome}_{quote_kind}')
                            probability = match_prices['probabilities'][outcome]
                            comparison.append({
                                'Outcome': name,
                                'Model probability': f'{probability:.1%}',
                                'Model fair odds': round(1 / probability, 2),
                                'Bookmaker odds': offered,
                                'Model EV %': round(100 * (probability * offered - 1), 2) if offered else None,
                            })
                        st.dataframe(pd.DataFrame(comparison), hide_index=True, use_container_width=True)
                        st.caption('Unvalidated theoretical expected values, not betting recommendations. Bookmaker prices may be stale. Historical data may not include current-season form.')
    else:
        st.info('No valid 1X2 prices found in this odds response.')
