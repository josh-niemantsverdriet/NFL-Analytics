# NFL Analytics

React/TypeScript dashboards and an Azure Functions API using nflverse data.

- **Dashboard:** league rankings, descriptive offense-versus-defense comparisons,
  player leaders, and recent results. Rankings and comparisons share one team-data request.
- **Team pages:** offense, defense, rankings, leaders, and results.
- **Game Forecasts (`/forecast`):** integer final-score predictions, alternatives,
  expected points, win/loss/tie chances, and historical performance.

## Forecast methodology

The `ridge-smooth-score-v5` model fits recency-weighted offense and defense ratings,
with a shared home-field advantage and regularized team deviations. A smoothed
distribution of final scores is exponentially tilted to match expected points.
It begins with score marginals and limits the influence of historical exact
score pairs, so a frequent league-wide final cannot become a generic forecast.
Scorelines, win/loss/tie probabilities, and margin intervals all come from that
distribution. The headline is a central integer score minimizing expected point
error; separately listed exact outcomes are only the highest-probability pairs,
each still unlikely.
Scheduled postseason games exclude ties.

Recency half-life (120, 180 or 270 days) and pair dependence (0%, 5%, or 10%) are selected using inner
chronological validation. Regression weights are normalized so faster decay
does not accidentally increase regularization. Four
expanding-window test blocks evaluate the complete procedure using only earlier
results; the production model then refits all eligible history. Forecasts use
current-season and three preceding seasons of public schedule results, without
requiring SQL or analytics ingestion. The cutoff advances at 8am Eastern and
excludes games on or after that date; downloads and fitted models cache for up
to an hour.

See [the algorithm and API semantics](docs/score-forecast.md),
[research and measured tradeoffs](docs/application-research.md),
[the v5 score-distribution overhaul](docs/score-distribution-overhaul.md), and
[the earlier 34–10 and recency investigation](docs/forecast-recency-investigation.md).

## Run locally

Python 3.11+, Azure Functions Core Tools, and Node 22 are required.

```powershell
python -m pip install -r requirements.txt
func start --cors http://localhost:5173
```

The Functions host needs its local hosting settings and
`FUNCTIONS_WORKER_RUNTIME=python`. Dashboard endpoints use
`NFL_SQL_CONNECTION_STRING`; ingestion uses `NFL_STORAGE_ACCOUNT_NAME` and Azure
credentials. Keep credentials in local/Azure settings, outside version control.
Forecast endpoints need access to public nflverse GitHub data releases.

Set `VITE_API_BASE_URL=http://localhost:7071` in `frontend/.env.local`, then:

```powershell
cd frontend
npm ci
npm run dev
```

An empty API base uses same-origin `/api` routing. Production uses the tracked
`frontend/.env.production`; SPA fallback is configured in
`frontend/public/staticwebapp.config.json`.

## Validate

```powershell
python -m unittest discover -s tests -v
python -m src.forecast_simulation --seeds 48 --seasons 8 --matchups 96
python -m src.forecast_backtest --schedules data/forecast/schedules.parquet --before 2026-09-17
cd frontend
npm test
npm run lint
npm run build
```

The extensive stress command generates **104,832 games** across 48 seeded runs
and checks **4,608 forecasts**. Unit tests additionally cover 6,552 simulated
games, 64,000 play-by-play rows, 2,000 corrupt/duplicate rows, and 3,200 frontend
ranking cases. Simulations test robustness, not real-game accuracy. The optional
backtest command needs a downloaded nflverse schedule parquet; data files are
not committed.

## Deployment

Pushing `main` deploys the frontend after the reusable Python/frontend quality
checks succeed. The Function App is deployed separately from the repository root:

```powershell
func azure functionapp publish <FUNCTION_APP_NAME> --python --build remote
```

After deploying these analytics changes, run the existing authenticated
`POST /api/analyze` operation for the desired snapshot to recompute stored team
metrics. No schema migration is needed. Existing SQL snapshots do not change
until analysis/ingestion runs again.

Send JSON with `season` and `snapshot_date` for an existing ingested snapshot,
and supply the Function key in the `x-functions-key` header.

Deploy both frontend and backend for the new projected-score semantics. The backend API
version identifies the new semantics; see the forecast documentation before
updating other consumers.
