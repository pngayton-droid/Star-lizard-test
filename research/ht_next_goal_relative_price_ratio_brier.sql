-- Stored StatsAPI only. Price ratio is from Bet365 last_seen, NOT verified pre-match.
-- One-goal HT trailing, score-reconciled events, fixed training cutoff and smoothing.
-- Existing StatsAPI records only; no provider calls.
-- Strength uses unverified Bet365 last_seen relative prices, not true pre-match odds.
-- Pre-July 2025 training only, fixed smoothing, date-separated validation and later test.
-- SQL score-reconciled timelines, not yet strict full-event chronology verified.
-- Read-only. Bet365 last_seen is not verified pre-match; relative strength proxy only.
-- Goal totals reconciled, not a full chronology audit.
-- Read-only chronological validation of a previously selected HT xG 0.20 screen.
-- These are descriptive outcomes, not a pristine untouched holdout:
-- the threshold was explored before this split.
-- All scoring events: goal, penalty_scored, own_goal (credited to opponent).
-- Requires exact official HT and FT score reconciliation.
WITH scoring AS (
 SELECT x.match_id,x.match_date,x.home_ht_goals hh,x.away_ht_goals ah,
        x.home_goals hf,x.away_goals af,x.home_ht_xg hx,x.away_ht_xg ax,
        v->>'period' period,(v->>'sequence')::int seq,
        CASE WHEN (v->>'type'='own_goal' AND v->'team'->>'name'=x.away_team)
                    OR (v->>'type'<>'own_goal' AND v->'team'->>'name'=x.home_team)
                  THEN 'home'
             WHEN (v->>'type'='own_goal' AND v->'team'->>'name'=x.home_team)
                    OR (v->>'type'<>'own_goal' AND v->'team'->>'name'=x.away_team)
                  THEN 'away' ELSE 'unknown' END side
 FROM historical_xg x JOIN historical_match_events e USING(match_id)
 CROSS JOIN LATERAL jsonb_array_elements(e.timeline_data->'events') v
 WHERE v->>'type' IN ('goal','own_goal','penalty_scored')
), reconciled AS (
 SELECT match_id,max(match_date) match_date,max(hh) hh,max(ah) ah,
        max(hf) hf,max(af) af,max(hx) hx,max(ax) ax,
        (array_agg(side ORDER BY seq) FILTER(WHERE period='second_half'))[1] first_2h,
        count(*) FILTER(WHERE side='home' AND period='first_half') chh,
        count(*) FILTER(WHERE side='away' AND period='first_half') cah,
        count(*) FILTER(WHERE side='home') chf,
        count(*) FILTER(WHERE side='away') caf,
        count(*) FILTER(WHERE side='unknown'
                            OR period NOT IN ('first_half','second_half')) invalid
 FROM scoring GROUP BY match_id
), eligible AS (
 SELECT *,CASE WHEN hh>ah THEN 'away' ELSE 'home' END trailing_side,
          CASE WHEN hh>ah THEN ax ELSE hx END trailing_ht_xg
 FROM reconciled
 WHERE abs(hh-ah)=1 AND hh=chh AND ah=cah
   AND hf=chf AND af=caf AND invalid=0
)
, quotes AS (
 SELECT o.match_id,
 (b->'markets'->'match_odds'->'home'->>'last_seen')::numeric hp,
 (b->'markets'->'match_odds'->'away'->>'last_seen')::numeric ap
 FROM historical_match_odds o
 CROSS JOIN LATERAL jsonb_array_elements(coalesce(o.odds_payload->'data'->'bookmakers','[]'::jsonb)) b
 WHERE b->>'bookmaker'='Bet365'
 AND b->'markets'->'match_odds'->'home'->>'last_seen' IS NOT NULL
 AND b->'markets'->'match_odds'->'away'->>'last_seen' IS NOT NULL
), classified AS (
 SELECT e.*,CASE WHEN trailing_side='home' THEN q.hp ELSE q.ap END trailing_quote,
 CASE WHEN trailing_side='home' THEN q.ap ELSE q.hp END leader_quote
 FROM eligible e JOIN quotes q USING(match_id)
 WHERE abs(hh-ah)=1
)
, samples AS (
 SELECT match_id,match_date,
 CASE WHEN trailing_quote>leader_quote THEN 'longer' WHEN trailing_quote<leader_quote THEN 'shorter' ELSE 'equal' END strength,
 CASE WHEN trailing_ht_xg>=0.20 THEN 'high' ELSE 'low' END xg_band,
 CASE WHEN trailing_quote / nullif(leader_quote,0) < 0.75 THEN 'very_shorter'
 WHEN trailing_quote / nullif(leader_quote,0) < 1.00 THEN 'moderate_shorter'
 WHEN trailing_quote / nullif(leader_quote,0) < 1.50 THEN 'near_or_moderate_longer'
 ELSE 'very_longer' END price_band,
 CASE WHEN first_2h=trailing_side THEN 1.0 ELSE 0.0 END outcome
 FROM classified WHERE trailing_ht_xg IS NOT NULL AND trailing_quote>1 AND leader_quote>1
), strength_train AS (
 SELECT strength,count(*) n,sum(outcome) wins FROM samples WHERE match_date<'2025-07-01' GROUP BY strength
), binary_train AS (
 SELECT strength,xg_band,count(*) n,sum(outcome) wins FROM samples WHERE match_date<'2025-07-01' GROUP BY strength,xg_band
), price_train AS (
 SELECT price_band,count(*) n,sum(outcome) wins FROM samples WHERE match_date<'2025-07-01' GROUP BY price_band
), price_xg_train AS (
 SELECT price_band,xg_band,count(*) n,sum(outcome) wins FROM samples WHERE match_date<'2025-07-01' GROUP BY price_band,xg_band
), predicted AS (
 SELECT s.*,CASE WHEN match_date<'2026-01-01' THEN 'validation' ELSE 'later_test' END period,
 (t.wins+2.0)/(t.n+4.0) p_strength,
 (b.wins+4.0*((t.wins+2.0)/(t.n+4.0)))/(b.n+4.0) p_binary,
 (p.wins+8.0*((t.wins+2.0)/(t.n+4.0)))/(p.n+8.0) p_price,
 (px.wins+8.0*((p.wins+8.0*((t.wins+2.0)/(t.n+4.0)))/(p.n+8.0)))/(px.n+8.0) p_price_xg
 FROM samples s JOIN strength_train t USING(strength)
 JOIN binary_train b USING(strength,xg_band)
 JOIN price_train p USING(price_band)
 JOIN price_xg_train px USING(price_band,xg_band)
 WHERE s.match_date>='2025-07-01'
)
SELECT period,count(*) n,
 round(avg(power(outcome-p_strength,2))::numeric,6) brier_strength,
 round(avg(power(outcome-p_binary,2))::numeric,6) brier_strength_xg,
 round(avg(power(outcome-p_price,2))::numeric,6) brier_price_band,
 round(avg(power(outcome-p_price_xg,2))::numeric,6) brier_price_band_xg
FROM predicted GROUP BY period ORDER BY period;