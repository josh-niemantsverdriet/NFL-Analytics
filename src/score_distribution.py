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

    @classmethod
    def fit(cls, scores, weights):
        """Fit using only completed training games, with one weight per game."""
        scores = np.asarray(scores, dtype=int)
        weights = np.asarray(weights, dtype=float)
        if scores.max() > MAXIMUM_OBSERVED_SCORE or scores.min() < 0:
            raise ValueError("Training scores exceed the supported modeling range.")
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
        base = observed + JOINT_PRIOR_GAMES * np.outer(marginal, marginal)
        base /= base.sum()
        return cls(base=base)

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
        values = np.column_stack((rows, columns)) / 10.0
        log_base = np.log(base[rows, columns])
        scaled_target = target / 10.0

        def objective(theta):
            logits = log_base + values @ theta
            normalizer = logsumexp(logits)
            mass = np.exp(logits - normalizer)
            return (
                float(normalizer - theta @ scaled_target),
                mass @ values - scaled_target,
            )

        solution = minimize(
            objective, np.zeros(2), jac=True, method="BFGS",
            options={"gtol": 1e-9, "maxiter": 200},
        )
        logits = log_base + values @ solution.x
        mass = np.exp(logits - logsumexp(logits))
        if np.max(np.abs(mass @ values * 10.0 - target)) > 1e-5:
            raise ValueError("The score distribution could not match expected points.")
        result = np.zeros_like(self.base)
        result[rows, columns] = mass
        if home_mean == away_mean:
            result = (result + result.T) / 2.0
        return result

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
