# Score-distribution overhaul (v5)

Investigated September 18, 2026. Distribution version: `ridge-smooth-score-v5`;
the v6 API displays the highest-probability exact score as its prediction.
This is a local implementation and validation report, not a deployed forecast
or a guarantee of a game outcome.

## Problem and evidence

The prior score model began with a weighted histogram of complete `(home, away)`
final-score pairs. Exponential tilting correctly matched the matchup's expected
points, but it did not prevent a frequent historical pair from remaining the
tallest individual probability. That made 34-10 a repeated exact mode for
moderately favored teams even though its absolute probability was well below 1%.

On the same 872 completed 2023-2026 games and 332 expanding-window test games
used for the earlier v4 investigation, the direct-pair distribution had exact
score log loss **7.1039** and exact-mode MAE **8.6401** per team. A fully smooth
independent-marginal distribution improved both to **7.0911** and **8.3057**.
A 10% empirical-pair blend gave the best tested exact-score log loss, **7.0824**;
larger pair blends made both the log loss and repeated-mode behavior worse.

| Direct empirical-pair share | Exact-score log loss | Exact-mode MAE |
| ---: | ---: | ---: |
| 0% | 7.0911 | 8.3057 |
| 10% | 7.0824 | 8.4367 |
| 25% | 7.1010 | 8.6401 |

These are chronological holdout comparisons. They support the distribution
change but do not make exact NFL final scores reliably predictable.

## Replacement model

The v5 base distribution is the outer product of two recency-weighted, smoothed
league score marginals. It therefore gives an individual final score probability
only when both component scores are plausible. It adds a capped 0%, 5%, or 10%
share of the symmetric empirical score-pair distribution, selected by inner
chronological exact-score log loss. The pair cap stops league-wide historical
spikes from determining a matchup forecast.

The distribution is then adjusted with minimum-relative-entropy exponential
tilting so its expected home and away points equal the regularized, recency-
weighted team-rating estimates. This follows the general score-forecasting
approach of time-varying bivariate count models, while retaining the app's
discrete NFL-score support and transparent API semantics. [Koopman and Lit,
dynamic bivariate Poisson forecasting](https://research.vu.nl/en/publications/a-dynamic-bivariate-poisson-model-for-analysing-and-forecasting-m/)
describes the value of dynamically modeling score dependence.

## Houston-Cincinnati check

With the cached schedule results through September 17, the refit chooses 10%
pair dependence and 180-day recency. Houston-Cincinnati's leading exact pairs
are now **27-20 (0.543%)**, **34-10 (0.506%)**, and **31-10 (0.457%)**. Thus
34-10 is no longer presented as the highest-probability exact outcome. The
separate central projection remains Houston 28-22 because it minimizes expected
absolute point error across the whole distribution.

The v6 interface presents 27-20 as the **Predicted final score**. It retains the
28-22 typical estimate only in the API for evaluation and advanced consumers.
