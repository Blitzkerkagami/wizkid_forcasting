-- WizKid Phase 5D: secure per-session time series for ARIMA forecasting.
-- Run after Phase 4, Phase 5A, and Phase 5B database scripts.

begin;

create or replace view public.learner_skill_features
with (security_invoker = true)
as
with ranked_attempts as (
    select
        qa.owner_id, qa.player_id, qa.skill, qa.session_id, qa.level,
        qa.difficulty, qa.is_correct, qa.timed_out, qa.response_time_ms,
        qa.attempted_at_utc,
        row_number() over (
            partition by qa.owner_id, qa.player_id, qa.skill
            order by qa.attempted_at_utc desc, qa.attempt_id desc
        ) as recency_rank
    from public.question_attempts as qa
),
aggregated as (
    select
        owner_id, player_id, skill,
        count(*)::integer as total_attempts,
        count(distinct session_id)::integer as total_sessions,
        count(*) filter (where is_correct)::integer as correct_attempts,
        count(*) filter (where timed_out)::integer as timed_out_attempts,
        round(avg(is_correct::integer)::numeric, 4) as overall_accuracy,
        round(avg(response_time_ms)::numeric, 2) as average_response_time_ms,
        round(avg(difficulty)::numeric, 2) as average_difficulty,
        max(level)::integer as highest_level_attempted,
        min(attempted_at_utc) as first_attempt_at,
        max(attempted_at_utc) as last_attempt_at,
        count(*) filter (where recency_rank <= 10)::integer as recent_attempt_count,
        round(avg(is_correct::integer) filter (where recency_rank <= 10)::numeric, 4)
            as recent_accuracy,
        round(avg(response_time_ms) filter (where recency_rank <= 10)::numeric, 2)
            as recent_average_response_time_ms,
        count(*) filter (where recency_rank between 11 and 20)::integer
            as previous_attempt_count,
        round(avg(is_correct::integer)
            filter (where recency_rank between 11 and 20)::numeric, 4)
            as previous_accuracy
    from ranked_attempts
    group by owner_id, player_id, skill
),
scored_sessions as (
    select gs.owner_id, gs.player_id, gs.skill,
        count(*)::integer as forecast_session_count
    from public.gameplay_sessions as gs
    where gs.completion_status in ('completed', 'failed')
      and gs.ended_at_utc is not null
      and gs.attempted_questions > 0
      and gs.score_percent is not null
    group by gs.owner_id, gs.player_id, gs.skill
),
features as (
    select aggregated.*,
        coalesce(scored_sessions.forecast_session_count, 0)::integer
            as forecast_session_count,
        case when previous_attempt_count >= 5
            then round(recent_accuracy - previous_accuracy, 4)
            else null end as accuracy_trend_delta
    from aggregated
    left join scored_sessions using (owner_id, player_id, skill)
)
select
    owner_id, player_id, skill, total_attempts, total_sessions,
    correct_attempts, timed_out_attempts, overall_accuracy,
    average_response_time_ms, average_difficulty, highest_level_attempted,
    first_attempt_at, last_attempt_at, recent_attempt_count, recent_accuracy,
    recent_average_response_time_ms, previous_attempt_count, previous_accuracy,
    accuracy_trend_delta,
    (total_attempts >= 10 and forecast_session_count >= 5)
        as is_forecast_eligible,
    greatest(0, 10 - total_attempts)::integer as attempts_needed,
    case
        when total_attempts < 10 then 'needs_more_attempts'
        when forecast_session_count < 5 then 'needs_more_sessions'
        else 'ready'
    end as data_quality_status,
    case
        when accuracy_trend_delta is null then 'insufficient_history'
        when accuracy_trend_delta >= 0.10 then 'improving'
        when accuracy_trend_delta <= -0.10 then 'declining'
        else 'stable'
    end as observed_trend,
    forecast_session_count,
    greatest(0, 5 - forecast_session_count)::integer as sessions_needed
from features;

revoke all on table public.learner_skill_features from public;
revoke all on table public.learner_skill_features from anon;
grant select on table public.learner_skill_features to authenticated;
grant select on table public.learner_skill_features to service_role;

create or replace view public.learner_skill_arima_series
with (security_invoker = true)
as
with session_rows as (
    select
        gs.owner_id, gs.player_id, gs.skill, gs.session_id,
        gs.ended_at_utc as observed_at, gs.level, gs.attempted_questions,
        gs.correct_answers, gs.score_percent::numeric(5, 2) as score_percent,
        row_number() over (
            partition by gs.owner_id, gs.player_id, gs.skill
            order by gs.ended_at_utc, gs.session_id
        )::integer as session_index,
        count(*) over (
            partition by gs.owner_id, gs.player_id, gs.skill
        )::integer as total_sessions,
        sum(gs.attempted_questions) over (
            partition by gs.owner_id, gs.player_id, gs.skill
        )::integer as total_attempts,
        sum(gs.correct_answers) over (
            partition by gs.owner_id, gs.player_id, gs.skill
        )::integer as total_correct_answers,
        max(gs.level) over (
            partition by gs.owner_id, gs.player_id, gs.skill
        )::integer as highest_level_attempted
    from public.gameplay_sessions as gs
    where gs.completion_status in ('completed', 'failed')
      and gs.ended_at_utc is not null
      and gs.attempted_questions > 0
      and gs.score_percent is not null
)
select
    owner_id, player_id, skill, session_id, observed_at, session_index,
    level, attempted_questions, correct_answers, score_percent,
    total_sessions, total_attempts, total_correct_answers,
    highest_level_attempted,
    (total_attempts >= 10 and total_sessions >= 5) as is_forecast_eligible
from session_rows;

revoke all on table public.learner_skill_arima_series from public;
revoke all on table public.learner_skill_arima_series from anon;
revoke all on table public.learner_skill_arima_series from authenticated;
grant select on table public.learner_skill_arima_series to service_role;

commit;
