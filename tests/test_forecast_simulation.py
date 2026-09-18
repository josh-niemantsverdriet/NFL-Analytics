"""Thousands of synthetic games; exact invariants, not invented accuracy claims."""

import copy
from collections import Counter
import json
import unittest

import numpy as np

from src.forecast_model import _clean_games, _fit, _forecast, build_forecast_model
from src.forecast_simulation import SCENARIOS, TEAMS, simulate_seasons


class ForecastSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Six distinct environments, 4 seasons each: 6,552 completed games.
        cls.histories = [simulate_seasons(seed, 4, scenario) for seed, scenario in enumerate(SCENARIOS)]
        cls.models = [_fit(_clean_games(history)[0]) for history in cls.histories]

    def test_seeded_seasons_are_reproducible_and_cover_all_teams(self):
        self.assertEqual(sum(map(len, self.histories)), 6552)
        self.assertEqual(self.histories[0], simulate_seasons(0, 4, "balanced"))
        for history in self.histories:
            self.assertEqual({game["home_team"] for game in history}, set(TEAMS))
            self.assertEqual(len({game["game_id"] for game in history}), len(history))
            self.assertTrue(all(g["home_score"] != g["away_score"] for g in history if g["game_type"] == "SB"))
            for season in {g["season"] for g in history}:
                hosted = Counter(g["home_team"] for g in history if g["season"] == season and g["game_type"] == "REG")
                self.assertTrue(all(8 <= hosted[team] <= 9 for team in TEAMS))

    def test_192_matchups_have_coherent_probabilities_and_legal_scorelines(self):
        for model in self.models:
            for index, home in enumerate(TEAMS):
                away = TEAMS[(index + 11) % len(TEAMS)]
                with self.subTest(home=home, away=away, through=model.trained_through):
                    neutral, allow_ties = index % 2 == 0, index % 3 != 0
                    forecast = _forecast(model, home, away, neutral, allow_ties)
                    self.assertEqual(forecast["score_prediction"]["method"], "highest_probability_exact_score")
                    self.assertEqual(forecast["score_prediction"]["home_score"], forecast["top_scorelines"][0]["home_score"])
                    self.assertEqual(forecast["score_prediction"]["away_score"], forecast["top_scorelines"][0]["away_score"])
                    self.assertEqual(forecast["typical_score_estimate"]["method"], "minimum_expected_absolute_error")
                    if not allow_ties:
                        self.assertNotEqual(forecast["score_prediction"]["home_score"], forecast["score_prediction"]["away_score"])
                    json.dumps(forecast, allow_nan=False)
                    chances = [forecast[key] for key in ("home_win_probability", "away_win_probability", "tie_probability")]
                    self.assertAlmostEqual(sum(chances), 1.0, places=10)
                    self.assertTrue(all(0 <= chance <= 1 for chance in chances))
                    self.assertAlmostEqual(forecast["total"], forecast["home_score"] + forecast["away_score"])
                    self.assertLessEqual(forecast["margin_interval"]["low"], forecast["margin_interval"]["high"])
                    if not allow_ties:
                        self.assertEqual(forecast["tie_probability"], 0)
                    for score in forecast["top_scorelines"]:
                        self.assertIs(type(score["home_score"]), int)
                        self.assertIs(type(score["away_score"]), int)
                        self.assertGreater(score["probability"], 0)
                        if not allow_ties:
                            self.assertNotEqual(score["home_score"], score["away_score"])

    def test_neutral_reversal_for_each_simulated_environment(self):
        for model in self.models:
            forward = _forecast(model, "BUF", "KC", True)
            reverse = _forecast(model, "KC", "BUF", True)
            self.assertAlmostEqual(forward["home_score"], reverse["away_score"])
            self.assertAlmostEqual(forward["home_win_probability"], reverse["away_win_probability"])
            self.assertEqual(forward["margin_interval"]["low"], -reverse["margin_interval"]["high"])
            self.assertEqual(forward["score_prediction"]["home_score"], reverse["score_prediction"]["away_score"])

    def test_2000_dirty_rows_and_input_order_cannot_change_clean_history(self):
        history = self.histories[0]
        dirty = copy.deepcopy(history)
        dirty.extend(copy.deepcopy(history[:1000]))
        dirty.extend({**row, "game_id": f"broken-{index}", "home_score": float("nan")}
                     for index, row in enumerate(history[:1000]))
        np.random.default_rng(2026).shuffle(dirty)
        cleaned, discarded, duplicates = _clean_games(dirty)
        self.assertEqual(discarded, 1000)
        self.assertEqual(duplicates, 1000)
        self.assertEqual(cleaned, _clean_games(history)[0])

    def test_nested_selection_and_outer_evaluation_remain_chronological(self):
        model = build_forecast_model(self.histories[2])
        evaluation = model.metadata["evaluation"]
        self.assertEqual(evaluation["method"], "expanding_window")
        self.assertEqual(len(evaluation["folds"]), 4)
        self.assertGreater(evaluation["games"], 400)
        self.assertEqual(sum(fold["games"] for fold in evaluation["folds"]), evaluation["games"])
        self.assertEqual(sum(bin_["games"] for bin_ in evaluation["calibration_bins"]), evaluation["decisive_games"])
        for fold in evaluation["folds"]:
            self.assertLess(fold["training_through"], fold["from_date"])
            selection = fold["distribution_selection"]
            self.assertGreaterEqual(selection["games"], 20)
            self.assertLess(selection["training_through"], selection["from_date"])
            self.assertLess(selection["through_date"], fold["from_date"])
            self.assertIn(selection["selected_half_life_days"], (120, 180, 270))
            self.assertEqual(len(selection["recency_candidates"]), 3)
            self.assertIn(selection["selected_pair_dependence"], (0, 0.05, 0.1))
        json.dumps(model.metadata, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
