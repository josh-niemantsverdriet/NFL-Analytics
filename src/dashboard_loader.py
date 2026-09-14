import math

import polars as pl

GAME_COLUMNS = (
    "game_id",
    "season",
    "game_type",
    "week",
    "gameday",
    "gametime",
    "away_team",
    "away_score",
    "home_team",
    "home_score",
    "location",
    "result",
    "total",
    "overtime",
    "roof",
    "surface",
    "temp",
    "wind",
    "stadium",
)

PLAYER_COLUMNS = (
    "game_id",
    "player_id",
    "season",
    "week",
    "player_name",
    "player_display_name",
    "position",
    "team",
    "opponent_team",
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "passing_epa",
    "passing_cpoe",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_epa",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "receiving_epa",
    "fantasy_points",
    "fantasy_points_ppr",
)

ANALYTICS_COLUMNS = (
    "season",
    "snapshot_date",
    "team",
    "plays",
    "epa_per_play",
    "pass_epa_per_play",
    "rush_epa_per_play",
    "success_rate",
    "explosive_play_rate",
    "pass_rate",
    "def_plays",
    "def_epa_per_play",
    "def_pass_epa_per_play",
    "def_rush_epa_per_play",
    "def_success_rate_allowed",
    "def_explosive_play_rate_allowed",
)


def _get_connection():
    from src.database import get_connection

    return get_connection()


def rows_for_columns(
    dataframe: pl.DataFrame,
    columns: tuple[str, ...]
) -> list[tuple]:
    rows = []

    for row in dataframe.to_dicts():
        values = []

        for column in columns:
            value = row.get(column)

            if isinstance(value, float) and math.isnan(value):
                value = None

            values.append(value)

        rows.append(tuple(values))

    return rows


def _replace_rows(
    connection,
    delete_sql: str,
    delete_params: dict,
    insert_sql: str,
    rows: list[tuple]
) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(delete_sql, delete_params)

        if rows:
            cursor.executemany(insert_sql, rows)

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def refresh_games_and_players(
    season: int,
    schedules: pl.DataFrame,
    player_stats: pl.DataFrame
) -> None:
    connection = _get_connection()

    try:
        _replace_rows(
            connection,
            "DELETE FROM dbo.Games WHERE season = %(season)s",
            {"season": season},
            """
            INSERT INTO dbo.Games (
                game_id, season, game_type, week, gameday, gametime,
                away_team, away_score, home_team, home_score, location,
                result, total, overtime, roof, surface, temp, wind, stadium
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows_for_columns(schedules, GAME_COLUMNS)
        )

        _replace_rows(
            connection,
            "DELETE FROM dbo.PlayerWeeklyStats WHERE season = %(season)s",
            {"season": season},
            """
            INSERT INTO dbo.PlayerWeeklyStats (
                game_id, player_id, season, week, player_name,
                player_display_name, position, team, opponent_team,
                completions, attempts, passing_yards, passing_tds,
                passing_interceptions, passing_epa, passing_cpoe, carries,
                rushing_yards, rushing_tds, rushing_epa, receptions, targets,
                receiving_yards, receiving_tds, receiving_epa, fantasy_points,
                fantasy_points_ppr
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows_for_columns(player_stats, PLAYER_COLUMNS)
        )
    finally:
        connection.close()


def refresh_team_analytics(
    season: int,
    snapshot_date: str,
    analytics: pl.DataFrame
) -> None:
    connection = _get_connection()

    try:
        _replace_rows(
            connection,
            """
            DELETE FROM dbo.TeamAnalytics
            WHERE season = %(season)s
              AND snapshot_date = %(snapshot_date)s
            """,
                        {
                                "season": season,
                                "snapshot_date": snapshot_date
                        },
            """
            INSERT INTO dbo.TeamAnalytics (
                season, snapshot_date, team, plays, epa_per_play,
                pass_epa_per_play, rush_epa_per_play, success_rate,
                explosive_play_rate, pass_rate, def_plays, def_epa_per_play,
                def_pass_epa_per_play, def_rush_epa_per_play,
                def_success_rate_allowed, def_explosive_play_rate_allowed
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows_for_columns(analytics, ANALYTICS_COLUMNS)
        )
    finally:
        connection.close()