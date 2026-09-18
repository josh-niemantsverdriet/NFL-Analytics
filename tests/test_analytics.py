import unittest

import numpy as np
import polars as pl

from src.analytics import calculate_team_analytics
from src.matchup_metrics import blend_matchup_metrics


def play(**overrides):
    return {"posteam": "BUF", "defteam": "KC", "season": 2025, "season_type": "REG",
            "epa": 1.0, "pass_attempt": 0, "rush_attempt": 0, "qb_dropback": 0,
            "sack": 0, "qb_scramble": 0, "qb_kneel": 0, "qb_spike": 0,
            "yards_gained": 5, "success": 0, **overrides}


class AnalyticsTests(unittest.TestCase):
    def test_sacks_and_scrambles_are_dropbacks_and_clock_plays_are_excluded(self):
        rows = [play(pass_attempt=1, epa=2), play(sack=1, epa=-2),
                play(rush_attempt=1, qb_scramble=1, epa=1), play(rush_attempt=1, epa=-1),
                play(rush_attempt=1, qb_kneel=1, epa=90), play(pass_attempt=1, qb_spike=1, epa=90),
                play(pass_attempt=1, epa=float("nan")), play(pass_attempt=1, epa=float("inf")),
                play(pass_attempt=1, season_type="POST", epa=90), play(pass_attempt=1, season=2024, epa=90)]
        result = calculate_team_analytics(pl.DataFrame(rows), 2025, "2025-12-01")
        teams = {row["team"]: row for row in result.to_dicts()}
        self.assertEqual(set(teams), {"BUF", "KC"})  # preserve teams with only one side observed
        self.assertEqual(teams["BUF"]["plays"], 4)
        self.assertAlmostEqual(teams["BUF"]["pass_epa_per_play"], 1 / 3)
        self.assertAlmostEqual(teams["BUF"]["rush_epa_per_play"], -1)
        self.assertAlmostEqual(teams["BUF"]["pass_rate"], 0.75)
        self.assertAlmostEqual(teams["BUF"]["success_rate"], 0.5)
        self.assertEqual(teams["KC"]["def_plays"], 4)
        self.assertAlmostEqual(teams["KC"]["def_epa_per_play"], 0)
        self.assertIsNone(teams["KC"]["epa_per_play"])

    def test_64000_simulated_plays_preserve_offense_defense_totals(self):
        rng = np.random.default_rng(921)
        count = 64000
        teams = np.array([f"T{index:02}" for index in range(32)])
        offense = rng.integers(0, 32, count)
        defense = (offense + rng.integers(1, 32, count)) % 32
        dropback = rng.random(count) < 0.62
        epa = rng.normal(0, 1.4, count)
        frame = pl.DataFrame({
            "posteam": teams[offense], "defteam": teams[defense], "epa": epa,
            "pass": dropback.astype(int), "rush": (~dropback).astype(int),
            "yards_gained": rng.integers(-12, 80, count),
        })
        result = calculate_team_analytics(frame, 2025, "2025-12-01")
        self.assertEqual(result.height, 32)
        self.assertEqual(result["plays"].sum(), count)
        self.assertEqual(result["def_plays"].sum(), count)
        offense_mean = (result["epa_per_play"] * result["plays"]).sum() / count
        defense_mean = (result["def_epa_per_play"] * result["def_plays"]).sum() / count
        self.assertAlmostEqual(offense_mean, float(epa.mean()), places=12)
        self.assertAlmostEqual(defense_mean, float(epa.mean()), places=12)
        self.assertTrue(all(0 <= value <= 1 for value in result["success_rate"]))

    def test_empty_filtered_data_has_stable_schema(self):
        result = calculate_team_analytics(pl.DataFrame([play(qb_kneel=1, rush_attempt=1)]), 2025, "2025-12-01")
        self.assertEqual(result.height, 0)
        self.assertIn("def_epa_per_play", result.columns)

    def test_descriptive_comparison_preserves_missing_metrics(self):
        result = blend_matchup_metrics(
            {"team": "BUF", "epa_per_play": 0.2, "success_rate": 0.5},
            {"team": "KC", "def_epa_per_play": -0.1, "def_success_rate_allowed": 0.4},
        )
        self.assertAlmostEqual(result["expected_epa_per_play"], 0.05)
        self.assertAlmostEqual(result["expected_success_rate"], 0.45)
        self.assertIsNone(result["expected_pass_epa_per_play"])


if __name__ == "__main__":
    unittest.main()
