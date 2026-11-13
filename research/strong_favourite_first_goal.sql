-- PRO STARLIZARD 2.0: first-goal comeback research
-- READ ONLY. Existing TheStatsAPI-derived Supabase tables; no provider requests.
-- Exploratory only: last_seen Bet365 prices are NOT confirmed pre-kickoff timestamps.
-- Excludes first goals recorded as own goals, but further timeline VAR audit required.
-- Never claim these are live tradable ROI or pre-match betting odds.
WITH prices AS (
 SELECT h.match_id,h.competition_id,h.home_team,h.away_team,h.home_goals,h.away_goals,
  (SELECT NULLIF(bk->'markets'->'match_odds'->'home'->>'last_seen','')::numeric
   FROM jsonb_array_elements(COALESCE(o.odds_payload->'data'->'bookmakers','[]'::jsonb)) bk
   WHERE bk->>'bookmaker'='Bet365' LIMIT 1) home_price,
  (SELECT NULLIF(bk->'markets'->'match_odds'->'away'->>'last_seen','')::numeric
   FROM jsonb_array_elements(COALESCE(o.odds_payload->'data'->'bookmakers','[]'::jsonb)) bk
   WHERE bk->>'bookmaker'='Bet365' LIMIT 1) away_price,
  e.timeline_data
 FROM historical_xg h
 JOIN historical_match_odds o USING(match_id)
 JOIN historical_match_events e USING(match_id)
), first_goal AS (
 SELECT p.*,
  (SELECT ev FROM jsonb_array_elements(COALESCE(p.timeline_data->'events','[]'::jsonb)) ev
   WHERE ev->>'type' IN ('goal','own_goal')
   ORDER BY (ev->>'minute')::int,COALESCE((ev->>'extra_time')::int,0),
            COALESCE((ev->>'sequence')::int,0) LIMIT 1) goal_event
 FROM prices p
), cases AS (
 SELECT *,
 CASE WHEN home_price < 1.50 AND (away_price IS NULL OR home_price < away_price) THEN 'home'
      WHEN away_price < 1.50 AND (home_price IS NULL OR away_price < home_price) THEN 'away'
 END AS favourite
 FROM first_goal
)
SELECT competition_id,COUNT(*) AS cases,
 COUNT(*) FILTER (WHERE (favourite='home' AND home_goals>away_goals)
                     OR (favourite='away' AND away_goals>home_goals)) AS favourite_won,
 COUNT(*) FILTER (WHERE home_goals=away_goals) AS drew,
 COUNT(*) FILTER (WHERE (favourite='home' AND home_goals<away_goals)
                     OR (favourite='away' AND away_goals<home_goals)) AS favourite_lost
FROM cases
WHERE favourite IS NOT NULL AND goal_event->>'type'='goal'
 AND (goal_event->>'minute')::int <=45
 AND ((favourite='home' AND goal_event->'team'->>'name'=away_team)
   OR (favourite='away' AND goal_event->'team'->>'name'=home_team))
GROUP BY competition_id ORDER BY cases DESC;
