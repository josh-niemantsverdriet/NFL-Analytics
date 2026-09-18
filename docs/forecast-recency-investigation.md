# Repeated 34–10 forecasts and recency weighting

Investigated September 18, 2026. Baseline: `ridge-joint-score-v3`, commit
`a8bd36b`. Revised model: `ridge-joint-score-v4`. Changes are local; this report
does not imply a deployment or a guaranteed game outcome.

## Confirmed cause

The production API returned 34–10, in either orientation, for **9 of 16 games**.
Houston–Cincinnati displayed Houston 34–10, but its expected points were
**26.20–21.59**, with **61.31%** Houston win probability. The probability of
34–10 itself was only **0.638%**; 27–20 had 0.610% and 23–20 had 0.590%.

The headline used the *joint mode*: the single most probable exact pair. A
historical score-frequency spike at 34–10 was amplified by exponential tilting
for moderately favored teams. Mean matching does not constrain where a
multimodal distribution's tallest individual spike lies. This was a mismatch
between the headline's intended use as a representative score and its exact-hit
objective. No team-specific override or random diversification was introduced.

## Point forecast change

The new projection minimizes expected absolute error across the two team
scores. Usually this gives their marginal medians. We search supported joint
score pairs, preserving postseason no-tie rules and excluded one-point finals.
Equal-loss choices prefer higher exact probability, then a deterministic
franchise ordering so reversing a neutral matchup reverses the result.

This choice follows the relationship between MAE and medians, and the need to
match a point forecast to its decision loss. [Forecasting: Principles and
Practice](https://otexts.com/fpp3/accuracy.html),
[Gneiting, Making and Evaluating Point Forecasts](https://arxiv.org/abs/0912.0902).

The full score probability distribution is retained. Its most likely exact
outcomes remain separately visible with their probabilities. The UI labels the
headline **Projected score**, explains its purpose, and distinguishes a tied
central estimate from a prediction that a tie is likely. The API method marker
is `score_prediction.method = minimum_expected_absolute_error`.

## Recent results receive more weight

The former model used a fixed 365-day half-life. The revised model selects
120, 180 or 270 days using expected-point MSE on inner chronological validation
games, then selects score-histogram smoothing by log loss. The process repeats
inside each outer fold; no outer outcomes select that fold's settings. Sparse
histories default to 180 days. Whole game dates stay on one side of each split.
[Rolling-origin evaluation](https://otexts.com/fpp3/tscv.html).

Regression weights are normalized to mean one. Simply shortening decay without
this step reduced the total weight of observations and inadvertently increased
the effect of the unchanged Ridge penalty. Normalization separates relative
recency from that weight-scale effect. This follows from the weighted loss and
penalty used by [Ridge regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).

The full current fit selected **180 days**. With results through September 17,
the league's training-weight shares are:

| Season | Share |
| --- | ---: |
| 2026 | 12.9% |
| 2025 | 66.7% |
| 2024 | 16.4% |
| 2023 | 4.0% |

Thus the current and previous two seasons supply **96.0%** of the weight. These
are league totals, not fixed per-season quotas or each team's exact proportions.
The UI exposes these shares and each team's current-season sample size.

## Houston–Cincinnati

The revised central score is **Houston 28–22 Cincinnati**, with expected points
28.24–21.95 and Houston win probability **65.24%**. The 80% Houston-margin range
is **−12 to +25**, so the estimate still has substantial uncertainty.

Cincinnati opened with a 33–27 win and Houston with a 31–36 loss. Each has only
one current-season regular-season result. [Bengals official schedule](https://www.bengals.com/schedule/2026/),
[Texans official schedule](https://www.houstontexans.com/schedule/2026/).

In the nflverse snapshot, Houston's 2025 results including playoffs average
23.7 points scored and 17.3 allowed, compared with Cincinnati's 24.4 scored and
28.9 allowed. Giving recent seasons more influence therefore still favors
Houston. One 2026 game per team is insufficient reason to force a reversal.
Quarterback availability and other roster changes are not modeled. The 34–10
exact mode can still appear among alternative outcomes; it is no longer the
representative headline.

## Validation and tradeoffs

The refreshed snapshot contains **872** completed 2023–2026 games. Both versions
were evaluated on the same **332** outer test games from December 30, 2024
through September 17, 2026, with four expanding training windows. Different
snapshot dates change fold boundaries, so these numbers should not be mixed
with the earlier 334-game v3 report. Full results, selected settings, snapshot
hash and simulated checks are in [forecast-v4-validation.json](forecast-v4-validation.json).

| Metric | v3 | v4 |
| --- | ---: | ---: |
| Displayed score MAE per team | 8.392 | 7.684 |
| Expected-point MAE per team | 7.653 | 7.646 |
| Margin MAE | 10.655 | 10.535 |
| Winner accuracy, 331 decisive games | 60.7% | 63.1% |
| Binary Brier score | 0.2344 | 0.2298 |
| Score-distribution log loss | 7.1018 | 7.1039 |
| Exact headline score hits | 2 / 332 | 1 / 332 |
| Unique projected scorelines | 9 | 126 |
| Largest share of one projected scoreline | 37.3% | 4.5% |

Displayed point error improved **8.4%**. Exact-hit rate decreased and distribution
log loss was essentially unchanged, slightly worse. This is a central-score
improvement rather than evidence of reliable exact-score prediction. The
historical comparison remains development evidence, not a future-season test.

For the same upcoming 16 fixtures, 34–10 headline projections dropped from
**9 to 0**. There are now **15 distinct** oriented scorelines; the largest
repetition is two games. No rule limits repeats or bans 34–10: the change comes
from the point objective and fitted ratings.

Regression checks cover a deliberately misleading 34–10 spike, an independent
brute-force absolute-loss oracle, reversal symmetry, postseason support,
recency response to changing team strength, Ridge weight normalization, and
chronological isolation. The full suite contains 51 Python tests and four
frontend tests. An additional 48-seed stress run checked **104,832 simulated
games and 4,608 forecasts** with no failures. Simulated volume verifies software
behavior, not NFL accuracy.

Deploy both backend and frontend so the v4 projection and its labels agree.
This change uses schedule history and requires no SQL migration or analytics
reingestion. Legacy v3 responses retain their original labels in the new UI.
