import copy
from datetime import date, timedelta
import json
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.forecast_model import ForecastDataError, build_forecast_model


def game_history(count=100):
    """Balanced fixtures with known strength and home effects plus noisy scores."""
    teams = ["BUF", "KC", "NYJ", "MIA"]
    attack = {"BUF": 5, "KC": 3, "NYJ": -4, "MIA": -1}
    allowed = {"BUF": -3, "KC": -1, "NYJ": 3, "MIA": 1}
    pairs = [(home, away) for home in teams for away in teams if home != away]
    history = []
    for index in range(count):
        home, away = pairs[index % len(pairs)]
        neutral = index % 7 == 0
        home_effect = 0 if neutral else 3
        noise = ((index * 7) % 11) - 5
        history.append({
            "game_id": f"fixture-{index}",
            "season": 2025,
            "gameday": (date(2025, 1, 1) + timedelta(days=index // 2)).isoformat(),
            "home_team": home,
            "away_team": away,
            "home_score": 23 + attack[home] + allowed[away] + home_effect + noise,
            "away_score": 23 + attack[away] + allowed[home] - home_effect - noise,
            "location": "Neutral" if neutral else "Home",
        })
    return history


class ForecastModelTests(unittest.TestCase):
    def test_neutral_predictions_are_symmetric_and_json_serializable(self):
        model = build_forecast_model(game_history())
        forward = model.predict("BUF", "NYJ", neutral=True)
        reverse = model.predict("NYJ", "BUF", neutral=True)
        self.assertAlmostEqual(forward["home_score"], reverse["away_score"])
        self.assertAlmostEqual(forward["away_score"], reverse["home_score"])
        self.assertEqual(forward["score_prediction"]["home_score"], reverse["score_prediction"]["away_score"])
        self.assertEqual(forward["score_prediction"]["away_score"], reverse["score_prediction"]["home_score"])
        self.assertAlmostEqual(forward["score_prediction"]["probability"], reverse["score_prediction"]["probability"])
        self.assertAlmostEqual(forward["margin"], -reverse["margin"])
        self.assertAlmostEqual(
            forward["home_win_probability"], reverse["away_win_probability"],
        )
        self.assertGreater(forward["home_win_probability"], 0.5)
        self.assertGreater(forward["margin_interval"]["high"], forward["margin"])
        self.assertLess(forward["margin_interval"]["low"], forward["margin"])
        json.dumps({"forecast": forward, "model": model.metadata}, allow_nan=False)

    def test_learned_home_effect_changes_margin_but_not_total(self):
        model = build_forecast_model(game_history(200))
        neutral = model.predict("BUF", "KC", neutral=True)
        hosted = model.predict("BUF", "KC", neutral=False)
        self.assertGreater(hosted["margin"], neutral["margin"])
        self.assertGreater(hosted["home_win_probability"], neutral["home_win_probability"])
        self.assertAlmostEqual(hosted["total"], neutral["total"])
        self.assertAlmostEqual(
            hosted["margin"] - neutral["margin"],
            model.metadata["home_field_points_by_team"]["BUF"],
        )

    def test_home_effects_can_differ_by_team(self):
        model = build_forecast_model(game_history(200))
        effects = model.metadata["home_field_points_by_team"]
        self.assertEqual(set(effects), {"BUF", "KC", "MIA", "NYJ"})
        self.assertNotAlmostEqual(effects["BUF"], effects["NYJ"], places=4)

    def test_evaluation_fits_only_strictly_earlier_dates(self):
        from src import forecast_model

        history = game_history()
        captured_fits = []
        original_fit = forecast_model._fit

        def capture(games):
            captured_fits.append(copy.deepcopy(games))
            return original_fit(games)

        with patch.object(forecast_model, "_fit", side_effect=capture):
            model = build_forecast_model(history)
        evaluation = model.metadata["evaluation"]
        self.assertGreater(evaluation["games"], 0)
        self.assertLess(evaluation["training_through"], evaluation["from_date"])
        self.assertEqual(len(captured_fits), 2)
        self.assertTrue(all(
            game["gameday"].isoformat() < evaluation["from_date"]
            for game in captured_fits[0]
        ))
        self.assertEqual(len(captured_fits[1]), len(history))

    def test_changed_held_out_results_do_not_change_evaluation_model_or_sigma(self):
        from src import forecast_model

        history = game_history()
        captured = []
        original_fit = forecast_model._fit

        def capture(games):
            fitted = original_fit(games)
            captured.append(fitted)
            return fitted

        with patch.object(forecast_model, "_fit", side_effect=capture):
            baseline = build_forecast_model(history)
        cutoff = baseline.metadata["evaluation"]["from_date"]
        changed = copy.deepcopy(history)
        for game in changed:
            if game["gameday"] >= cutoff:
                game["home_score"] += 35
        with patch.object(forecast_model, "_fit", side_effect=capture):
            updated = build_forecast_model(changed)
        np.testing.assert_array_equal(
            captured[0].score_distribution.base, captured[2].score_distribution.base,
        )
        before = baseline.metadata["evaluation"]
        after = updated.metadata["evaluation"]
        self.assertEqual(before["margin_stddev"], after["margin_stddev"])
        self.assertEqual(before["training_through"], after["training_through"])
        self.assertNotEqual(before["margin_mae"], after["margin_mae"])
        self.assertNotEqual(before["scoreline_log_loss"], after["scoreline_log_loss"])
        self.assertNotEqual(
            baseline.predict("BUF", "KC")["home_score"],
            updated.predict("BUF", "KC")["home_score"],
        )

    def test_duplicate_and_malformed_rows_cannot_change_fitted_forecast(self):
        history = game_history()
        malformed = [
            {**history[0], "game_id": "nan", "home_score": float("nan")},
            {**history[0], "game_id": "inf", "away_score": float("inf")},
            {**history[0], "game_id": "partial", "away_score": None},
            {**history[0], "game_id": "negative", "home_score": -1},
            {**history[0], "game_id": "boolean", "home_score": True},
            {**history[0], "game_id": "fraction", "home_score": 2.5},
            {**history[0], "game_id": "oversized", "home_score": 100000},
            {**history[0], "game_id": "date", "gameday": "bad-date"},
            {**history[0], "game_id": "self", "away_team": history[0]["home_team"]},
            {**history[0], "game_id": "location", "location": "Unknown"},
            {},
            None,
        ]
        baseline = build_forecast_model(history)
        dirty = build_forecast_model(history + history + malformed)
        self.assertEqual(dirty.metadata["training_games"], len(history))
        self.assertEqual(dirty.metadata["duplicate_games"], len(history))
        self.assertEqual(dirty.metadata["discarded_games"], len(malformed))
        self.assertEqual(baseline.predict("BUF", "KC"), dirty.predict("BUF", "KC"))

    def test_conflicting_results_fail_instead_of_choosing_an_outcome(self):
        history = game_history()
        conflicting = {**history[0], "home_score": history[0]["home_score"] + 7}
        with self.assertRaises(ForecastDataError):
            build_forecast_model(history + [conflicting])
        conflicting["game_id"] = "different-id-same-fixture"
        with self.assertRaises(ForecastDataError):
            build_forecast_model(history + [conflicting])

    def test_missing_history_and_invalid_requests_are_rejected(self):
        with self.assertRaises(ForecastDataError):
            build_forecast_model(game_history(5))
        model = build_forecast_model(game_history())
        for home, away, neutral in [
            ("BUF", "SEA", False), ("BUF", "BUF", False),
            ("BAD!", "KC", False), ("BUF", "KC", "false"),
        ]:
            with self.subTest(home=home, away=away, neutral=neutral):
                with self.assertRaises(ForecastDataError):
                    model.predict(home, away, neutral=neutral)

    def test_sparse_history_is_labeled_and_has_no_fake_evaluation(self):
        model = build_forecast_model(game_history(12))
        self.assertTrue(model.predict("BUF", "KC")["low_data"])
        evaluation = model.metadata["evaluation"]
        self.assertEqual(evaluation["games"], 0)
        self.assertIsNone(evaluation["winner_accuracy"])
        self.assertIsNone(evaluation["margin_mae"])
        self.assertIsNone(evaluation["exact_score_accuracy"])
        self.assertIsNone(evaluation["scoreline_log_loss"])

    def test_score_evaluation_distinguishes_means_modes_and_oriented_results(self):
        from src.forecast_model import _clean_games, _evaluate

        history = game_history()
        # Half of the held-out games match the mode, half reverse its teams.
        for index, game in enumerate(history[80:]):
            game["home_score"], game["away_score"] = (27, 20) if index < 10 else (20, 27)
        cleaned, _, _ = _clean_games(history)
        fitted = Mock()
        fitted.team_indices = {team: index for index, team in enumerate(["BUF", "KC", "NYJ", "MIA"])}
        fitted.trained_through = cleaned[79]["gameday"]
        fitted.margin_stddev = 10.0
        fitted.scores.return_value = (24.5, 20.5)
        mass = np.zeros((31, 31))
        mass[27, 20], mass[20, 27] = 0.2, 0.1
        baseline = np.zeros((31, 31))
        baseline[27, 20] = baseline[20, 27] = 0.1
        fitted.score_distribution.probabilities.return_value = mass
        fitted.score_distribution.baseline.return_value = baseline
        fitted.score_distribution.top_scorelines.return_value = [
            {"home_score": 27, "away_score": 20, "probability": 0.2},
        ]
        with patch("src.forecast_model._fit", return_value=fitted):
            evaluation = _evaluate(cleaned)

        self.assertEqual(evaluation["games"], 20)
        self.assertAlmostEqual(evaluation["score_mae"], 3.5)
        self.assertAlmostEqual(evaluation["score_rmse"], np.sqrt(17.25))
        self.assertAlmostEqual(evaluation["predicted_score_mae"], 3.5)
        self.assertEqual(evaluation["exact_score_accuracy"], 0.5)
        self.assertEqual(evaluation["rounded_score_accuracy"], 0.0)
        self.assertAlmostEqual(evaluation["scoreline_log_loss"], -0.5 * np.log(0.02))
        self.assertAlmostEqual(evaluation["baseline_scoreline_log_loss"], -np.log(0.1))

    def test_historical_aliases_share_one_team_rating(self):
        history = game_history()
        for index, game in enumerate(history):
            for side in ("home_team", "away_team"):
                if game[side] == "BUF":
                    game[side] = "OAK" if index % 2 else "LV"
        model = build_forecast_model(history)
        self.assertIn("LV", model.metadata["teams"])
        self.assertNotIn("OAK", model.metadata["teams"])
        self.assertEqual(model.predict("OAK", "KC"), model.predict("LV", "KC"))


if __name__ == "__main__":
    unittest.main()
