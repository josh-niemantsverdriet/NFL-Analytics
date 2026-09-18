import unittest

import numpy as np

from src.score_distribution import ScoreDistribution


def scoring_history():
    """Repeated NFL scorelines with a strong 27-20 mode and uneven spacing."""
    return np.array(
        [[27, 20]] * 80
        + [[24, 17]] * 25
        + [[20, 10]] * 15
        + [[30, 24]] * 10,
        dtype=int,
    )


class ScoreDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scores = scoring_history()
        cls.distribution = ScoreDistribution.fit(scores, np.ones(len(scores)))

    def test_probabilities_are_finite_normalized_and_match_requested_means(self):
        # Include ordinary games, heavily mismatched teams, near-support limits,
        # and exact-zero boundary solutions where a finite tilt does not exist.
        for home, away in [
            (23.6, 19.2), (20.0, 20.0), (40.0, 7.0), (90.0, 2.0),
            (99.5, 0.01), (0.0, 27.0), (27.0, 0.0), (0.0, 0.0),
        ]:
            with self.subTest(home=home, away=away):
                probabilities = self.distribution.probabilities(home, away)
                self.assertTrue(np.all(np.isfinite(probabilities)))
                self.assertTrue(np.all(probabilities >= 0))
                self.assertAlmostEqual(float(probabilities.sum()), 1.0, places=10)
                points = np.arange(probabilities.shape[0])
                predicted_home = float(probabilities.sum(axis=1) @ points)
                predicted_away = float(probabilities.sum(axis=0) @ points)
                self.assertAlmostEqual(predicted_home, home, delta=1e-5)
                self.assertAlmostEqual(predicted_away, away, delta=1e-5)

    def test_reversing_teams_transposes_the_distribution_and_scorelines(self):
        forward = self.distribution.probabilities(28.3, 17.8)
        reverse = self.distribution.probabilities(17.8, 28.3)
        np.testing.assert_array_equal(forward, reverse.T)
        forward_scores = self.distribution.top_scorelines(forward, "BUF", "KC")
        reverse_scores = self.distribution.top_scorelines(reverse, "KC", "BUF")
        self.assertEqual(forward_scores, [
            {
                "home_score": row["away_score"],
                "away_score": row["home_score"],
                "probability": row["probability"],
            }
            for row in reverse_scores
        ])

    def test_equal_means_use_canonical_franchise_order_to_break_mode_ties(self):
        probabilities = self.distribution.probabilities(20.0, 20.0)
        np.testing.assert_array_equal(probabilities, probabilities.T)
        forward = self.distribution.top_scorelines(probabilities, "BUF", "KC")
        reverse = self.distribution.top_scorelines(probabilities, "KC", "BUF")
        # This fixture has two equally probable, mirrored, non-tied finals.
        self.assertNotEqual(forward[0]["home_score"], forward[0]["away_score"])
        self.assertEqual(forward[0]["probability"], forward[1]["probability"])
        for first, second in zip(forward, reverse):
            self.assertEqual(first["home_score"], second["away_score"])
            self.assertEqual(first["away_score"], second["home_score"])
            self.assertEqual(first["probability"], second["probability"])

    def test_mode_uses_observed_score_patterns_instead_of_rounding_means(self):
        home_mean, away_mean = 23.6, 19.2
        probabilities = self.distribution.probabilities(home_mean, away_mean)
        scorelines = self.distribution.top_scorelines(probabilities, "BUF", "KC")
        mode = scorelines[0]
        self.assertEqual((mode["home_score"], mode["away_score"]), (27, 20))
        self.assertNotEqual(
            (mode["home_score"], mode["away_score"]),
            (round(home_mean), round(away_mean)),
        )
        self.assertEqual(mode["probability"], float(probabilities.max()))
        self.assertEqual(len(scorelines), 3)
        self.assertGreater(sum(row["probability"] for row in scorelines), 0)
        self.assertLessEqual(sum(row["probability"] for row in scorelines), 1)
        self.assertEqual(len({
            (row["home_score"], row["away_score"]) for row in scorelines
        }), len(scorelines))
        for index, row in enumerate(scorelines):
            self.assertIs(type(row["home_score"]), int)
            self.assertIs(type(row["away_score"]), int)
            self.assertGreaterEqual(row["home_score"], 0)
            self.assertGreaterEqual(row["away_score"], 0)
            self.assertGreater(row["probability"], 0)
            if index:
                self.assertLessEqual(row["probability"], scorelines[index - 1]["probability"])

    def test_smoothing_allows_unseen_scores_but_omits_unobserved_one_point_finals(self):
        probabilities = self.distribution.probabilities(23.6, 19.2)
        for home, away in [(11, 8), (57, 44), (0, 5)]:
            with self.subTest(home=home, away=away):
                self.assertGreater(float(probabilities[home, away]), 0)
        self.assertEqual(float(probabilities[1, :].sum()), 0)
        self.assertEqual(float(probabilities[:, 1].sum()), 0)

    def test_observed_one_point_final_is_retained_in_support(self):
        scores = np.vstack([scoring_history(), [[6, 1]]])
        fitted = ScoreDistribution.fit(scores, np.ones(len(scores)))
        probabilities = fitted.probabilities(23.6, 19.2)
        self.assertGreater(float(probabilities[6, 1]), 0)
        self.assertGreater(float(probabilities[1, 6]), 0)

    def test_zero_score_boundary_has_no_impossible_alternative_scorelines(self):
        probabilities = self.distribution.probabilities(0.0, 0.0)
        self.assertEqual(self.distribution.top_scorelines(probabilities, "BUF", "KC"), [
            {"home_score": 0, "away_score": 0, "probability": 1.0},
        ])

    def test_postseason_removes_tied_finals_even_when_they_dominate_history(self):
        scores = np.array([[20, 20]] * 100 + [[27, 20]] * 20 + [[20, 17]] * 20)
        fitted = ScoreDistribution.fit(scores, np.ones(len(scores)))
        regular = fitted.probabilities(20.0, 20.0)
        regular_mode = fitted.top_scorelines(regular, "BUF", "KC")[0]
        self.assertEqual((regular_mode["home_score"], regular_mode["away_score"]), (20, 20))
        original_base = fitted.base.copy()
        postseason = fitted.probabilities(20.0, 20.0, allow_ties=False)
        baseline = fitted.baseline(allow_ties=False)
        for probabilities in (postseason, baseline):
            self.assertTrue(np.all(np.isfinite(probabilities)))
            self.assertTrue(np.all(probabilities >= 0))
            self.assertAlmostEqual(float(probabilities.sum()), 1.0, places=10)
            self.assertEqual(float(np.trace(probabilities)), 0.0)
        points = np.arange(postseason.shape[0])
        self.assertAlmostEqual(float(postseason.sum(axis=1) @ points), 20.0, delta=1e-5)
        self.assertAlmostEqual(float(postseason.sum(axis=0) @ points), 20.0, delta=1e-5)
        for row in fitted.top_scorelines(postseason, "BUF", "KC"):
            self.assertNotEqual(row["home_score"], row["away_score"])
        # Removing playoff ties must not alter later regular-season forecasts.
        np.testing.assert_array_equal(fitted.base, original_base)
        np.testing.assert_array_equal(fitted.probabilities(20.0, 20.0), regular)

    def test_postseason_distribution_preserves_matchup_means_and_reversal(self):
        forward = self.distribution.probabilities(25.0, 18.0, allow_ties=False)
        reverse = self.distribution.probabilities(18.0, 25.0, allow_ties=False)
        np.testing.assert_array_equal(forward, reverse.T)
        self.assertEqual(float(np.trace(forward)), 0.0)
        self.assertAlmostEqual(float(forward.sum()), 1.0, places=10)
        points = np.arange(forward.shape[0])
        self.assertAlmostEqual(float(forward.sum(axis=1) @ points), 25.0, delta=1e-5)
        self.assertAlmostEqual(float(forward.sum(axis=0) @ points), 18.0, delta=1e-5)

    def test_infeasible_postseason_expected_scores_are_rejected(self):
        for home, away in [(0.0, 0.0), (0.5, 0.5), (0.0, 1.9)]:
            with self.subTest(home=home, away=away):
                with self.assertRaisesRegex(ValueError, "without a tie"):
                    self.distribution.probabilities(home, away, allow_ties=False)

    def test_invalid_expected_scores_are_rejected(self):
        maximum = self.distribution.base.shape[0] - 1
        for home, away in [
            (-1, 20), (20, -1), (float("nan"), 20),
            (20, float("inf")), (maximum, 20), (20, maximum + 1),
        ]:
            with self.subTest(home=home, away=away):
                with self.assertRaises(ValueError):
                    self.distribution.probabilities(home, away)

    def test_malformed_training_arrays_are_rejected_before_allocation(self):
        for scores, weights in [
            ([], []), ([20, 10], [1]), ([[20, 10]], []), ([[20, 10]], [0]),
            ([[20, 10]], [-1]), ([[20, 10]], [float("nan")]),
            ([[20.5, 10]], [1]), ([[float("inf"), 10]], [1]), ([[100000, 10]], [1]),
        ]:
            with self.subTest(scores=scores, weights=weights):
                with self.assertRaises(ValueError):
                    ScoreDistribution.fit(scores, weights)

    def test_joint_summary_includes_ties_and_correct_margin_quantiles(self):
        mass = np.zeros((31, 31))
        mass[27, 20], mass[20, 27], mass[20, 20] = 0.6, 0.3, 0.1
        summary = ScoreDistribution.summarize(mass)
        self.assertAlmostEqual(summary["home_win_probability"], 0.6)
        self.assertAlmostEqual(summary["away_win_probability"], 0.3)
        self.assertAlmostEqual(summary["tie_probability"], 0.1)
        self.assertEqual(summary["margin_interval"], {"coverage": 0.8, "low": -7, "high": 7})
        reverse = ScoreDistribution.summarize(mass.T)
        self.assertEqual(reverse["home_win_probability"], summary["away_win_probability"])

    def test_zero_weight_results_cannot_expand_score_support(self):
        clean = ScoreDistribution.fit([[20, 17]], [1])
        dirty = ScoreDistribution.fit([[20, 17], [200, 200]], [1, 0])
        np.testing.assert_array_equal(clean.base, dirty.base)

    def test_projected_score_does_not_repeat_a_remote_34_10_mode(self):
        points = np.arange(51)
        selected = set()
        for home_mean in (21, 23, 25, 27):
            for away_mean in (19, 21, 23, 25):
                home = np.exp(-0.5 * ((points - home_mean) / 7) ** 2)
                away = np.exp(-0.5 * ((points - away_mean) / 7) ** 2)
                mass = np.outer(home / home.sum(), away / away.sum()) * 0.99
                mass[34, 10] += 0.01
                before = mass.copy()
                self.assertEqual(self.distribution.top_scorelines(mass, "HOU", "CIN")[0]["home_score"], 34)
                projection = self.distribution.point_scoreline(mass, "HOU", "CIN")
                self.assertLessEqual(abs(projection["home_score"] - home_mean), 1)
                self.assertLessEqual(abs(projection["away_score"] - away_mean), 1)
                selected.add((projection["home_score"], projection["away_score"]))
                self.assertEqual(projection["probability"], mass[projection["home_score"], projection["away_score"]])
                np.testing.assert_array_equal(before, mass)
        self.assertEqual(len(selected), 16)

    def test_point_projection_matches_independent_absolute_loss_oracle(self):
        rng = np.random.default_rng(2026)
        for _ in range(25):
            mass = rng.random((7, 7))
            mass[mass < 0.3] = 0
            mass /= mass.sum()
            projection = self.distribution.point_scoreline(mass, "AAA", "BBB")
            def loss(h, a):
                return sum(mass[x, y] * (abs(h - x) + abs(a - y)) for x in range(7) for y in range(7))
            optimum = min(loss(h, a) for h in range(7) for a in range(7) if mass[h, a] > 0)
            self.assertAlmostEqual(loss(projection["home_score"], projection["away_score"]), optimum)
            self.assertEqual(projection["method"], "minimum_expected_absolute_error")

    def test_point_projection_respects_support_postseason_and_reversal(self):
        for means, allow_ties in [((25.0, 21.0), True), ((20.0, 20.0), False), ((0.0, 27.0), False)]:
            mass = self.distribution.probabilities(*means, allow_ties=allow_ties)
            forward = self.distribution.point_scoreline(mass, "HOU", "CIN")
            reverse = self.distribution.point_scoreline(mass.T, "CIN", "HOU")
            self.assertEqual(forward["home_score"], reverse["away_score"])
            self.assertEqual(forward["away_score"], reverse["home_score"])
            self.assertEqual(forward["probability"], reverse["probability"])
            self.assertGreater(forward["probability"], 0)
            self.assertNotIn(1, (forward["home_score"], forward["away_score"]))
            if not allow_ties:
                self.assertNotEqual(forward["home_score"], forward["away_score"])
        point = self.distribution.point_scoreline(self.distribution.probabilities(0, 0), "HOU", "CIN")
        self.assertEqual((point["home_score"], point["away_score"], point["probability"]), (0, 0, 1))


if __name__ == "__main__":
    unittest.main()
