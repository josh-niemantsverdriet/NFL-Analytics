"""Discrete final scores from a regularized empirical joint distribution.

Exponential tilting (minimum relative entropy) adjusts historical scoreline
frequencies to match a matchup's expected points. This preserves football's
uneven score frequencies without inferring touchdowns from final scores.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


JOINT_PRIOR_GAMES = 32.0
MARGINAL_PRIOR_SCORES = 2.0
MINIMUM_SCORE_SUPPORT = 100
MAXIMUM_OBSERVED_SCORE = 200  # Resource bound for malformed data, not a football rule.
MINIMUM_PRIOR_STDDEV = 7.0


@dataclass
class ScoreDistribution:
    base: np.ndarray
    prior_games: float = JOINT_PRIOR_GAMES

    @classmethod
    def fit(cls, scores, weights, prior_games=JOINT_PRIOR_GAMES):
        """Fit using only completed training games, with one weight per game."""
        scores = np.asarray(scores, dtype=float)
        weights = np.asarray(weights, dtype=float)
        if not np.isfinite(prior_games) or prior_games <= 0:
            raise ValueError("The joint prior must have positive finite weight.")
        if scores.ndim != 2 or scores.shape[1] != 2 or not len(scores):
            raise ValueError("Training scores must be a nonempty array of score pairs.")
        if (weights.shape != (len(scores),) or not np.all(np.isfinite(weights))
                or np.any(weights < 0) or not np.any(weights > 0)):
            raise ValueError("Game weights must be finite, nonnegative, and have positive mass.")
        if (not np.all(np.isfinite(scores)) or np.any(scores != np.floor(scores))
                or scores.max() > MAXIMUM_OBSERVED_SCORE or scores.min() < 0):
            raise ValueError("Training scores exceed the supported modeling range.")
        scores, weights = scores[weights > 0].astype(int), weights[weights > 0]
        # Leave ample tail support beyond even the highest training score.
        maximum = max(MINIMUM_SCORE_SUPPORT, int(scores.max()) + 40)
        grid = np.arange(maximum + 1, dtype=float)
        pooled_weights = np.repeat(weights, 2)
        mean = np.average(scores.ravel(), weights=pooled_weights)
        variance = np.average((scores.ravel() - mean) ** 2, weights=pooled_weights)
        sigma = max(MINIMUM_PRIOR_STDDEV, float(np.sqrt(variance)))

        # A small Dirichlet prior avoids zero mass at previously unseen scores.
        # One-point finals require an exceptionally rare conversion safety and
        # are outside this model's support unless present in training history.
        smooth = np.exp(-0.5 * ((grid - mean) / sigma) ** 2)
        if not np.any(scores == 1):
            smooth[1] = 0.0
        smooth /= smooth.sum()
        marginal = np.bincount(
            scores.ravel(), weights=pooled_weights, minlength=len(grid),
        ) + MARGINAL_PRIOR_SCORES * smooth
        marginal /= marginal.sum()

        observed = np.zeros((len(grid), len(grid)), dtype=float)
        np.add.at(observed, (scores[:, 0], scores[:, 1]), weights / 2.0)
        np.add.at(observed, (scores[:, 1], scores[:, 0]), weights / 2.0)
        # Pool both orientations: venue belongs in the expected-score model,
        # rather than being counted again in this league-wide score prior.
        base = observed + prior_games * np.outer(marginal, marginal)
        base /= base.sum()
        return cls(base=base, prior_games=float(prior_games))

    def baseline(self, allow_ties=True):
        if allow_ties:
            return self.base
        base = self.base.copy()
        np.fill_diagonal(base, 0.0)
        return base / base.sum()

    def probabilities(self, home_mean, away_mean, allow_ties=True):
        """Return P(home score, away score), matching the supplied means.

        Solve log(sum(q[h,a] exp(theta_h*h + theta_a*a))) - theta dot means.
        Its gradient is the difference between fitted and requested means.
        """
        # Solve in one orientation so reversing teams transposes exactly.
        if home_mean < away_mean:
            return self.probabilities(away_mean, home_mean, allow_ties=allow_ties).T
        target = np.array([home_mean, away_mean], dtype=float)
        maximum = self.base.shape[0] - 1
        if not np.all(np.isfinite(target)) or np.any(target < 0) or np.any(target >= maximum):
            raise ValueError("Expected points are outside the score distribution support.")

        base = self.baseline(allow_ties=allow_ties)
        rows, columns = np.nonzero(base)
        if target.sum() < np.min(rows + columns):
            raise ValueError("Expected points cannot describe a game without a tie.")
        # Zero expectations are boundary solutions, not finite exponential tilts.
        keep = ((rows == 0) | (target[0] > 0)) & ((columns == 0) | (target[1] > 0))
        rows, columns = rows[keep], columns[keep]
        home_values, away_values = rows / 10.0, columns / 10.0
        log_base = np.log(base[rows, columns])
        scaled_target = target / 10.0

        def moments(mass):
            return np.array([np.sum(mass * home_values), np.sum(mass * away_values)])

        def objective(theta):
            logits = log_base + home_values * theta[0] + away_values * theta[1]
            normalizer = logsumexp(logits)
            mass = np.exp(logits - normalizer)
            return (
                float(normalizer - theta @ scaled_target),
                moments(mass) - scaled_target,
            )

        solution = minimize(
            objective, np.zeros(2), jac=True, method="BFGS",
            options={"gtol": 1e-9, "maxiter": 200},
        )
        logits = log_base + home_values * solution.x[0] + away_values * solution.x[1]
        mass = np.exp(logits - logsumexp(logits))
        if not np.all(np.isfinite(mass)) or np.max(np.abs(moments(mass) * 10.0 - target)) > 1e-5:
            raise ValueError("The score distribution could not match expected points.")
        result = np.zeros_like(self.base)
        result[rows, columns] = mass
        if home_mean == away_mean:
            result = (result + result.T) / 2.0
        return result

    @staticmethod
    def summarize(probabilities, coverage=0.8):
        """Derive win/tie chances and a central margin interval from one PMF."""
        size = len(probabilities)
        points = np.arange(size)
        margins = points[:, None] - points[None, :]
        margin_mass = np.bincount(
            (margins + size - 1).ravel(), weights=probabilities.ravel(),
            minlength=2 * size - 1,
        )
        support = np.arange(1 - size, size)
        cumulative = np.cumsum(margin_mass)
        tail = (1.0 - coverage) / 2.0
        low = int(support[min(np.searchsorted(cumulative, tail), len(support) - 1)])
        high = int(support[min(np.searchsorted(cumulative, 1.0 - tail), len(support) - 1)])
        margin_mean = float(margin_mass @ support)
        return {
            "home_win_probability": float(np.tril(probabilities, -1).sum()),
            "away_win_probability": float(np.triu(probabilities, 1).sum()),
            "tie_probability": float(np.trace(probabilities)),
            "margin_stddev": float(np.sqrt(margin_mass @ (support - margin_mean) ** 2)),
            "margin_interval": {"coverage": coverage, "low": low, "high": high},
        }

    @staticmethod
    def point_scoreline(probabilities, home_team, away_team):
        """Bayes point forecast under per-team absolute score error.

        Marginal medians minimize this loss. Search the joint support so the
        answer also respects excluded scores and postseason no-tie rules.
        Exact-score probability breaks equal-risk ties; franchise ordering
        makes the last tie-break invariant to reversing a neutral matchup.
        """
        reverse = home_team > away_team
        mass = probabilities.T if reverse else probabilities
        points = np.arange(len(mass))
        distances = np.abs(points[:, None] - points[None, :])
        home_risk = np.sum(distances * mass.sum(axis=1)[None, :], axis=1)
        away_risk = np.sum(distances * mass.sum(axis=0)[None, :], axis=1)
        risk = home_risk[:, None] + away_risk[None, :]
        supported = mass > 0
        minimum = np.min(risk[supported])
        candidates = np.flatnonzero((supported & (risk <= minimum + 1e-10)).ravel())
        index = candidates[np.argmax(mass.ravel()[candidates])]
        first, second = np.unravel_index(index, mass.shape)
        home, away = (second, first) if reverse else (first, second)
        return {
            "home_score": int(home), "away_score": int(away),
            "probability": float(probabilities[home, away]),
            "method": "minimum_expected_absolute_error",
        }

    @staticmethod
    def top_scorelines(probabilities, home_team, away_team, count=3):
        """Rank joint modes, breaking equal probabilities by franchise code.

        A single most likely scoreline can differ from the overall favorite:
        winning probability combines many different possible final scores.
        """
        reverse = home_team > away_team
        ordered = probabilities.T if reverse else probabilities
        possible = np.flatnonzero(ordered.ravel() > 0.0)
        indices = possible[np.argsort(-ordered.ravel()[possible], kind="stable")[:count]]
        result = []
        for index in indices:
            first, second = np.unravel_index(index, ordered.shape)
            home, away = (second, first) if reverse else (first, second)
            result.append({
                "home_score": int(home),
                "away_score": int(away),
                "probability": float(probabilities[home, away]),
            })
        return result
