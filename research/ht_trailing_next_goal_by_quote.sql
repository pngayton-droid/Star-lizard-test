-- Read-only TheStatsAPI stored-event study.
-- Bet365 last_seen is NOT guaranteed to be a pre-match price.
-- It is a proxy for relative favourite status, NOT a time-aligned quote.
-- Scoring events: goal, own_goal (credited to opponent), penalty_scored.
-- Discrepant HT/FT goal counts are excluded. 0-0 games are irrelevant to
-- the one-goal-trailing sample. Chronological event order is not fully audited.
WITH scoring_events AS (
  SELECT x.match_id, x.home_ht_goals hh, x.away_ht_goals ah,
         x.home_goals hf, x.away_goals af, x.home_ht_xg hx, x.away_ht_xg ax,
         v->>'period' period, (v->>'sequence')::int seq,
         CASE WHEN (v->>'type'='own_goal' AND v->'team'->>'name'=x.away_team)
                     OR (v->>'type'<>'own_goal' AND v->'team'->>'name'=x.home_team)
                THEN 'home'
              WHEN (v->>'type'='own_goal' AND v->'team'->>'name'=x.home_team)
                     OR (v->>'type'<>'own_goal' AND v->'team'->>'name'=x.away_team)
                THEN 'away' ELSE 'unknown' END scoring_side
  FROM historical_xg x
  JOIN historical_match_events e USING(match_id)
  CROSS JOIN LATERAL jsonb_array_elements(e.timeline_data->'events') v
  WHERE v->>'type' IN ('goal','own_goal','penalty_scored')
), reconciled AS (
  SELECT match_id, max(hh) hh, max(ah) ah, max(hf) hf, max(af) af,
         max(hx) hx, max(ax) ax,
         (array_agg(scoring_side ORDER BY seq)
           FILTER (WHERE period='second_half'))[1] first_2h,
         count(*) FILTER (WHERE scoring_side='home' AND period='first_half') counted_hh,
         count(*) FILTER (WHERE scoring_side='away' AND period='first_half') counted_ah,
         count(*) FILTER (WHERE scoring_side='home') counted_hf,
         count(*) FILTER (WHERE scoring_side='away') counted_af,
         count(*) FILTER (WHERE scoring_side='unknown'
                              OR period NOT IN ('first_half','second_half')) invalid
  FROM scoring_events GROUP BY match_id
), bet365 AS (
  SELECT o.match_id,
         (b->'markets'->'match_odds'->'home'->>'last_seen')::numeric home_quote,
         (b->'markets'->'match_odds'->'away'->>'last_seen')::numeric away_quote
  FROM historical_match_odds o
  CROSS JOIN LATERAL jsonb_array_elements(
    coalesce(o.odds_payload->'data'->'bookmakers','[]'::jsonb)) b
  WHERE b->>'bookmaker'='Bet365'
    AND b->'markets'->'match_odds'->'home'->>'last_seen' IS NOT NULL
    AND b->'markets'->'match_odds'->'away'->>'last_seen' IS NOT NULL
), eligible AS (
  SELECT r.*, CASE WHEN hh>ah THEN 'away' ELSE 'home' END trailing_side,
         CASE WHEN hh>ah THEN ax ELSE hx END trailing_ht_xg,
         CASE WHEN hh>ah THEN p.away_quote ELSE p.home_quote END trailing_quote,
         CASE WHEN hh>ah THEN p.home_quote ELSE p.away_quote END leader_quote
  FROM reconciled r JOIN bet365 p USING(match_id)
  WHERE abs(hh-ah)=1 AND hh=counted_hh AND ah=counted_ah
    AND hf=counted_hf AND af=counted_af AND invalid=0
)
SELECT CASE WHEN trailing_quote<leader_quote THEN 'Shorter-priced trailing team'
            WHEN trailing_quote>leader_quote THEN 'Longer-priced trailing team'
            ELSE 'Equal quote' END relative_quote,
       CASE WHEN trailing_ht_xg>=0.20 THEN 'xG 0.20+' ELSE 'xG below 0.20' END xg_band,
       count(*) matches, count(*) FILTER (WHERE first_2h=trailing_side) successes,
       round(100.0*count(*) FILTER (WHERE first_2h=trailing_side)/count(*),2) hit_pct,
       round(count(*)::numeric/nullif(count(*) FILTER (WHERE first_2h=trailing_side),0),3) fair_decimal
FROM eligible WHERE trailing_quote>1 AND leader_quote>1
GROUP BY 1,2 ORDER BY 1,2;
