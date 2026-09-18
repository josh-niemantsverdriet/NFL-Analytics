# Forecast algorithm and API

Model version: `ridge-smooth-score-v5`.

## Expected points

For scoring team `i` against opponent `j`, the regression estimates:

`points = league intercept + offense_i + defense_j + venue effect`.

A non-neutral game adds half of the home team's venue effect to its score and
subtracts half from the away score. The venue effect is a shared league parameter
plus a regularized team deviation. This partial pooling prevents teams with
little home history from having their entire home advantage shrunk toward zero.
Ridge alpha remains 20. Game weights decay with a half-life chosen from 120,
180 or 270 days using mean squared expected-point error on inner validation
dates. Histories too short for selection use 180 days. Before regression,
weights are normalized to mean one so faster decay does not silently increase
Ridge shrinkage by reducing total weight. Distribution counts retain raw
recency weights. All selection repeats inside each outer evaluation fold.
The API reports the selected half-life and each season's share of training
weight; current-season game counts appear beside each team's score.

## Integer final scores

The base distribution starts with independent, symmetric home/away pooled
league score marginals, weighted by recency. Each marginal receives two
pseudo-observations from a nonnegative discrete Gaussian centered on training
scores, using training standard deviation with a seven-point floor. This makes
the model learn individual NFL-like scores without treating a repeated
historical pair as a universal game result.

A limited **0%, 5%, or 10%** blend of the observed symmetric score-pair
histogram preserves some league-level score dependence. Its value is selected
using natural-log exact-score loss on inner validation dates. The 10% cap is
intentional: larger direct-pair weights restored repeated modes such as 34-10
in historical evaluation. Selection requires at least 200 input games, 100
inner training games, and 20 usable validation games. The split uses the first
80% of distinct training dates. Recency candidates are evaluated on all usable
later games; then at most 48 deterministically spaced later games select pair
dependence. Each regression and distribution sees only the inner training
dates. Selected settings are refit on all supplied training results.
Insufficient histories use 10% pair dependence.

For matchup means `mu_home` and `mu_away`, solve

`p(h,a) = q(h,a) * exp(theta_home*h + theta_away*a) / Z`

subject to the two expected scores equaling those means. This minimum-relative-
entropy exponential tilt preserves common NFL score patterns. Computation uses
log-space normalization, an analytic gradient, and a 0.00001-point convergence
check. Zero means are boundary distributions. The three most probable exact
outcomes remain in `top_scorelines`.

The headline `score_prediction` is labeled a **typical score estimate**, not a
most-likely exact final. It minimizes
`E[|home_score - H| + |away_score - A|]` over score pairs with positive model
probability. This is the Bayes point forecast for per-team absolute error,
normally the two marginal medians. Searching joint support also excludes
postseason ties and unsupported scores. Exact probability breaks equal-loss
ties, followed by franchise-code ordering for consistent neutral reversals.
It need not equal the most likely exact score or imply the same favorite.
A tied central projection indicates a close matchup, not a likely tied result.

Support runs from zero through `max(100, highest training score + 40)`, excluding
one unless observed in training. A one-point final is an exceptionally rare
conversion-safety outcome, not a mathematical impossibility. Input scores above
200 are unsupported to bound memory; this is not a football rule. Nonfinite,
negative, fractional and incomplete scores are rejected, identical fixtures
are deduplicated, and conflicting completed results fail explicitly.

## One coherent probability distribution

- Home win: sum `p(h,a)` where `h > a`.
- Away win: sum `p(h,a)` where `h < a`.
- Tie: sum `p(h,a)` where `h == a`.
- Margin interval: the 10th and 90th percentiles of `h - a`.

The three outcome probabilities sum to one. Postseason ties are removed before
tilting, preserving the two mean constraints. The favorite follows total win
probability, which can differ from the winner in the single most likely
scoreline. Modes, medians and means solve different prediction objectives.

## Evaluation

Begin with the first 60% of distinct dates, then evaluate four consecutive
blocks from the remaining dates. Each model is fit only on dates strictly
before its test block. Earlier test blocks may enter later training windows;
no game is evaluated against a model trained on its own date or a later date.
Inner recency and pair-dependence selection repeat independently inside each training fold.

Report per-team MAE/RMSE, central-score and mode-score MAE, oriented exact-score accuracy, rounded-
mean accuracy, scoreline log loss, winner accuracy, Brier scores, and interval
coverage/width. Baselines use training-only league average points, a smoothed
historical home-win rate, and the untilted score distribution. Log loss uses a
`1e-15` floor for zero/out-of-support probabilities. Binary Brier and winner
accuracy exclude actual ties and use home probability conditional on a decisive
result. The separate three-outcome Brier includes ties.

Five fixed reliability bins expose average predicted versus observed home-win
rates and sample counts. They diagnose calibration; they are not a fitted
calibrator or proof of calibration. Fold boundaries and distribution-selection
records are returned for auditing.

The production model refits every eligible completed game before the service
cutoff after evaluation. Simulated histories never enter production training.

## API

- `GET /api/forecasts`: next 16 eligible fixtures, team codes and model metadata.
- `GET /api/forecast?home_team=BUF&away_team=MIA&neutral=false`: hypothetical
  regular-season matchup using the same fitted model.

`home_score` and `away_score` remain decimal expected points. `score_prediction`,
`typical_score_estimate`, and `top_scorelines` contain integer scores with probabilities. `margin` is
always home minus away; `total` is the sum of expected points. `favorite` is
based on win probability. `allow_ties` is false for scheduled postseason games.
`margin_stddev` now describes the joint distribution's margin uncertainty.

**v6 displayed-score change:** `score_prediction.method` is
`highest_probability_exact_score`, and it is exactly `top_scorelines[0]`. This is
the displayed predicted final. Its probability remains small; it is not a
confidence score. `typical_score_estimate.method` is
`minimum_expected_absolute_error` and is retained for evaluation and API users
who need a representative point estimate. `predicted_score_mae` and
`exact_score_accuracy` evaluate that typical estimate; `modal_score_mae` and
`modal_exact_score_accuracy` evaluate the highest-probability exact final.
Deploy frontend and backend together for the v6 response semantics.

**v5 score-distribution change:** `assumptions.pair_dependence` reports the
fitted empirical-pair share, and `assumptions.distribution_selection` reports
its training-only selection record. `top_scorelines` now derives from smooth
marginals with that capped blend; it is not a certain or representative final score.

**v3 probability change:** `home_win_probability + away_win_probability` is
`1 - tie_probability`, not always one. Clients needing a decisive-game
probability can divide either win probability by their sum. For older responses
without `tie_probability`, the frontend uses zero as a compatibility fallback.

## Limits

This is a custom experimental combination of established techniques. No
quarterback/injury, weather, rest, roster, betting-market or drive features are
used. It does not simulate overtime. Broad NFL score patterns are pooled across
seasons. Small exact-hit counts are unstable, and finite support omits very rare
outcomes. The historical comparisons are development evidence, not an untouched
future-season guarantee. See [research and results](application-research.md).
