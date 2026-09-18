# Predicting an NFL final score

The forecast chooses the most probable pair of integer scores from a joint
distribution. Expected average points remain separate: predicting an exact
result and minimizing average point error are different objectives. A mode
need not be close to the mean, and the single most likely result can favor a
different team from the favorite across all outcomes.

## Algorithm

1. **Estimate expected points.** Fit an L2-regularized linear model to both
   teams' scores in completed games. Features represent scoring team, opposing
   defense, and the home team's venue effect. Neutral games have no venue
   effect. Weights decay with a 365-day half-life; ridge alpha is fixed at 20.
2. **Learn final-score frequencies.** Form a recency-weighted histogram of
   score pairs, splitting each game's weight equally between both orientations.
   This pools league scoring patterns while leaving home advantage to the
   regression. It retains dependence between scores, common football totals,
   and the relative scarcity of tied finals.
3. **Regularize the histogram.** Add a prior equivalent to 32 games with
   independent scores from the league's pooled marginal distribution. Smooth
   those marginals with two pseudo-observations from a discrete Gaussian,
   centered on training scores with their weighted standard deviation
   (minimum seven points). This gives unseen combinations positive probability
   without allowing sparse historical pairs to determine the entire model.
4. **Adjust to this matchup.** Let `q(h,a)` be the smoothed joint histogram.
   Solve for two parameters so that
   `p(h,a) = q(h,a) exp(theta_home*h + theta_away*a) / Z`
   has the regression's expected home and away points. This is exponential
   tilting: the distribution closest to `q` in relative entropy subject to the
   two mean constraints. Use log-space normalization and an analytic gradient;
   verify the resulting means within 0.00001 points. For postseason games,
   remove tied outcomes before solving. Zero-point expectations are handled
   explicitly as boundary distributions.
5. **Choose the final score.** Return the joint mode, its probability, and the
   next two most probable pairs. Break equal probabilities deterministically
   using franchise codes, so reversing a neutral matchup reverses its scores.

The support is every integer from zero through the larger of 100 and the
highest training score plus 40, except one unless observed in training. A
one-point final requires an exceptionally rare conversion safety; it is a
model limitation rather than a claim that such scores are impossible. Scores
beyond finite support are also excluded. Zero-probability alternatives are
never displayed.
Scores greater than 200 are rejected as unsupported input to bound memory
allocation; this is an implementation limit, not a football scoring rule.

These components use established statistical methods. Their particular
combination here is a custom, experimental NFL model. No scoring-event rates
are inferred from final points, and no season-end EPA aggregates enter a
historical prediction.

## Historical evaluation

Train on the first 80% of distinct game dates, then keep that model fixed for
the remaining dates. The regression, histogram, smoothing prior, tail support,
and uncertainty estimates all use training results only. Test scores cannot
affect predictions. Parameters are fixed assumptions, not optimized against
this holdout. The production model subsequently refits on all eligible games.

The local nflverse snapshot evaluated with an exclusive 2026-09-17 cutoff has
865 completed regular-season and postseason games. Its chronological split
uses 705 training games through 2025-11-03 and 160 test games from 2025-11-06
through 2026-09-13.

| Metric | Result |
| --- | ---: |
| Expected points MAE, per team | 7.92 points |
| Expected points RMSE, per team | 9.83 points |
| Integer final-score MAE, per team | 8.03 points |
| Both final scores correct | 2 / 160 (1.25%) |
| Both correct by rounding expected points | 0 / 160 |

The small exact-hit count does not establish superiority. The mode's point
error is slightly higher than the means' point error, as different objectives
would suggest. The API also reports natural-log loss for the full joint
distribution and the same league distribution without matchup adjustments.
Lower log loss is better; probabilities are floored at `1e-15` for evaluation,
including outcomes outside support. Both models exclude ties in postseason
evaluation. These probabilities have not been calibrated on a separate sample.

Reproduce the full metrics from a downloaded nflverse schedule parquet:

```powershell
python -m src.forecast_backtest --schedules data/forecast/schedules.parquet --before 2026-09-17
```

The command outputs JSON containing the snapshot SHA-256, model assumptions,
and evaluation. Snapshot used above:
`fc1fef7fa8c5a754599a5c355ec72bfcca1a8ba6f931150b9aaf17237788f472`.
The ignored data file is not distributed with the repository; another snapshot
can produce different results.

## Limits and references

Injuries, starting quarterbacks, weather, rest, roster changes, and betting
markets are not features. Win chances and the margin range retain the existing
normal-margin approximation, so they are separate estimates from the discrete
score distribution. The model does not simulate drives or overtime. Further
changes should be assessed on additional untouched seasons before claiming an
accuracy improvement.

- [scikit-learn: Ridge regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)
- [R boot package: exponential tilting](https://web.mit.edu/~r/current/lib/R/library/boot/html/exp.tilt.html)
- [Theory-coherent forecasting: distributions with moment restrictions](https://www.sciencedirect.com/science/article/pii/S0304407614000736)
- [Gneiting: Making and Evaluating Point Forecasts](https://arxiv.org/abs/0912.0902)
- [scikit-learn: chronological cross-validation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
