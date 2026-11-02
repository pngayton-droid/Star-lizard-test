"""Pro Star Lizard — mobile Asian pricing with optional historical CSV inputs.

Exploratory model only. No API calls or bookmaker-independent validated predictions.
"""
import math
from itertools import product
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Star Lizard | Asian Pricing Mobile', layout='centered')
st.title('Pro Star Lizard | Asian Pricing Mobile')
st.caption('Mobile-first exploratory Asian handicap and goal totals. Historical estimates are not calibrated predictions.')

@st.cache_data
def outcome_grid(hxg, axg, cap=25):
    def poisson(lam):
        p = math.exp(-lam)
        result = [p]
        for n in range(1, cap + 1):
            p *= lam / n
            result.append(p)
        return result
    hp, ap = poisson(hxg), poisson(axg)
    grid = [(h, a, x*y) for (h,x),(a,y) in product(enumerate(hp), enumerate(ap))]
    return grid, 1-sum(p for _,_,p in grid)

def leg(v):
    return (v > 1e-9) - (v < -1e-9)

def settle(diff, line):
    q = round(line*4)
    if abs(line*4-q)>1e-7:
        raise ValueError('Quarter-line increments required')
    if q%2:
        lower = math.floor(line*2)/2
        return (leg(diff+lower)+leg(diff+lower+0.5))/2
    return leg(diff+line)

def price(grid, kind, line):
    bins = {1:0., .5:0., 0:0., -.5:0., -1:0.}
    for h,a,p in grid:
        diff = {'Home handicap':h-a, 'Away handicap':a-h,
                'Over goals':h+a, 'Under goals':-h-a}[kind]
        effective_line = -line if kind=='Over goals' else line
        bins[settle(diff,effective_line)] += p
    w = bins[1]+.5*bins[.5]
    l = bins[-1]+.5*bins[-.5]
    return bins, (1+l/w if w else float('inf')), w, l

st.subheader('1. Match inputs')
home_name = st.text_input('Home team', 'Newcastle')
away_name = st.text_input('Away team', 'Everton')
file = st.file_uploader('Historical analysis CSV (optional)', type=['csv'])
mode = st.radio('Expected-goals source', ['Manual assumptions', 'Historical CSV estimate'],
                disabled=file is None)
if file is None:
    st.caption('Upload the historical analysis CSV to enable data-derived estimates. Manual inputs work without a file.')

hxg_default, axg_default = 1.55, 1.35
if file is not None and mode == 'Historical CSV estimate':
    try:
        df = pd.read_csv(file)
        required = {'Team','H/A','xG','xG against'}
        if not required.issubset(df.columns):
            st.error('CSV is missing: '+', '.join(sorted(required-set(df.columns))))
            st.stop()
        df['xG'] = pd.to_numeric(df['xG'], errors='coerce')
        df['xG against'] = pd.to_numeric(df['xG against'], errors='coerce')
        team_options = sorted(df['Team'].dropna().astype(str).unique())
        if len(team_options)<2:
            st.error('CSV needs two different teams.')
            st.stop()
        home_pick = st.selectbox('Historical home team', team_options, index=0)
        away_pick = st.selectbox('Historical away team', team_options,
                                 index=1 if len(team_options)>1 else 0)
        if home_pick==away_pick:
            st.warning('Select two different teams.')
            st.stop()
        home_name,away_name=home_pick,away_pick
        home = df[(df['Team']==home_pick)&(df['H/A']=='H')]
        away = df[(df['Team']==away_pick)&(df['H/A']=='A')]
        if home[['xG','xG against']].dropna().empty or away[['xG','xG against']].dropna().empty:
            st.error('Not enough home/away xG records for these teams.')
            st.stop()
        home_att = home['xG'].mean()
        away_def = away['xG against'].mean()
        away_att = away['xG'].mean()
        home_def = home['xG against'].mean()
        hxg_default = (home_att+away_def)/2
        axg_default = (away_att+home_def)/2
        st.write(f'**{home_pick} home:** {home_att:.2f} xG for, {home_def:.2f} xG against ({len(home)} games)')
        st.write(f'**{away_pick} away:** {away_att:.2f} xG for, {away_def:.2f} xG against ({len(away)} games)')
        st.caption('Simple 50/50 blend of team attacking xG and opponent defensive xGA. No opponent-strength, schedule, league, recency or injury adjustments. Not a calibrated forecast.')
    except Exception as exc:
        st.error(f'Could not process CSV: {exc}')
        st.stop()

hxg = st.number_input(f'{home_name} expected goals', .05, 6., float(round(hxg_default,2)), .05)
axg = st.number_input(f'{away_name} expected goals', .05, 6., float(round(axg_default,2)), .05)
if mode=='Manual assumptions':
    st.caption('These are manual assumptions, not verified fixture predictions.')

grid,tail=outcome_grid(hxg,axg)
if tail>1e-7:
    st.warning(f'Score grid tail: {tail:.5%}')

st.subheader('2. Choose your Asian market')
kind=st.selectbox('Market', ['Home handicap','Away handicap','Over goals','Under goals'])
lines=[i/4 for i in range(-12,13)] if 'handicap' in kind else [i/4 for i in range(2,25)]
default=0.0 if 'handicap' in kind else 2.5
line=st.selectbox('Line',lines,index=lines.index(default),format_func=lambda x:f'{x:+.2f}' if 'handicap' in kind else f'{x:.2f}')
bins,fair,w,l=price(grid,kind,line)
st.metric('Model fair decimal odds',f'{fair:.3f}')
st.write(f'**Full win:** {bins[1]:.1%} · **Half win:** {bins[.5]:.1%}')
st.write(f'**Push:** {bins[0]:.1%} · **Half loss:** {bins[-.5]:.1%} · **Full loss:** {bins[-1]:.1%}')
quote=st.number_input('Bookmaker odds (optional comparison)',1.01,1000.,1.95,.01)
ev=w*(quote-1)-l
st.metric('Model expected ROI',f'{ev:+.2%}')
st.caption('Positive model ROI does not establish a betting edge. It is conditional on the chosen expected-goals inputs and unvalidated model assumptions.')

st.subheader('3. Compact comparison')
if 'handicap' in kind:
    other='Away handicap' if kind=='Home handicap' else 'Home handicap'
    pairs=[(kind,line),(other,-line)]
else:
    other='Under goals' if kind=='Over goals' else 'Over goals'
    pairs=[(kind,line),(other,line)]
for k,v in pairs:
    b,f,_,_=price(grid,k,v)
    st.write(f'**{k} {v:+.2f}** — fair odds **{f:.3f}**')

with st.expander('Full fair-price tables and CSV export'):
    rows=[]
    for k in ('Home handicap','Away handicap','Over goals','Under goals'):
        ls=[i/4 for i in range(-12,13)] if 'handicap' in k else [i/4 for i in range(2,25)]
        for ln in ls:
            b,f,_,_=price(grid,k,ln)
            rows.append({'Market':k,'Line':ln,'Fair odds':round(f,3),
                         'Full win %':round(b[1]*100,2),'Half win %':round(b[.5]*100,2),
                         'Push %':round(b[0]*100,2),'Half loss %':round(b[-.5]*100,2),
                         'Full loss %':round(b[-1]*100,2)})
    all_prices=pd.DataFrame(rows)
    st.dataframe(all_prices[['Market','Line','Fair odds']],hide_index=True,use_container_width=True)
    st.download_button('Download full pricing CSV',all_prices.to_csv(index=False).encode(),
                       'starlizard_asian_mobile_prices.csv','text/csv')

st.caption('Next: proper team-strength model, time-aware backtesting and comparison with historical market prices. Corners require a separate distribution.')
