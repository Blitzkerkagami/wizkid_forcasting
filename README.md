# WizKid forecasting service (Phase 5B)

This is a small server-side Python service. It reads only aggregated learner-skill
features from Supabase, generates an explainable seven-day forecast, and writes the
result to the protected `learner_forecasts` table. Unity must never receive or call
the Supabase secret key.

## 1. Apply the database migration

In the Supabase SQL Editor, run:

1. `../supabase/schema/phase5b_forecasting_worker.sql`
2. `../supabase/tests/phase5b_worker_security_checks.sql`

## 2. Create server-only environment values

Copy `.env.example` to `.env` on the server and set:

- `SUPABASE_URL`: the same project URL used by Unity;
- `SUPABASE_SECRET_KEY`: a new `sb_secret_...` key from Supabase project API keys;
- `FORECAST_JOB_TOKEN`: a random value of at least 32 characters used only by the
  administrator that starts a manual forecast run;
- `CRON_SECRET`: a different random value of at least 32 characters. Vercel uses
  this to authenticate automatic scheduled runs.

Never add `.env` to source control, Unity Resources, a mobile build, screenshots, or
chat messages. The service intentionally sends the secret key only through the
Supabase `apikey` header, not as a bearer token.

## 3. Run locally

Install Python 3.11 or newer, then from this `forecasting` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The service automatically reads the local `.env` file. On a deployed host, use the
host's secret/environment settings instead of uploading that file.

Health check:

```text
GET http://127.0.0.1:8000/health
```

Protected forecast run:

```text
POST http://127.0.0.1:8000/forecast/run
X-Job-Token: <FORECAST_JOB_TOKEN>
Content-Type: application/json

{}
```

Use `{"player_id":"<uuid>"}` to process one learner, or `{}` to process every
eligible learner. The command-line equivalent is `python -m app.worker`.

## 4. Deploy to Vercel and schedule

Import this repository into Vercel and add every value from `.env.example` under
**Project Settings > Environment Variables**. Keep `SUPABASE_SECRET_KEY`,
`FORECAST_JOB_TOKEN`, and `CRON_SECRET` available only to the backend.

`vercel.json` runs `GET /forecast/cron` every day at `01:00 UTC` (`09:00` in the
Philippines) and allows the function to run for up to 60 seconds. Vercel automatically
sends `CRON_SECRET` through the `Authorization: Bearer ...` header. Preview deployments
do not execute this production cron.

The included Dockerfile remains available for other container hosts. It is not needed
for a normal Vercel Python deployment. Never expose either trigger secret to Unity.

## Model behavior

`bayesian-recency-v1` combines a conservative Beta prior, overall accuracy, the
latest ten attempts, recent trend, and timeout rate. Confidence grows with attempts,
sessions, and usable history. This is a transparent baseline suitable for the first
data collection period; it should be evaluated against real outcomes before being
described as predictive AI.

