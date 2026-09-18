# NFL-Analytics

NFL dashboards, team efficiency comparisons, and experimental forecasts built
with React/TypeScript, Azure Functions, and nflverse data.

## Game forecasts

Open **Game Forecasts** in the navigation (or `/forecast`). Choose one of the
next 16 scheduled games, or select two teams and switch between home field and
a neutral venue. The page shows a predicted integer final score, its estimated
probability and two alternatives, expected average points, win chances, a
margin range, and historical prediction results.

Forecasts load schedules directly through `nflreadpy`; they do not require the
dashboard's SQL tables or a completed analytics ingestion. The first request
downloads schedule history and fits the model, so it can take longer. Network
access to the public nflverse data release on GitHub is required.

### How the score model works

- Uses the current season and three previous seasons of regular-season and
  postseason scores. January and February belong to the preceding season.
- Fits scoring and defensive effects for each team and team-specific home-field effects
  with ridge regression. Recent games receive more weight (365-day half-life);
  the regularization parameter is fixed at 20, not optimized against the test set.
- Learns a distribution of whole-number final-score pairs from completed games.
  Regularization smooths rare outcomes, and exponential tilting adjusts the
  distribution to each matchup's expected points. The most probable pair is
  the predicted final score; the next two pairs are alternatives. Scheduled
  postseason games cannot have tied predicted scores.
- Converts expected score margin to a win chance with a normal approximation.
  Its spread comes from training-period margin residuals, with a seven-point
  minimum standard deviation. These probabilities have not been calibrated.
- Tests on the final 20% of distinct game dates using a model fit only on earlier
  dates. Reports score MAE/RMSE, exact-score accuracy versus rounded averages,
  scoreline log loss versus a league baseline, margin MAE, winner accuracy,
  a home-team baseline, Brier score, and observed coverage of the nominal 80%
  interval. All score-distribution components use only the earlier training
  results. It then refits on all
  available completed history for future forecasts.
- Excludes the cutoff date and later results from training. The cutoff advances
  at 8am America/New_York, giving late games time to finish. Scheduled games
  whose kickoff has passed or which already have either score are excluded
  from the upcoming list.

The integer prediction is one possible final score, often with a small
probability; the decimal scores remain expected averages. Exact-score
probabilities are uncalibrated. Win chances use a separate normal-margin
approximation without a separate tie outcome; winner accuracy and Brier score
exclude actual ties.
Injuries, quarterback changes, weather, rest, and offseason roster changes are
not modeled. The displayed 80% margin range is nominal and may cover fewer than
80% of real outcomes.

See [the algorithm, assumptions, and reproducible backtest](docs/score-forecast.md).
This is a custom combination of established statistical techniques, not a claim
of industry-leading accuracy.

References: [nflverse schedule data](https://nflreadr.nflverse.com/articles/dictionary_schedules.html),
[ridge regression](https://sklearn.org/stable/modules/generated/sklearn.linear_model.Ridge.html),
[exponential tilting](https://web.mit.edu/~r/current/lib/R/library/boot/html/exp.tilt.html),
and [chronological evaluation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

### Run locally

Install Python dependencies and start the Azure Functions host with Python 3.11+
and Azure Functions Core Tools available:

```powershell
python -m pip install -r requirements.txt
func start --cors http://localhost:5173
```

The Functions host needs a local `local.settings.json` with
`FUNCTIONS_WORKER_RUNTIME` set to `python` (and the hosting configuration required
by your local Functions setup). Dashboard endpoints additionally use
`NFL_SQL_CONNECTION_STRING`; ingestion uses `NFL_STORAGE_ACCOUNT_NAME` and Azure
credentials. Forecast endpoints only need public data access.

Downloaded schedules and fitted models are cached in process for up to one hour.
The forecast service caps nflreadpy's shared download cache at one hour,
preserving shorter `NFLREADPY_CACHE_DURATION` settings. Fitted models are also
invalidated when the daily training cutoff changes. The page displays
the latest training game date, not a claim of live game coverage.

In `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:7071
```

Then:

```powershell
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173/forecast`. Use an empty API base only when your
hosting setup routes `/api` requests to the Functions app. Production static
hosting also needs an SPA fallback to `index.html` for direct `/forecast` visits.

### Forecast API

- `GET /api/forecasts`: upcoming fixtures with predictions, available teams,
  training cutoff, and model evaluation.
- `GET /api/forecast?home_team=BUF&away_team=MIA&neutral=false`: hypothetical
  matchup using the same model. Both teams must have completed game history.

The normal margin is always **home score minus away score**, including neutral
fixtures where home/away are only schedule labels. Score/probability values are
returned at full precision and formatted by the frontend.

`home_score` / `away_score` remain expected means for API compatibility.
`score_prediction` contains integer `home_score`, integer `away_score`, and
`probability`; `top_scorelines` contains up to three such objects, including
the primary prediction. `allow_ties` is false for scheduled postseason games;
hypothetical matchups use regular-season semantics.

### Checks

```powershell
python -m unittest discover -s tests -v
cd frontend
npm run build
npm run lint
```

The forecast tests use deterministic fixtures and mocked schedule downloads;
they cover chronological isolation, duplicates, missing history, venue symmetry,
probability normalization and mean matching, integer score selection, postseason
tie exclusion, upcoming filtering, cache invalidation, and API validation.
