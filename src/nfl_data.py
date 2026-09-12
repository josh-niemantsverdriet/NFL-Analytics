import nflreadpy as nfl
import polars as pl


def load_nfl_datasets(season: int) -> dict:
    schedules = nfl.load_schedules([season])

    player_stats = nfl.load_player_stats(
        [season],
        summary_level="week"
    )

    player_stats = player_stats.filter(
        pl.col("player_id").is_not_null()
        & pl.col("game_id").is_not_null()
    )

    team_stats = nfl.load_team_stats(
        [season],
        summary_level="week"
    )

    play_by_play = nfl.load_pbp([season])

    return {
        "schedules": schedules,
        "player_stats": player_stats,
        "team_stats": team_stats,
        "play_by_play": play_by_play,
    }