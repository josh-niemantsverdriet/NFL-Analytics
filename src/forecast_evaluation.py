"""Expanding-window evaluation with whole dates kept on one side of each split."""

from collections import Counter

import numpy as np


EVALUATION_FOLDS = 4
INITIAL_TRAINING_FRACTION = 0.6
MINIMUM_TRAINING_GAMES = 40
MINIMUM_TEST_GAMES = 10
LOG_PROBABILITY_FLOOR = 1e-15


def chronological_folds(games):
    dates = sorted({game["gameday"] for game in games})
    start = max(1, int(len(dates) * INITIAL_TRAINING_FRACTION))
    while start < len(dates) and sum(game["gameday"] < dates[start] for game in games) < MINIMUM_TRAINING_GAMES:
        start += 1
    if start >= len(dates) or sum(game["gameday"] >= dates[start] for game in games) < MINIMUM_TEST_GAMES:
        return
    for block in np.array_split(dates[start:], min(EVALUATION_FOLDS, len(dates) - start)):
        training = [game for game in games if game["gameday"] < block[0]]
        testing = [game for game in games if block[0] <= game["gameday"] <= block[-1]]
        yield training, testing


def _mean(values):
    return float(np.mean(values)) if values else None


def evaluate(games, fit, forecast):
    records, folds = [], []
    skipped = 0
    for training, testing in chronological_folds(games):
        model = fit(training)
        baseline_scores = np.mean([[g["home_score"], g["away_score"]] for g in training], axis=0)
        # A smoothed training-only constant win probability is a stronger
        # probability baseline than the always-home classification rule.
        decisive_training = [g for g in training if g["home_score"] != g["away_score"]]
        baseline_home = (1 + sum(g["home_score"] > g["away_score"] for g in decisive_training)) / (2 + len(decisive_training))
        fold_records = []
        for game in testing:
            home, away = game["home_team"], game["away_team"]
            if home not in model.team_indices or away not in model.team_indices:
                skipped += 1
                continue
            means = model.scores(home, away, game["neutral"])
            mass = model.score_distribution.probabilities(*means, allow_ties=game["allow_ties"])
            prediction = forecast(model, home, away, game["neutral"], game["allow_ties"], means, mass)
            actual = np.array([game["home_score"], game["away_score"]], dtype=int)
            point = prediction["score_prediction"]
            predicted_scores = np.array([point["home_score"], point["away_score"]])
            mode = prediction["top_scorelines"][0]
            modal_scores = np.array([mode["home_score"], mode["away_score"]])
            actual_margin = int(actual[0] - actual[1])
            interval = prediction["margin_interval"]
            p_home, p_away = prediction["home_win_probability"], prediction["away_win_probability"]
            p_tie = prediction.get("tie_probability", 0.0)
            conditional_home = p_home / (p_home + p_away) if p_home + p_away > 0 else 0.5
            in_support = max(actual) < len(mass)
            observed_p = mass[tuple(actual)] if in_support else 0.0
            baseline_mass = model.score_distribution.baseline(game["allow_ties"])
            baseline_p = baseline_mass[tuple(actual)] if in_support else 0.0
            league_means = np.repeat(baseline_scores.mean(), 2) if game["neutral"] else baseline_scores
            outcome = np.array([actual_margin > 0, actual_margin < 0, actual_margin == 0], dtype=float)
            row = {
                "date": game["gameday"].isoformat(),
                "score_mae": float(np.mean(np.abs(np.array(means) - actual))),
                "score_mse": float(np.mean((np.array(means) - actual) ** 2)),
                "baseline_score_mae": float(np.mean(np.abs(league_means - actual))),
                "predicted_score_mae": float(np.mean(np.abs(predicted_scores - actual))),
                "modal_score_mae": float(np.mean(np.abs(modal_scores - actual))),
                "modal_exact_score_accuracy": float(np.array_equal(modal_scores, actual)),
                "projected_pair": tuple(predicted_scores.tolist()),
                "exact_score_accuracy": float(np.array_equal(predicted_scores, actual)),
                "rounded_score_accuracy": float(np.array_equal(np.floor(np.array(means) + 0.5), actual)),
                "scoreline_log_loss": float(-np.log(max(observed_p, LOG_PROBABILITY_FLOOR))),
                "baseline_scoreline_log_loss": float(-np.log(max(baseline_p, LOG_PROBABILITY_FLOOR))),
                "margin_mae": abs(prediction["margin"] - actual_margin),
                "margin_interval_coverage": float(interval["low"] <= actual_margin <= interval["high"]),
                "margin_interval_width": interval["high"] - interval["low"],
                "outcome_brier_score": float(np.sum((np.array([p_home, p_away, p_tie]) - outcome) ** 2)),
                "outcome": float(actual_margin > 0) if actual_margin != 0 else None,
                "home_probability": conditional_home,
                "baseline_home_probability": baseline_home,
            }
            fold_records.append(row)
        records.extend(fold_records)
        folds.append({
            "training_games": len(training),
            "training_through": model.trained_through.isoformat(),
            "from_date": testing[0]["gameday"].isoformat(),
            "through_date": testing[-1]["gameday"].isoformat(),
            "games": len(fold_records),
            "score_mae": _mean([row["score_mae"] for row in fold_records]),
            "scoreline_log_loss": _mean([row["scoreline_log_loss"] for row in fold_records]),
            "prior_selection": model.prior_selection,
        })

    metric_names = (
        "score_mae", "baseline_score_mae", "predicted_score_mae", "exact_score_accuracy",
        "rounded_score_accuracy", "scoreline_log_loss", "baseline_scoreline_log_loss",
        "margin_mae", "margin_interval_coverage", "margin_interval_width", "outcome_brier_score",
        "modal_score_mae", "modal_exact_score_accuracy",
    )
    result = {name: _mean([row[name] for row in records]) for name in metric_names}
    decisive = [row for row in records if row["outcome"] is not None]
    probabilities = [row["home_probability"] for row in decisive]
    result.update({
        "method": "expanding_window",
        "folds": folds,
        "games": len(records),
        "decisive_games": len(decisive),
        "skipped_games": skipped,
        "from_date": records[0]["date"] if records else None,
        "through_date": records[-1]["date"] if records else None,
        # These two fields describe the first fold for older API consumers.
        "training_through": folds[0]["training_through"] if folds else None,
        "training_games": folds[0]["training_games"] if folds else 0,
        "score_rmse": float(np.sqrt(np.mean([r["score_mse"] for r in records]))) if records else None,
        "winner_accuracy": _mean([
            0.5 if abs(r["home_probability"] - 0.5) < 1e-12 else float((r["home_probability"] > 0.5) == r["outcome"])
            for r in decisive
        ]),
        "home_baseline_accuracy": _mean([r["outcome"] for r in decisive]),
        "brier_score": _mean([(r["home_probability"] - r["outcome"]) ** 2 for r in decisive]),
        "baseline_brier_score": _mean([(r["baseline_home_probability"] - r["outcome"]) ** 2 for r in decisive]),
        "calibration_bins": [],
    })
    for bin_index in range(5):
        selected = [r for r in decisive if min(4, int(r["home_probability"] * 5)) == bin_index]
        result["calibration_bins"].append({
            "low": bin_index / 5, "high": (bin_index + 1) / 5, "games": len(selected),
            "predicted": _mean([r["home_probability"] for r in selected]),
            "observed": _mean([r["outcome"] for r in selected]),
        })
    # Count is explicit: bin summaries are diagnostics, not a fitted calibrator.
    result["calibration_games"] = len(probabilities)
    projected = Counter(r["projected_pair"] for r in records)
    result["projected_unique_scorelines"] = len(projected)
    result["most_common_projected_score_share"] = max(projected.values()) / len(records) if records else None
    return result
