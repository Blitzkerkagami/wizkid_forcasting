-- Run after phase5d_arima_forecasting.sql.

select
    has_table_privilege('anon', 'public.learner_skill_arima_series', 'select')
        as anon_can_read_arima_series,
    has_table_privilege('authenticated', 'public.learner_skill_arima_series', 'select')
        as authenticated_can_read_arima_series,
    has_table_privilege('service_role', 'public.learner_skill_arima_series', 'select')
        as service_can_read_arima_series;
-- Expected: false, false, true.

select c.relname, c.reloptions
from pg_class as c
where c.relnamespace = 'public'::regnamespace
  and c.relname in ('learner_skill_features', 'learner_skill_arima_series')
order by c.relname;
-- Expected: both views include security_invoker=true.

select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'learner_skill_features'
  and column_name in ('forecast_session_count', 'sessions_needed')
order by column_name;
-- Expected: two integer columns.
