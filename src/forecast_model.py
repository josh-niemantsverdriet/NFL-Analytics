"""Experimental pregame score forecasts from completed schedule results.

The model deliberately does not consume season aggregate EPA: those aggregates
cannot reconstruct what was known before a historical game. Parameters below
are fixed assumptions or selected using inner training dates only, never the
outer evaluation outcomes.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
import re

import numpy as np
from sklearn.linear_model import Ridge

from src.forecast_evaluation import evaluate, INITIAL_TRAINING_FRACTION, EVALUATION_FOLDS

from src.score_distribution import (
    JOINT_PRIOR_GAMES, MARGINAL_PRIOR_SCORES, MAXIMUM_OBSERVED_SCORE, ScoreDistribution,
)

RIDGE_ALPHA = 20.0
RECENCY_HALF_LIFE_DAYS = 365.0
MINIMUM_GAMES = 12
INTERVAL_COVERAGE = 0.8
POSTSEASON_GAME_TYPES = {"WC", "DIV", "CON", "SB"}
JOINT_PRIOR_CANDIDATES = (32.0, 128.0, 512.0)
MINIMUM_PRIOR_SELECTION_GAMES = 200
MAXIMUM_PRIOR_VALIDATION_GAMES = 48

TEAM_ALIASES = {
    "LAR": "LA",
    "STL": "LA",
    "OAK": "LV",
    "SD": "LAC",
    "JAC": "JAX",
    "WSH": "WAS",
}


class ForecastDataError(ValueError):
    """There is not enough valid, consistent history for a forecast."""


def normalize_team(team):
    if not isinstance(team, str):
        raise ValueError("Team codes must be strings.")
    code = team.strip().upper()
    if not re.fullmatch(r"[A-Z]{2,4}", code):
        raise ValueError("Team codes must contain two to four letters.")
    return TEAM_ALIASES.get(code, code)


def _game_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _score(value):
    if isinstance(value, bool):
        raise ValueError("A score cannot be a boolean.")
    score = float(value)
    if not isfinite(score) or score < 0 or not score.is_integer():
        raise ValueError("Completed scores must be finite nonnegative integers.")
    if score > MAXIMUM_OBSERVED_SCORE:
        raise ValueError("Completed score exceeds the supported modeling range.")
    return score


def _clean_games(games):
    cleaned = []
    seen_ids = {}
    seen_fixtures = {}
    discarded = 0
    duplicates = 0

    for source in games:
        try:
            home = normalize_team(source["home_team"])
            away = normalize_team(source["away_team"])
            if home == away:
                raise ValueError("A team cannot play itself.")
            gameday = _game_date(source["gameday"])
            season_value = source["season"]
            season = int(season_value)
            if isinstance(season_value, bool) or float(season_value) != season:
                raise ValueError("The season must be an integer.")
            location = str(source.get("location") or "Home").strip().lower()
            if location not in ("home", "neutral"):
                raise ValueError("Unknown game location.")
            game_type = source.get("game_type", "REG")
            if game_type not in POSTSEASON_GAME_TYPES | {"REG"}:
                raise ValueError("Only regular-season and postseason games are supported.")
            game = {
                "game_id": str(source.get("game_id") or "").strip(),
                "season": season,
                "gameday": gameday,
                "home_team": home,
                "away_team": away,
                "home_score": _score(source["home_score"]),
                "away_score": _score(source["away_score"]),
                "neutral": location == "neutral",
                "allow_ties": game_type not in POSTSEASON_GAME_TYPES,
            }
            if not game["allow_ties"] and game["home_score"] == game["away_score"]:
                raise ValueError("A completed postseason game cannot be tied.")
        except (KeyError, TypeError, ValueError, OverflowError):
            discarded += 1
            continue

        fixture = (season, gameday, home, away)
        signature = fixture + (
            game["home_score"], game["away_score"], game["neutral"], game["allow_ties"],
        )
        game_id = game["game_id"]
        if game_id and game_id in seen_ids:
            if seen_ids[game_id] != signature:
                raise ForecastDataError(
                    f"Conflicting completed results for game {game_id}."
                )
            duplicates += 1
            continue
        if fixture in seen_fixtures:
            if seen_fixtures[fixture] != signature:
                raise ForecastDataError(
                    "Conflicting completed results for the same fixture."
                )
            duplicates += 1
            if game_id:
                seen_ids[game_id] = signature
            continue
        seen_fixtures[fixture] = signature
        if game_id:
            seen_ids[game_id] = signature
        cleaned.append(game)

    cleaned.sort(key=lambda game: (
        game["gameday"], game["home_team"], game["away_team"],
    ))
    return cleaned, discarded, duplicates


@dataclass
class _FittedScores:
    regression: Ridge
    team_indices: dict
    game_counts: Counter
    trained_through: date
    score_distribution: ScoreDistribution | None = None
    prior_selection: dict | None = None

    @property
    def home_field_points(self):
        team_count = len(self.team_indices)
        return self.regression.coef_[2 * team_count:3 * team_count] + self.regression.coef_[-1]

    def features(self, home_team, away_team, neutral):
        team_count = len(self.team_indices)
        features = np.zeros((2, 3 * team_count + 1), dtype=float)
        home_index = self.team_indices[home_team]
        away_index = self.team_indices[away_team]
        features[0, home_index] = 1.0
        features[0, team_count + away_index] = 1.0
        features[1, away_index] = 1.0
        features[1, team_count + home_index] = 1.0
        if not neutral:
            venue_start = 2 * team_count
            features[0, venue_start + home_index] = 0.5
            features[1, venue_start + home_index] = -0.5
            # Shared home effect plus shrunk team deviations (partial pooling).
            features[0, -1] = 0.5
            features[1, -1] = -0.5
        return features

    def scores(self, home_team, away_team, neutral):
        values = self.regression.predict(
            self.features(home_team, away_team, neutral)
        )
        return max(0.0, float(values[0])), max(0.0, float(values[1]))


def _fit_base(games, prior_games=JOINT_PRIOR_GAMES):
    teams = sorted({
        game[side] for game in games for side in ("home_team", "away_team")
    })
    counts = Counter(
        game[side] for game in games for side in ("home_team", "away_team")
    )
    trained_through = max(game["gameday"] for game in games)
    fitted = _FittedScores(
        regression=Ridge(alpha=RIDGE_ALPHA, fit_intercept=True, solver="cholesky"),
        team_indices={team: index for index, team in enumerate(teams)},
        game_counts=counts,
        trained_through=trained_through,
    )
    features = np.vstack([
        fitted.features(game["home_team"], game["away_team"], game["neutral"])
        for game in games
    ])
    scores = np.array([
        game[side] for game in games for side in ("home_score", "away_score")
    ], dtype=float)
    game_weights = np.array([
        0.5 ** ((trained_through - game["gameday"]).days / RECENCY_HALF_LIFE_DAYS)
        for game in games
    ], dtype=float)
    fitted.regression.fit(features, scores, sample_weight=np.repeat(game_weights, 2))
    actual = scores.reshape(-1, 2)
    fitted.score_distribution = ScoreDistribution.fit(actual, game_weights, prior_games=prior_games)
    return fitted


def _fit(games):
    """Choose smoothing on inner chronological data, then refit all training data."""
    selection = {"games": 0, "selected_prior_games": JOINT_PRIOR_GAMES, "candidates": []}
    if len(games) >= MINIMUM_PRIOR_SELECTION_GAMES:
        dates = sorted({game["gameday"] for game in games})
        split = dates[min(len(dates) - 1, int(len(dates) * 0.8))]
        earlier = [g for g in games if g["gameday"] < split]
        validation = [g for g in games if g["gameday"] >= split]
        if len(earlier) >= 100 and len(validation) >= 20:
            if len(validation) > MAXIMUM_PRIOR_VALIDATION_GAMES:
                validation = [validation[i] for i in np.linspace(0, len(validation) - 1, MAXIMUM_PRIOR_VALIDATION_GAMES, dtype=int)]
            inner = _fit_base(earlier)
            validation = [g for g in validation if g["home_team"] in inner.team_indices and g["away_team"] in inner.team_indices]
            targets = [inner.scores(g["home_team"], g["away_team"], g["neutral"]) for g in validation]
            weights = np.array([0.5 ** ((inner.trained_through - g["gameday"]).days / RECENCY_HALF_LIFE_DAYS) for g in earlier])
            actual = np.array([[g["home_score"], g["away_score"]] for g in earlier])
            if len(validation) >= 20:
                for prior in JOINT_PRIOR_CANDIDATES:
                    distribution = ScoreDistribution.fit(actual, weights, prior_games=prior)
                    losses = []
                    for game, means in zip(validation, targets):
                        mass = distribution.probabilities(*means, allow_ties=game["allow_ties"])
                        home, away = int(game["home_score"]), int(game["away_score"])
                        probability = mass[home, away] if max(home, away) < len(mass) else 0.0
                        losses.append(-np.log(max(float(probability), 1e-15)))
                    selection["candidates"].append({"prior_games": prior, "log_loss": float(np.mean(losses))})
                selection.update({
                    "games": len(validation), "training_through": inner.trained_through.isoformat(),
                    "from_date": validation[0]["gameday"].isoformat(),
                    "through_date": validation[-1]["gameday"].isoformat(),
                    "selected_prior_games": min(selection["candidates"], key=lambda row: row["log_loss"])["prior_games"],
                })
    fitted = _fit_base(games, prior_games=selection["selected_prior_games"])
    fitted.prior_selection = selection
    return fitted


def _forecast(fitted, home_team, away_team, neutral=False, allow_ties=True, means=None, probabilities=None):
    home_score, away_score = means if means is not None else fitted.scores(home_team, away_team, neutral)
    if probabilities is None:
        probabilities = fitted.score_distribution.probabilities(home_score, away_score, allow_ties=allow_ties)
    scorelines = fitted.score_distribution.top_scorelines(probabilities, home_team, away_team)
    summary = fitted.score_distribution.summarize(probabilities, INTERVAL_COVERAGE)
    home_games, away_games = fitted.game_counts[home_team], fitted.game_counts[away_team]
    difference = summary["home_win_probability"] - summary["away_win_probability"]
    return {
        "home_team": home_team, "away_team": away_team,
        "neutral": neutral, "allow_ties": allow_ties,
        "home_score": home_score, "away_score": away_score,
        "score_prediction": scorelines[0], "top_scorelines": scorelines,
        "margin": home_score - away_score, "total": home_score + away_score,
        "favorite": None if abs(difference) < 1e-12 else home_team if difference > 0 else away_team,
        "home_games": home_games, "away_games": away_games,
        "low_data": min(home_games, away_games) < 8,
        **summary,
    }


def _evaluate(games):
    return evaluate(games, _fit, _forecast)


@dataclass
class ForecastModel:
    _fitted: _FittedScores
    metadata: dict

    def predict(self, home_team, away_team, neutral=False, allow_ties=True):
        try:
            home_team = normalize_team(home_team)
            away_team = normalize_team(away_team)
        except ValueError as error:
            raise ForecastDataError(str(error)) from error
        if home_team == away_team:
            raise ForecastDataError("Choose two different teams.")
        missing = [
            team for team in (home_team, away_team)
            if team not in self._fitted.team_indices
        ]
        if missing:
            raise ForecastDataError("No completed game history for: " + ", ".join(missing))
        if not isinstance(neutral, bool):
            raise ForecastDataError("neutral must be a boolean.")
        if not isinstance(allow_ties, bool):
            raise ForecastDataError("allow_ties must be a boolean.")

        return _forecast(self._fitted, home_team, away_team, neutral, allow_ties)



def build_forecast_model(games: list[dict]) -> ForecastModel:
    """Fit and evaluate completed games supplied from before the forecast date.

    The caller owns the forecast cutoff. Only actual completed results should
    be supplied; invalid/incomplete rows are discarded, while conflicting
    completed duplicates raise ForecastDataError instead of choosing an outcome.
    """
    cleaned, discarded, duplicates = _clean_games(games)
    if len(cleaned) < MINIMUM_GAMES:
        raise ForecastDataError(
            f"At least {MINIMUM_GAMES} unique completed games are needed for a forecast."
        )
    evaluation = _evaluate(cleaned)
    fitted = _fit(cleaned)
    metadata = {
        "name": "Experimental final-score forecast",
        "version": "ridge-joint-score-v3",
        "method": (
            "Ridge regression fits team scoring, opponent points allowed, and "
            "a shared home-field advantage with regularized team deviations. Recent games receive "
            "more weight. A smoothed distribution of historical final-score pairs "
            "is adjusted to these expected points using exponential tilting. Its "
            "most probable pair supplies the integer score prediction. "
            "Win, loss and tie chances and margin ranges all come from this same "
            "score distribution. Calibration is assessed on chronological test games."
        ),
        "training_games": len(cleaned),
        "discarded_games": discarded,
        "duplicate_games": duplicates,
        "history_seasons": sorted({game["season"] for game in cleaned}),
        "trained_through": fitted.trained_through.isoformat(),
        "teams": sorted(fitted.team_indices),
        "home_field_points": float(np.mean(fitted.home_field_points)),
        "home_field_points_by_team": {
            team: float(fitted.home_field_points[index])
            for team, index in fitted.team_indices.items()
        },
        "assumptions": {
            "ridge_alpha": RIDGE_ALPHA,
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "joint_prior_games": fitted.score_distribution.prior_games,
            "joint_prior_candidates": list(JOINT_PRIOR_CANDIDATES),
            "prior_selection": fitted.prior_selection,
            "marginal_prior_scores": MARGINAL_PRIOR_SCORES,
            "score_support_maximum": len(fitted.score_distribution.base) - 1,
            "scoreline_method": (
                "Recency-weighted joint final-score frequencies, pooled across "
                "home/away orientations and shrunk toward smoothed independent "
                "marginals. Minimum-relative-entropy exponential tilting matches "
                "the two ridge score means. Postseason scorelines exclude ties. "
                "The joint mode predicts a final score."
            ),
            "scoreline_log_loss_baseline": (
                "The same training-only league score distribution without "
                "matchup adjustments; natural logs, probabilities floored at 1e-15."
            ),
            "evaluation_fraction_of_dates": 1 - INITIAL_TRAINING_FRACTION,
            "evaluation_folds": EVALUATION_FOLDS,
            "evaluation_method": (
                "Expanding-window evaluation: start with the first 60% of dates, "
                "then evaluate up to four later blocks. Each block is predicted "
                "using only strictly earlier dates. Production refits all completed games."
            ),
            "uncertainty_method": "Central discrete quantiles from the joint score distribution.",
        },
        "limitations": [
            "Experimental score-only model; probability calibration is not established.",
            "Injuries, quarterbacks, weather, rest, and roster changes are not modeled.",
            "Binary winner accuracy and Brier score exclude ties; Brier probabilities condition on a decisive result.",
            "The predicted final score is one possible outcome; exact-score probabilities are uncalibrated.",
            "The most likely single scoreline can differ from the favorite across all outcomes.",
            "The score distribution excludes one-point finals unless observed in training and has finite tail support.",
            "The central 80% margin range is discrete; observed coverage may differ from its target.",
            "Teams with fewer than eight prior games have limited history.",
            "Missing venue labels are assumed to be home games.",
        ],
        "evaluation": evaluation,
    }
    return ForecastModel(_fitted=fitted, metadata=metadata)
