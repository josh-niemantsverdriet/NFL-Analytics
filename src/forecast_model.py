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
    MARGINAL_PRIOR_SCORES, MAXIMUM_OBSERVED_SCORE, PAIR_DEPENDENCE,
    PAIR_DEPENDENCE_CANDIDATES, ScoreDistribution,
)

RIDGE_ALPHA = 20.0
RECENCY_HALF_LIFE_DAYS = 180.0
RECENCY_CANDIDATES = (120.0, 180.0, 270.0)
MINIMUM_GAMES = 12
INTERVAL_COVERAGE = 0.8
POSTSEASON_GAME_TYPES = {"WC", "DIV", "CON", "SB"}
MINIMUM_DISTRIBUTION_SELECTION_GAMES = 200
MAXIMUM_DISTRIBUTION_VALIDATION_GAMES = 48

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
    distribution_selection: dict | None = None
    recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS
    season_weights: list | None = None
    current_season_counts: Counter | None = None

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


def _recency_weights(games, half_life_days):
    latest = max(game["gameday"] for game in games)
    return np.array([
        0.5 ** ((latest - game["gameday"]).days / half_life_days)
        for game in games
    ], dtype=float)


def _fit_base(games, pair_dependence=PAIR_DEPENDENCE, half_life_days=RECENCY_HALF_LIFE_DAYS):
    teams = sorted({
        game[side] for game in games for side in ("home_team", "away_team")
    })
    counts = Counter(
        game[side] for game in games for side in ("home_team", "away_team")
    )
    trained_through = max(game["gameday"] for game in games)
    latest_season = max(game["season"] for game in games)
    fitted = _FittedScores(
        regression=Ridge(alpha=RIDGE_ALPHA, fit_intercept=True, solver="cholesky"),
        team_indices={team: index for index, team in enumerate(teams)},
        game_counts=counts,
        trained_through=trained_through,
        recency_half_life_days=half_life_days,
        current_season_counts=Counter(
            game[side] for game in games if game["season"] == latest_season
            for side in ("home_team", "away_team")
        ),
    )
    features = np.vstack([
        fitted.features(game["home_team"], game["away_team"], game["neutral"])
        for game in games
    ])
    scores = np.array([
        game[side] for game in games for side in ("home_score", "away_score")
    ], dtype=float)
    game_weights = _recency_weights(games, half_life_days)
    # Keep Ridge's penalty comparable across half-lives. Unnormalized faster
    # decay otherwise shrinks every team harder merely by reducing total mass.
    fitted.regression.fit(features, scores, sample_weight=np.repeat(game_weights / game_weights.mean(), 2))
    fitted.season_weights = [
        {"season": season, "games": sum(game["season"] == season for game in games),
         "weight_share": float(sum(weight for game, weight in zip(games, game_weights) if game["season"] == season) / game_weights.sum())}
        for season in sorted({game["season"] for game in games}, reverse=True)
    ]
    actual = scores.reshape(-1, 2)
    fitted.score_distribution = ScoreDistribution.fit(actual, game_weights, pair_dependence=pair_dependence)
    return fitted


def _fit(games):
    """Choose recency and score-pair dependence on inner dates, then refit."""
    selection = {"games": 0, "selected_pair_dependence": PAIR_DEPENDENCE, "candidates": [],
                 "selected_half_life_days": RECENCY_HALF_LIFE_DAYS, "recency_candidates": []}
    if len(games) >= MINIMUM_DISTRIBUTION_SELECTION_GAMES:
        dates = sorted({game["gameday"] for game in games})
        split = dates[min(len(dates) - 1, int(len(dates) * 0.8))]
        earlier = [g for g in games if g["gameday"] < split]
        validation = [g for g in games if g["gameday"] >= split]
        if len(earlier) >= 100 and len(validation) >= 20:
            recency_fits = {}
            for half_life in RECENCY_CANDIDATES:
                candidate = _fit_base(earlier, half_life_days=half_life)
                eligible = [g for g in validation if g["home_team"] in candidate.team_indices and g["away_team"] in candidate.team_indices]
                if len(eligible) < 20:
                    continue
                errors = [np.array(candidate.scores(g["home_team"], g["away_team"], g["neutral"])) - [g["home_score"], g["away_score"]] for g in eligible]
                selection["recency_candidates"].append({"half_life_days": half_life, "score_mse": float(np.mean(np.square(errors))), "games": len(eligible)})
                recency_fits[half_life] = candidate
            if recency_fits:
                selection["selected_half_life_days"] = min(selection["recency_candidates"], key=lambda row: row["score_mse"])["half_life_days"]
            if len(validation) > MAXIMUM_DISTRIBUTION_VALIDATION_GAMES:
                validation = [validation[i] for i in np.linspace(0, len(validation) - 1, MAXIMUM_DISTRIBUTION_VALIDATION_GAMES, dtype=int)]
            inner = recency_fits.get(selection["selected_half_life_days"]) or _fit_base(earlier)
            validation = [g for g in validation if g["home_team"] in inner.team_indices and g["away_team"] in inner.team_indices]
            targets = [inner.scores(g["home_team"], g["away_team"], g["neutral"]) for g in validation]
            weights = _recency_weights(earlier, selection["selected_half_life_days"])
            actual = np.array([[g["home_score"], g["away_score"]] for g in earlier])
            if len(validation) >= 20:
                for pair_dependence in PAIR_DEPENDENCE_CANDIDATES:
                    distribution = ScoreDistribution.fit(actual, weights, pair_dependence=pair_dependence)
                    losses = []
                    for game, means in zip(validation, targets):
                        mass = distribution.probabilities(*means, allow_ties=game["allow_ties"])
                        home, away = int(game["home_score"]), int(game["away_score"])
                        probability = mass[home, away] if max(home, away) < len(mass) else 0.0
                        losses.append(-np.log(max(float(probability), 1e-15)))
                    selection["candidates"].append({"pair_dependence": pair_dependence, "log_loss": float(np.mean(losses))})
                selection.update({
                    "games": len(validation), "training_through": inner.trained_through.isoformat(),
                    "from_date": validation[0]["gameday"].isoformat(),
                    "through_date": validation[-1]["gameday"].isoformat(),
                    "selected_pair_dependence": min(selection["candidates"], key=lambda row: row["log_loss"])["pair_dependence"],
                })
    fitted = _fit_base(games, pair_dependence=selection["selected_pair_dependence"], half_life_days=selection["selected_half_life_days"])
    fitted.distribution_selection = selection
    return fitted


def _forecast(fitted, home_team, away_team, neutral=False, allow_ties=True, means=None, probabilities=None):
    home_score, away_score = means if means is not None else fitted.scores(home_team, away_team, neutral)
    if probabilities is None:
        probabilities = fitted.score_distribution.probabilities(home_score, away_score, allow_ties=allow_ties)
    scorelines = fitted.score_distribution.top_scorelines(probabilities, home_team, away_team)
    primary_scoreline = scorelines[0] | {"method": "highest_probability_exact_score"}
    typical_score = fitted.score_distribution.point_scoreline(probabilities, home_team, away_team)
    summary = fitted.score_distribution.summarize(probabilities, INTERVAL_COVERAGE)
    home_games, away_games = fitted.game_counts[home_team], fitted.game_counts[away_team]
    difference = summary["home_win_probability"] - summary["away_win_probability"]
    return {
        "home_team": home_team, "away_team": away_team,
        "neutral": neutral, "allow_ties": allow_ties,
        "home_score": home_score, "away_score": away_score,
        "score_prediction": primary_scoreline,
        "typical_score_estimate": typical_score,
        "top_scorelines": scorelines,
        "margin": home_score - away_score, "total": home_score + away_score,
        "favorite": None if abs(difference) < 1e-12 else home_team if difference > 0 else away_team,
        "home_games": home_games, "away_games": away_games,
        "home_current_season_games": fitted.current_season_counts[home_team],
        "away_current_season_games": fitted.current_season_counts[away_team],
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
        "version": "ridge-smooth-score-v6",
        "method": (
            "Ridge regression fits team scoring, opponent points allowed, and "
            "a shared home-field advantage with regularized team deviations. Recent games receive "
            "more weight. A smoothed distribution of historical final-score pairs "
            "is adjusted to these expected points using exponential tilting. Its "
            "The displayed score prediction is the highest-probability exact final; "
            "a separate typical-score estimate minimizes expected absolute score error. "
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
            "recency_half_life_days": fitted.recency_half_life_days,
            "recency_candidates": list(RECENCY_CANDIDATES),
            "regression_weight_normalization": "mean_one",
            "history_weight_by_season": fitted.season_weights,
            "point_forecast_method": "minimum_expected_absolute_error",
            "pair_dependence": fitted.score_distribution.pair_dependence,
            "pair_dependence_candidates": list(PAIR_DEPENDENCE_CANDIDATES),
            "distribution_selection": fitted.distribution_selection,
            "marginal_prior_scores": MARGINAL_PRIOR_SCORES,
            "score_support_maximum": len(fitted.score_distribution.base) - 1,
            "scoreline_method": (
                "Recency-weighted marginal final-score frequencies with a small "
                "validated empirical-pair dependence blend. Minimum-relative-entropy "
                "exponential tilting matches the two ridge score means. Postseason scorelines exclude ties. "
                "The displayed prediction is the highest-probability exact final. The separate typical-score estimate minimizes expected absolute point error on supported score pairs."
            ),
            "scoreline_log_loss_baseline": (
                "The same training-only smooth league score distribution without "
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
            "The projected score summarizes the distribution; it is not the most likely exact outcome.",
            "A tied projection means a close matchup, not that a tied result is likely.",
            "The score distribution excludes one-point finals unless observed in training and has finite tail support.",
            "The central 80% margin range is discrete; observed coverage may differ from its target.",
            "Teams with fewer than eight prior games have limited history.",
            "Missing venue labels are assumed to be home games.",
        ],
        "evaluation": evaluation,
    }
    return ForecastModel(_fitted=fitted, metadata=metadata)
