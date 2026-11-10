
"""PRO STARLIZARD V5.7 — bounded-memory halftime corners/cards research.

Read-only Supabase. Historical frequencies are descriptive, not calibrated forecasts.
"""
from datetime import date
import math
import streamlit as st

PAGE_SIZE = 200
MAX_CANDIDATES = 3000
MIN_SAMPLE = 30


def _num(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _count(value):
    n = _num(value)
    return int(n) if n is not None and n >= 0 and n.is_integer() else None


def _market(stats, name):
    try:
        periods = stats['overview'][name]
        out = {}
        for period in ('all', 'first_half', 'second_half'):
            h = _count(periods[period]['home'])
            a = _count(periods[period]['away'])
            if h is None or a is None:
                return None
            out[period] = h + a
        if out['all'] != out['first_half'] + out['second_half']:
            return None
        return out
    except (KeyError, TypeError, AttributeError):
        return None


def _get_candidates(db, ht_home, ht_away, home_xg, away_xg, tolerance, cutoff):
    """Read at most MAX_CANDIDATES matching xG rows, no raw event JSON."""
    candidates = []
    offset = 0
    while len(candidates) < MAX_CANDIDATES:
        limit = min(PAGE_SIZE, MAX_CANDIDATES - len(candidates))
        q = (db.table('historical_xg')
             .select('match_id,match_date,home_ht_xg,away_ht_xg')
             .eq('home_ht_goals', ht_home)
             .eq('away_ht_goals', ht_away)
             .gte('home_ht_xg', max(0, home_xg - tolerance))
             .lte('home_ht_xg', home_xg + tolerance)
             .gte('away_ht_xg', max(0, away_xg - tolerance))
             .lte('away_ht_xg', away_xg + tolerance)
             .lt('match_date', cutoff)
             .order('match_date', desc=True)
             .order('match_id')
             .range(offset, offset + limit - 1))
        batch = q.execute().data or []
        if not batch:
            break
        candidates.extend(batch)
        offset += len(batch)
        if len(batch) < limit:
            break
    return candidates


def _collect(db, candidates, corner_total, corner_tol, yellow_total, yellow_tol):
    """Fetch event JSON in bounded chunks and retain only small numeric summaries."""
    corners, yellows = [], []
    received = 0
    for i in range(0, len(candidates), PAGE_SIZE):
        ids = [str(x['match_id']) for x in candidates[i:i + PAGE_SIZE] if x.get('match_id')]
        if not ids:
            continue
        rows = (db.table('historical_match_events')
                .select('match_id,stats_data')
                .in_('match_id', ids)
                .execute().data or [])
        received += len(rows)
        for row in rows:
            stats = row.get('stats_data') or {}
            c = _market(stats, 'corner_kicks')
            if c is not None and abs(c['first_half'] - corner_total) <= corner_tol:
                corners.append((c['second_half'], c['all']))
            y = _market(stats, 'yellow_cards')
            if y is not None and abs(y['first_half'] - yellow_total) <= yellow_tol:
                yellows.append((y['second_half'], y['all']))
        del rows
    return corners, yellows, received


def _card(label, records, index, line):
    n = len(records)
    with st.container(border=True):
        st.markdown(f'**{label}**')
        if n < MIN_SAMPLE:
            st.caption(f'{n} matches — price withheld (minimum {MIN_SAMPLE})')
            return
        wins = sum(row[index] > line for row in records)
        probability = wins / n
        a, b = st.columns(2)
        a.metric('Historical rate', f'{probability:.1%}')
        b.metric('Inverse frequency', f'{1 / probability:.2f}' if probability else '—')
        st.caption(f'{wins}/{n} historical matches')


def _section(title, records, second_lines, full_lines, unit):
    st.subheader(title)
    st.caption(f'{len(records)} verified comparable {unit} records')
    st.markdown('**Second-half totals**')
    for line in second_lines:
        _card(f'Over {line:.1f} second-half {unit}', records, 0, line)
    st.markdown('**Full-match totals (from halftime)**')
    for line in full_lines:
        _card(f'Over {line:.1f} full-match {unit}', records, 1, line)


def render_halftime_markets(db):
    st.header('🦎 V5.7 Halftime Corners & Cards')
    st.caption('Bounded historical lookup; no full-database download or persistent dataset cache.')
    c1, c2 = st.columns(2)
    with c1:
        hh = st.number_input('Home HT goals', 0, 15, 0, key='v57_hh')
        hx = st.number_input('Home HT xG', 0.0, 10.0, 0.85, 0.05, key='v57_hx')
        hc = st.number_input('Home HT corners', 0, 30, 3, key='v57_hc')
        hy = st.number_input('Home HT yellows', 0, 20, 1, key='v57_hy')
    with c2:
        ah = st.number_input('Away HT goals', 0, 15, 1, key='v57_ah')
        ax = st.number_input('Away HT xG', 0.0, 10.0, 0.35, 0.05, key='v57_ax')
        ac = st.number_input('Away HT corners', 0, 30, 2, key='v57_ac')
        ay = st.number_input('Away HT yellows', 0, 20, 2, key='v57_ay')
    with st.expander('Matching settings'):
        xt = st.slider('HT xG tolerance', 0.10, 1.00, 0.30, 0.05, key='v57_xt')
        ct = st.slider('HT corner tolerance', 0, 5, 2, key='v57_ct')
        yt = st.slider('HT yellow tolerance', 0, 4, 1, key='v57_yt')
        cutoff = st.date_input('Fixture date', value=date.today(), max_value=date.today(), key='v57_cutoff')
    st.caption('Corner/card matching uses combined home + away first-half totals, not team-specific splits.')
    if not st.button('Calculate historical market rates', type='primary', use_container_width=True, key='v57_run'):
        st.info('Enter halftime observations, then tap Calculate. No historical data is loaded until then.')
        return
    try:
        with st.spinner('Querying comparable matches in bounded batches...'):
            candidates = _get_candidates(db, int(hh), int(ah), float(hx), float(ax), float(xt), cutoff.isoformat())
            corners, yellows, received = _collect(db, candidates, int(hc + ac), int(ct), int(hy + ay), int(yt))
    except Exception as exc:
        st.error(f'Historical lookup failed: {type(exc).__name__}: {exc}')
        return
    st.caption(f'{len(candidates)} score/xG candidates; {received} event records fetched. Maximum {MAX_CANDIDATES} candidates; most recent first.')
    if len(candidates) == MAX_CANDIDATES:
        st.warning('Candidate cap reached. Results reflect only the latest matching records, not the entire history.')
    _section('🚩 Corners', corners, [3.5, 4.5, 5.5, 6.5], [7.5, 8.5, 9.5, 10.5, 11.5], 'corners')
    _section('🟨 Yellow cards', yellows, [1.5, 2.5, 3.5, 4.5], [3.5, 4.5, 5.5, 6.5], 'yellow cards')
    st.info('Descriptive historical frequencies only. Not validated live probabilities, bookmaker card points, or demonstrated betting value.')
