"""Load schedule history and serve forecasts without depending on the SQL snapshot."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

import nflreadpy as nfl
from nflreadpy.config import get_config, update_config

from src.forecast_model import POSTSEASON_GAME_TYPES, build_forecast_model, normalize_team


EASTERN = ZoneInfo("America/New_York")
CACHE_SECONDS = 3600
# nflreadpy's downloader shares one cache across loaders. Cap its duration so an
# hourly model refresh does not silently reuse yesterday's schedule, preserving
# any shorter cache duration chosen by the operator. No cached data is cleared.
update_config(cache_duration=min(get_config().cache_duration, CACHE_SECONDS))
_cache_lock = Lock()
_cached_state = None


@dataclass
class ForecastState:
    model: object
    schedules: list[dict]
    cutoff: date
    generated_at: str
    expires_at: float


def _game_date(game: dict) -> date:
    value = game["gameday"]
    return date.fromisoformat(str(value)[:10])


def _training_cutoff(now: datetime) -> date:
    # Wait until 8am ET to consume the previous day's scores, keeping late
    # night games out of training while they may still be in progress.
    local = now.astimezone(EASTERN)
    return local.date() - timedelta(days=int(local.hour < 8))


def _load_state(now: datetime) -> ForecastState:
    cutoff = _training_cutoff(now)
    # January/February belong to the season that started the previous year.
    local = now.astimezone(EASTERN)
    season = local.year - int(local.month < 3)
    seasons = list(range(season - 3, season + 1))
    schedules = nfl.load_schedules(seasons).to_dicts()
    schedules = [
        game for game in schedules
        if game.get("game_type") in {"REG", "WC", "DIV", "CON", "SB"}
        and game.get("gameday") and game.get("home_team")
        and game.get("away_team")
    ]
    completed = [
        game for game in schedules
        if _game_date(game) < cutoff
        and game.get("home_score") is not None
        and game.get("away_score") is not None
    ]
    model = build_forecast_model(completed)
    return ForecastState(
        model=model,
        schedules=schedules,
        cutoff=cutoff,
        generated_at=now.astimezone(timezone.utc).isoformat(),
        expires_at=monotonic() + CACHE_SECONDS,
    )


def get_forecast_state(now: datetime | None = None) -> ForecastState:
    global _cached_state
    now = now or datetime.now(timezone.utc)
    with _cache_lock:
        if (
            _cached_state is None
            or _cached_state.cutoff != _training_cutoff(now)
            or monotonic() >= _cached_state.expires_at
        ):
            _cached_state = _load_state(now)
        return _cached_state


def _envelope(state: ForecastState) -> dict:
    return {
        "generated_at": state.generated_at,
        "data_cutoff": state.cutoff.isoformat(),
        "model": state.model.metadata,
    }


def upcoming_forecasts(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    state = get_forecast_state(now)
    result = _envelope(state)
    result["teams"] = sorted(state.model.metadata["teams"])
    candidates = []
    seen = set()
    for game in state.schedules:
        if game.get("home_score") is not None or game.get("away_score") is not None:
            continue
        game_date = _game_date(game)
        kickoff_time = game.get("gametime")
        if kickoff_time:
            kickoff = datetime.combine(
                game_date, time.fromisoformat(str(kickoff_time)), EASTERN
            )
        else:
            # A game with an unknown start time is selectable only before its
            # date begins; never imply it is still upcoming during that day.
            kickoff = datetime.combine(game_date, time.min, EASTERN)
        if kickoff <= now:
            continue
        home, away = normalize_team(game["home_team"]), normalize_team(game["away_team"])
        if home not in result["teams"] or away not in result["teams"]:
            continue
        key = (game_date, home, away)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((kickoff, game | {"home_team": home, "away_team": away}))

    result["games"] = []
    for _, game in sorted(candidates, key=lambda entry: (entry[0], entry[1]["home_team"]))[:16]:
        neutral = str(game.get("location") or "Home").strip().lower() == "neutral"
        result["games"].append({
            "game_id": game.get("game_id") or (
                f"{_game_date(game)}-{game['away_team']}-{game['home_team']}"
            ),
            "season": game["season"],
            "week": game["week"],
            "date": _game_date(game).isoformat(),
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "neutral": neutral,
            "forecast": state.model.predict(
                game["home_team"], game["away_team"], neutral=neutral,
                allow_ties=game.get("game_type") not in POSTSEASON_GAME_TYPES,
            ),
        })
    return result


def matchup_forecast(home_team: str, away_team: str, neutral: bool) -> dict:
    state = get_forecast_state()
    result = _envelope(state)
    result["forecast"] = state.model.predict(home_team, away_team, neutral=neutral)
    return result
