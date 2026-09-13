import json
import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

import azure.functions as func

from src import forecast_routes as routes
from src import forecast_service as service


def game(game_id, gameday, **overrides):
    result = {
        "game_id": game_id, "season": 2026, "week": 1,
        "gameday": gameday, "gametime": "13:00", "game_type": "REG",
        "home_team": "BUF", "away_team": "MIA", "location": "Home",
        "home_score": None, "away_score": None,
    }
    return result | overrides


class ForecastServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 13, 16, tzinfo=timezone.utc)
        self.model = Mock()
        self.model.metadata = {"teams": ["BUF", "MIA"], "training_games": 40}
        self.model.predict.return_value = {"home_score": 24.0, "away_score": 21.0}

    def test_training_excludes_same_day_future_incomplete_and_preseason_games(self):
        rows = [
            game("past", "2026-09-10", home_score=21, away_score=14),
            game("same-day", "2026-09-13", home_score=10, away_score=7),
            game("future", "2026-09-20", home_score=28, away_score=14),
            game("partial", "2026-09-11", home_score=7),
            game("preseason", "2026-08-20", game_type="PRE", home_score=3, away_score=0),
        ]
        with patch.object(service.nfl, "load_schedules") as load, patch.object(
            service, "build_forecast_model", return_value=self.model
        ) as build:
            load.return_value.to_dicts.return_value = rows
            state = service._load_state(self.now)
        load.assert_called_once_with([2023, 2024, 2025, 2026])
        self.assertEqual([row["game_id"] for row in build.call_args.args[0]], ["past"])
        self.assertEqual(state.cutoff, date(2026, 9, 13))

    def test_january_uses_previous_season_and_waits_for_late_games(self):
        now = datetime(2027, 1, 11, 6, tzinfo=timezone.utc)  # 1am ET
        with patch.object(service.nfl, "load_schedules") as load, patch.object(
            service, "build_forecast_model", return_value=self.model
        ):
            load.return_value.to_dicts.return_value = []
            state = service._load_state(now)
        load.assert_called_once_with([2023, 2024, 2025, 2026])
        self.assertEqual(state.cutoff, date(2027, 1, 10))

    def test_upcoming_omits_started_scored_unknown_and_duplicate_fixtures(self):
        upcoming = game("upcoming", "2026-09-13", location="Neutral")
        rows = [
            upcoming, upcoming.copy(),
            game("started", "2026-09-13", gametime="11:00"),
            game("scored", "2026-09-13", home_score=0),
            game("unknown-time", "2026-09-13", gametime=None),
            game("unknown-team", "2026-09-14", home_team="ZZZ"),
            game("tomorrow", "2026-09-14", gametime=None),
        ]
        state = service.ForecastState(self.model, rows, date(2026, 9, 13), "test", 100)
        with patch.object(service, "get_forecast_state", return_value=state):
            data = service.upcoming_forecasts(self.now)
        self.assertEqual([row["game_id"] for row in data["games"]], ["upcoming", "tomorrow"])
        self.assertTrue(data["games"][0]["neutral"])
        self.model.predict.assert_any_call("BUF", "MIA", neutral=True)

    def test_cache_reuses_model_but_invalidates_at_daily_cutoff_and_expiry(self):
        state = service.ForecastState(self.model, [], date(2026, 9, 13), "test", 200)
        with patch.object(service, "_cached_state", None), patch.object(
            service, "_load_state", return_value=state
        ) as load, patch.object(service, "monotonic", return_value=100):
            service.get_forecast_state(self.now)
            service.get_forecast_state(self.now)
            self.assertEqual(load.call_count, 1)
            service.get_forecast_state(datetime(2026, 9, 14, 16, tzinfo=timezone.utc))
            self.assertEqual(load.call_count, 2)
        with patch.object(service, "_cached_state", state), patch.object(
            service, "_load_state", return_value=state
        ) as load, patch.object(service, "monotonic", return_value=201):
            service.get_forecast_state(self.now)
            load.assert_called_once()

    def test_upcoming_normalizes_franchise_aliases_and_venue(self):
        self.model.metadata["teams"] = ["BUF", "LA"]
        rows = [game("alias", "2026-09-14", home_team="LAR", away_team="BUF", location=" neutral ")]
        state = service.ForecastState(self.model, rows, date(2026, 9, 13), "test", 100)
        with patch.object(service, "get_forecast_state", return_value=state):
            data = service.upcoming_forecasts(self.now)
        self.assertEqual(data["games"][0]["home_team"], "LA")
        self.model.predict.assert_called_once_with("LA", "BUF", neutral=True)


class ForecastRouteTests(unittest.TestCase):
    def request(self, **params):
        return func.HttpRequest("GET", "http://localhost/api/forecast", params=params, body=b"")

    def test_valid_request_normalizes_teams_and_returns_json(self):
        payload = {"forecast": {"home_score": 24.5}}
        with patch.object(routes, "matchup_forecast", return_value=payload) as predict:
            response = routes.forecast(self.request(home_team=" buf ", away_team="mia", neutral="true"))
        predict.assert_called_once_with("BUF", "MIA", True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.get_body()), payload)

    def test_invalid_inputs_never_load_model(self):
        inputs = [
            {}, {"home_team": "BUF", "away_team": "BUF"},
            {"home_team": "BUF", "away_team": "MIA", "neutral": "maybe"},
            {"home_team": "BUF;", "away_team": "MIA"},
        ]
        with patch.object(routes, "matchup_forecast") as predict:
            for params in inputs:
                with self.subTest(params=params):
                    self.assertEqual(routes.forecast(self.request(**params)).status_code, 400)
            predict.assert_not_called()

    def test_download_failure_returns_retryable_error_without_exception_details(self):
        with patch.object(routes, "upcoming_forecasts", side_effect=RuntimeError("private detail")), patch.object(
            routes.logging, "exception"
        ):
            response = routes.forecasts(self.request())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private detail", response.get_body().decode())


if __name__ == "__main__":
    unittest.main()
