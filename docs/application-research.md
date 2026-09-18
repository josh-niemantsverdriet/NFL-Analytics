# Application research and improvements

This report records the v3 application review. The subsequent
[v4 score and recency investigation](forecast-recency-investigation.md) corrects
the repetitive modal-score headline and updates recency weighting.

This review examined forecasting, evaluation, play-by-play aggregation, ranking
consistency, browser request lifecycles, repeated content, and deployment checks.
Changes were evaluated locally; nothing was deployed or written to the live SQL
database. The comparison baseline is commit `1a47bed`.

## Forecasting decisions

**Use chronological evaluation of the complete fitting procedure.** A single
frozen split provided little information about stability. The new evaluation
uses four expanding training windows and holds every game date together. This
follows rolling-origin evaluation, where each test observation is predicted
using earlier observations. Blocks bound online startup cost; they do not claim
to reproduce a weekly refit exactly. [Hyndman and Athanasopoulos,
Forecasting: Principles and Practice](https://otexts.com/fpp3/tscv.html)

**Select smoothing inside training, not against the reported test scores.**
Sparse score pairs can receive excessive probability while unseen pairs receive
too little. Candidate prior strengths of 32, 128 and 512 are compared using
an inner chronological sample, and that procedure repeats inside each outer
fold. This separates model selection from evaluation. Ridge strength and
recency decay remain fixed to keep the search small. [scikit-learn,
nested versus non-nested validation](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html)

**Pool home-field information across teams.** Previously all team-specific home
effects shrank toward zero separately. A shared home parameter with regularized
team deviations lets limited-history teams borrow the league effect. The
regularized offense/defense model remains interpretable and inexpensive to fit.
[scikit-learn, ridge regression](https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification)

**Use one distribution for scores, outcomes and uncertainty.** The previous
scoreline distribution coexisted with a separate normal-margin approximation.
The new forecast sums the joint score probabilities for win/loss/tie chances
and takes discrete margin quantiles from the same distribution. Exponential
tilting still enforces the two expected-score constraints. [R boot package,
exponential tilting](https://web.mit.edu/~r/current/lib/R/library/boot/html/exp.tilt.html)

**Assess probabilities with proper scores, and show calibration diagnostics.**
Exact-hit rates alone are highly unstable. Log loss evaluates the score
distribution, while Brier scores evaluate outcome probabilities. Reliability
bins show predicted and observed home-win rates with sample counts. No
post-hoc calibration was fit to the outer test data. Proper scores also reflect
discrimination and uncertainty, so a lower Brier score alone is not proof of
calibration. [Gneiting and Raftery, proper scoring rules](https://doi.org/10.1198/016214506000001437),
[scikit-learn, probability calibration](https://scikit-learn.org/stable/modules/calibration.html)

## Measured historical tradeoffs

The same 865-game schedule snapshot and the same four test blocks were used
for both algorithms. There are 334 test games, including one tie, from
2024-12-29 through 2026-09-13. Every parameter-selection step for the new model
uses only the relevant outer fold's training games. Full fold boundaries,
selection records, snapshot hash and metrics are in
[validation-results.json](validation-results.json).

| Metric | Previous model on these folds | Revised model |
| --- | ---: | ---: |
| Expected-score MAE, per team | 7.737 | 7.708 |
| Integer-score MAE, per team | 8.377 | 8.466 |
| Exact-score log loss | 7.694 | 7.111 |
| Binary Brier score | 0.2337 | 0.2331 |
| Coverage of nominal 80% margin range | 74.9% | 80.8% |
| Winner accuracy, 333 decisive games | 61.9% | 60.7% |
| Both exact final scores correct | 1 / 334 | 1 / 334 |

The principal gain is probability quality and observed interval coverage.
Expected-score error improved slightly; winner accuracy and modal score error
worsened. This is an explicit tradeoff, not across-the-board superiority. The
new model's point MAE beats the training-only league-average baseline of 8.052;
its binary Brier beats the historical home-win baseline of 0.2477. A new,
untouched season is still needed for stronger evidence. These are development
comparisons, and the small exact-hit count cannot support an exact-score
accuracy claim. Mean and mode forecasts target different objectives.
[Gneiting, Making and Evaluating Point Forecasts](https://arxiv.org/abs/0912.0902)

## Analytics and application findings

- **Consistent offensive-play classification.** Prefer nflfastR's `pass` and
  `rush` fields; fall back to dropback, sack and scramble indicators for older
  snapshots. Scrambles belong to dropbacks. Exclude kneels, spikes, nonfinite
  EPA, wrong-season and postseason rows from season efficiency rankings.
  Derive success from positive EPA, preserve teams with only one side observed,
  and share aggregation logic between offense and defense. This matches the
  distinction between dropbacks and designed runs in the nflfastR guide.
  [nflfastR beginner's guide](https://nflfastr.com/articles/beginners_guide)
- **Treat the matchup average as descriptive.** The offense/defense mean is
  not a trained prediction model. Its duplicated calculations now share one
  helper, and the interface labels the result as blended efficiency. The
  separate Game Forecasts page supplies actual probabilistic forecasts.
- **Make rankings agree.** SQL team pages already use competition ranks;
  the browser previously assigned different positions to tied metrics.
  Browser rankings now match SQL `RANK()` semantics, including nulls last.
- **Remove repeated content and requests.** Removed the redundant Top Offenses
  block beneath the sortable league rankings, the obsolete NEW badge, and
  starter README/title content. Dashboard ranking and matchup components share
  one team-data request and one type definition.
- **Prevent stale results.** Shared request handling normalizes API URLs and
  errors. Team navigation and matchup requests abort on cleanup or selection
  changes; old results cannot overwrite a newer selection. This addresses the
  response-order race described in React's data-fetching guidance.
  [React useEffect](https://react.dev/reference/react/useEffect)
- **Improve navigation and failure handling.** Added a skip link, active route
  state, labeled team selectors, pressed-state ranking controls, and a missing-
  page route. Malformed schedule rows no longer fail the entire forecast list.
- **Keep checks ahead of deployment.** The Static Web Apps workflow now depends
  on reusable Python and frontend checks. Function publishing excludes frontend,
  node_modules, tests and docs. Reusable jobs avoid maintaining a separate,
  inconsistent set of deployment checks. [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)

Existing SQL analytics must be recomputed through the authenticated analysis
operation before the revised metric definitions appear in production. No
schema migration was introduced.

## Simulated and browser verification

The reusable generator produces 32-team seasons with 17 games per team, eight
or nine home games per team, some neutral venues, and a stylized postseason
final. Points arise from touchdowns, extra points, field goals and safeties.
Shared pace induces score dependence; team strengths evolve across seasons.
Six environments cover balanced, unequal, drifting, volatile, low-scoring and
high-scoring leagues. It is intentionally a test generator, not an exact NFL
scheduling or overtime simulator.

- Extended run: **48 seeds × 8 seasons = 104,832 games**, with **4,608 forecast
  checks** and zero failures. Each environment receives eight seeds.
- Default Python suite: **6,552 simulated games**, 192 direct matchup checks,
  reversal symmetry, postseason tie exclusion, nested chronological isolation,
  normalization, mean matching, boundary cases and resource limits.
- Analytics: **64,000 simulated plays** verify count conservation and identical
  offense/defense EPA totals. Explicit cases cover sacks, scrambles, kneels,
  spikes, invalid EPA, empty data and missing observations.
- Data corruption: **2,000 duplicate/malformed rows** cannot change clean
  history; zero-weight scores cannot change distribution support.
- Browser ranking tests: **3,200 simulated team rows** agree with independent
  pairwise ranking definitions and preserve ties and input immutability.
- Browser smoke tests: cached real schedules for forecast endpoints and isolated
  fixtures for SQL-backed pages. Checked 1280px desktop, 390px and 320px mobile;
  score rendering, probability details, neutral games, error/retry, stale result
  clearing, shared requests, and horizontal overflow. No production SQL data
  was required or changed.
- Final checks: 46 Python tests and two frontend tests passed, as did lint and
  the production build. The Function App imported and registered all nine
  functions after installing the declared SQL driver in an isolated local
  directory. Live SQL integration and remote deployment were not exercised.

Simulated outcomes never train the live model. Large synthetic volume tests
software behavior and known invariants; it cannot establish real-world
predictive accuracy. Reproduction commands are in the [README](../README.md).

## Deferred research directions

Quarterback/injury, weather, rest, drive and opponent-adjusted EPA features
could provide richer inputs, but this repository's aggregate snapshots cannot
reconstruct when those values became available before past kickoffs. Adding
them without point-in-time histories would risk leakage. More flexible models
and probability calibration should be compared on additional untouched seasons
once those histories exist. They were not added merely to increase complexity.
