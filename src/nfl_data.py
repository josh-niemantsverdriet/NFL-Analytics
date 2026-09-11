import nflreadpy as nfl


def load_nfl_datasets(season: int) -> dict:
    return {
        "schedules": nfl.load_schedules([season]),

        "player_stats": nfl.load_player_stats(
            [season],
            summary_level="week"
        ),

        "team_stats": nfl.load_team_stats(
            [season],
            summary_level="week"
        ),

        "play_by_play": nfl.load_pbp([season]),
    }