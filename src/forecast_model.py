"""Experimental pregame score forecasts from completed schedule results.

The model deliberately does not consume season aggregate EPA: those aggregates
cannot reconstruct what was known before a historical game. Parameters below
are fixed baseline assumptions, not values tuned on the evaluation period.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from math import erf, isfinite, sqrt
import re

import numpy as np
from sklearn.linear_model import Ridge


RIDGE_ALPHA = 20.0
RECENCY_HALF_LIFE_DAYS = 365.0
MINIMUM_GAMES = 12
MINIMUM_EVALUATION_TRAINING_GAMES = 40
MINIMUM_EVALUATION_GAMES = 10
MINIMUM_MARGIN_STDDEV = 7.0
INTERVAL_COVERAGE = 0.8
INTERVAL_NORMAL_QUANTILE = 1.2815515655446004

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
            game = {
                "game_id": str(source.get("game_id") or "").strip(),
                "season": season,
                "gameday": gameday,
                "home_team": home,
                "away_team": away,
                "home_score": _score(source["home_score"]),
                "away_score": _score(source["away_score"]),
                "neutral": location == "neutral",
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            discarded += 1
            continue

        fixture = (season, gameday, home, away)
        signature = fixture + (
            game["home_score"], game["away_score"], game["neutral"],
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


def _home_probability(margin, margin_stddev):
    # Continuous margin approximation; ties are not a separately modeled event.
    return 0.5 * (1.0 + erf(margin / (margin_stddev * sqrt(2.0))))


@dataclass
class _FittedScores:
    regression: Ridge
    team_indices: dict
    game_counts: Counter
    margin_stddev: float
    trained_through: date

    @property
    def home_field_points(self):
        team_count = len(self.team_indices)
        return self.regression.coef_[2 * team_count:]

    def features(self, home_team, away_team, neutral):
        team_count = len(self.team_indices)
        features = np.zeros((2, 3 * team_count), dtype=float)
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
        return features

    def scores(self, home_team, away_team, neutral):
        values = self.regression.predict(
            self.features(home_team, away_team, neutral)
        )
        return max(0.0, float(values[0])), max(0.0, float(values[1]))


def _fit(games):
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
        margin_stddev=MINIMUM_MARGIN_STDDEV,
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
    predicted = fitted.regression.predict(features).reshape(-1, 2)
    actual = scores.reshape(-1, 2)
    margin_errors = (actual[:, 0] - actual[:, 1]) - (
        predicted[:, 0] - predicted[:, 1]
    )
    # Only fit-period errors estimate the spread. Evaluation outcomes never
    # determine the uncertainty used to forecast the evaluation period.
    residual_mean = float(np.average(margin_errors, weights=game_weights))
    residual_variance = float(np.average(
        (margin_errors - residual_mean) ** 2, weights=game_weights,
    ))
    fitted.margin_stddev = max(MINIMUM_MARGIN_STDDEV, sqrt(residual_variance))
    return fitted


def _evaluate(games):
    evaluation = {
        "games": 0,
        "decisive_games": 0,
        "skipped_games": 0,
        "from_date": None,
        "through_date": None,
        "training_through": None,
        "training_games": 0,
        "margin_mae": None,
        "winner_accuracy": None,
        "home_baseline_accuracy": None,
        "brier_score": None,
        "margin_interval_coverage": None,
        "margin_stddev": None,
    }
    dates = sorted({game["gameday"] for game in games})
    if len(dates) < 2:
        return evaluation
    split_date = dates[min(len(dates) - 1, int(len(dates) * 0.8))]
    training = [game for game in games if game["gameday"] < split_date]
    held_out = [game for game in games if game["gameday"] >= split_date]
    if (
        len(training) < MINIMUM_EVALUATION_TRAINING_GAMES
        or len(held_out) < MINIMUM_EVALUATION_GAMES
    ):
        return evaluation

    model = _fit(training)
    absolute_errors = []
    winner_hits = []
    home_hits = []
    brier_scores = []
    interval_hits = []
    used_dates = []
    for game in held_out:
        if (
            game["home_team"] not in model.team_indices
            or game["away_team"] not in model.team_indices
        ):
            evaluation["skipped_games"] += 1
            continue
        home_score, away_score = model.scores(
            game["home_team"], game["away_team"], game["neutral"],
        )
        margin = home_score - away_score
        actual_margin = game["home_score"] - game["away_score"]
        probability = _home_probability(margin, model.margin_stddev)
        absolute_errors.append(abs(margin - actual_margin))
        interval_hits.append(
            abs(margin - actual_margin)
            <= INTERVAL_NORMAL_QUANTILE * model.margin_stddev
        )
        used_dates.append(game["gameday"])
        if actual_margin != 0:
            outcome = float(actual_margin > 0)
            # Exactly even predictions receive half credit instead of an
            # arbitrary home-team preference in winner accuracy.
            winner_hits.append(
                0.5 if margin == 0 else float((margin > 0) == (actual_margin > 0))
            )
            home_hits.append(outcome)
            brier_scores.append((probability - outcome) ** 2)

    evaluation.update({
        "games": len(absolute_errors),
        "decisive_games": len(winner_hits),
        "from_date": min(used_dates).isoformat() if used_dates else None,
        "through_date": max(used_dates).isoformat() if used_dates else None,
        "training_through": model.trained_through.isoformat(),
        "training_games": len(training),
        "margin_mae": float(np.mean(absolute_errors)) if absolute_errors else None,
        "winner_accuracy": float(np.mean(winner_hits)) if winner_hits else None,
        "home_baseline_accuracy": float(np.mean(home_hits)) if home_hits else None,
        "brier_score": float(np.mean(brier_scores)) if brier_scores else None,
        "margin_interval_coverage": (
            float(np.mean(interval_hits)) if interval_hits else None
        ),
        "margin_stddev": model.margin_stddev,
    })
    return evaluation


@dataclass
class ForecastModel:
    _fitted: _FittedScores
    metadata: dict

    def predict(self, home_team, away_team, neutral=False):
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

        home_score, away_score = self._fitted.scores(home_team, away_team, neutral)
        margin = home_score - away_score
        probability = _home_probability(margin, self._fitted.margin_stddev)
        radius = INTERVAL_NORMAL_QUANTILE * self._fitted.margin_stddev
        home_games = self._fitted.game_counts[home_team]
        away_games = self._fitted.game_counts[away_team]
        return {
            "home_team": home_team,
            "away_team": away_team,
            "neutral": neutral,
            "home_score": home_score,
            "away_score": away_score,
            "home_win_probability": probability,
            "away_win_probability": 1.0 - probability,
            "margin": margin,
            "total": home_score + away_score,
            "favorite": home_team if margin > 0 else away_team if margin < 0 else None,
            "home_games": home_games,
            "away_games": away_games,
            "margin_stddev": self._fitted.margin_stddev,
            "margin_interval": {
                "coverage": INTERVAL_COVERAGE,
                "low": margin - radius,
                "high": margin + radius,
            },
            "low_data": min(home_games, away_games) < 8,
        }


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
        "name": "Experimental score forecast",
        "version": "ridge-score-v1",
        "method": (
            "Ridge regression fits team scoring, opponent points allowed, and "
            "team-specific home-field effects from completed scores. Recent games receive "
            "more weight. Win chances use an approximate normal distribution of "
            "the score margin; they are uncalibrated estimates."
        ),
        "training_games": len(cleaned),
        "discarded_games": discarded,
        "duplicate_games": duplicates,
        "history_seasons": sorted({game["season"] for game in cleaned}),
        "trained_through": fitted.trained_through.isoformat(),
        "teams": sorted(fitted.team_indices),
        "margin_stddev": fitted.margin_stddev,
        "home_field_points": float(np.mean(fitted.home_field_points)),
        "home_field_points_by_team": {
            team: float(fitted.home_field_points[index])
            for team, index in fitted.team_indices.items()
        },
        "assumptions": {
            "ridge_alpha": RIDGE_ALPHA,
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "minimum_margin_stddev": MINIMUM_MARGIN_STDDEV,
            "evaluation_fraction_of_dates": 0.2,
            "evaluation_method": (
                "One chronological holdout: fit on earlier dates and evaluate on "
                "the final 20% of dates without updating during that period. "
                "Residual spread uses only the earlier fit. Production scores "
                "are then refit using all supplied completed games."
            ),
            "uncertainty_method": "Normal approximation using fit-period margin residuals.",
        },
        "limitations": [
            "Experimental score-only model; probability calibration is not established.",
            "Injuries, quarterbacks, weather, rest, and roster changes are not modeled.",
            "Ties are not modeled separately; winner accuracy and Brier score exclude ties.",
            "Score means are averages, not predictions of an exact final score.",
            "The nominal 80% margin range is approximate; actual coverage may differ.",
            "Teams with fewer than eight prior games have limited history.",
            "Missing venue labels are assumed to be home games.",
        ],
        "evaluation": evaluation,
    }
    return ForecastModel(_fitted=fitted, metadata=metadata)
