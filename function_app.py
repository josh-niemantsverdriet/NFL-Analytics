import json
from datetime import datetime, timezone

import azure.functions as func

from src.analytics import calculate_team_analytics
from src.azure_storage import download_dataframe, upload_dataframe
from src.database import get_connection
from src.nfl_data import load_nfl_datasets


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="ingest", methods=["POST"])
def ingest(req: func.HttpRequest) -> func.HttpResponse:
    try:
        season_value = req.params.get("season")

        if not season_value:
            try:
                body = req.get_json()
                season_value = body.get("season")
            except ValueError:
                season_value = None

        if season_value:
            season = int(season_value)
        else:
            season = datetime.now(timezone.utc).year

        snapshot_date = datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")

        datasets = load_nfl_datasets(season)

        uploaded_datasets = {}

        for dataset_name, dataframe in datasets.items():
            blob_name = (
                f"season={season}/"
                f"snapshot_date={snapshot_date}/"
                f"{dataset_name}.parquet"
            )

            upload_dataframe(
                dataframe=dataframe,
                blob_name=blob_name
            )

            uploaded_datasets[dataset_name] = {
                "rows": dataframe.height,
                "columns": dataframe.width,
                "blob": blob_name
            }

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "season": season,
                "snapshot_date": snapshot_date,
                "datasets": uploaded_datasets
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="analyze", methods=["POST"])
def analyze(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()

        season = int(body["season"])
        snapshot_date = body["snapshot_date"]

        pbp_blob = (
            f"season={season}/"
            f"snapshot_date={snapshot_date}/"
            "play_by_play.parquet"
        )

        play_by_play = download_dataframe(
            pbp_blob
        )

        analytics = calculate_team_analytics(
            play_by_play=play_by_play,
            season=season,
            snapshot_date=snapshot_date
        )

        output_blob = (
            f"season={season}/"
            f"snapshot_date={snapshot_date}/"
            "team_analytics.parquet"
        )

        upload_dataframe(
            dataframe=analytics,
            blob_name=output_blob
        )

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "season": season,
                "snapshot_date": snapshot_date,
                "teams": analytics.height,
                "blob": output_blob
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(
    route="sql-test",
    methods=["GET"]
)
def sql_test(req: func.HttpRequest) -> func.HttpResponse:
    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                USER_NAME(),
                (
                    SELECT COUNT(*)
                    FROM dbo.TeamAnalytics
                )
        """)

        row = cursor.fetchone()

        cursor.close()

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "connected_user": row[0],
                "team_analytics_rows": row[1]
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )

    finally:
        if connection:
            connection.close()


@app.route(
    route="team-analytics",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def team_analytics(
    req: func.HttpRequest
) -> func.HttpResponse:
    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                season,
                snapshot_date,
                team,

                plays,
                epa_per_play,
                pass_epa_per_play,
                rush_epa_per_play,
                success_rate,
                explosive_play_rate,
                pass_rate,

                def_plays,
                def_epa_per_play,
                def_pass_epa_per_play,
                def_rush_epa_per_play,
                def_success_rate_allowed,
                def_explosive_play_rate_allowed

            FROM dbo.TeamAnalytics

            WHERE snapshot_date = (
                SELECT MAX(snapshot_date)
                FROM dbo.TeamAnalytics
            )

            ORDER BY epa_per_play DESC
        """)

        rows = cursor.fetchall()

        results = []

        for row in rows:
            results.append({
                "season": row[0],
                "snapshot_date": (
                    row[1].isoformat()
                    if row[1]
                    else None
                ),
                "team": row[2],

                "plays": row[3],
                "epa_per_play": row[4],
                "pass_epa_per_play": row[5],
                "rush_epa_per_play": row[6],
                "success_rate": row[7],
                "explosive_play_rate": row[8],
                "pass_rate": row[9],

                "def_plays": row[10],
                "def_epa_per_play": row[11],
                "def_pass_epa_per_play": row[12],
                "def_rush_epa_per_play": row[13],
                "def_success_rate_allowed": row[14],
                "def_explosive_play_rate_allowed": row[15]
            })

        cursor.close()

        return func.HttpResponse(
            json.dumps(results),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )

    finally:
        if connection:
            connection.close()


@app.route(
    route="dashboard",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def dashboard(
    req: func.HttpRequest
) -> func.HttpResponse:
    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT TOP 1
                season,
                snapshot_date
            FROM dbo.TeamAnalytics
            ORDER BY
                snapshot_date DESC,
                season DESC
        """)

        snapshot = cursor.fetchone()

        if snapshot is None:
            cursor.close()

            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "No analytics data found."
                }),
                mimetype="application/json",
                status_code=404
            )

        season = snapshot[0]
        snapshot_date = snapshot[1]

        cursor.execute("""
            SELECT TOP 5
                team,
                plays,
                epa_per_play,
                success_rate,
                pass_epa_per_play,
                rush_epa_per_play
            FROM dbo.TeamAnalytics
            WHERE season = %(season)s
              AND snapshot_date = %(snapshot_date)s
            ORDER BY epa_per_play DESC
        """, {
            "season": season,
            "snapshot_date": snapshot_date
        })

        top_offenses = []

        for index, row in enumerate(
            cursor.fetchall()
        ):
            top_offenses.append({
                "rank": index + 1,
                "team": row[0],
                "plays": row[1],
                "epa_per_play": row[2],
                "success_rate": row[3],
                "pass_epa_per_play": row[4],
                "rush_epa_per_play": row[5]
            })

        cursor.execute("""
            SELECT TOP 5
                player_id,
                MAX(player_display_name),
                MAX(team),
                SUM(passing_yards),
                SUM(passing_tds)
            FROM dbo.PlayerWeeklyStats
            WHERE season = %(season)s
            GROUP BY player_id
            HAVING SUM(passing_yards) > 0
            ORDER BY SUM(passing_yards) DESC
        """, {
            "season": season
        })

        passing = []

        for index, row in enumerate(
            cursor.fetchall()
        ):
            passing.append({
                "rank": index + 1,
                "player_id": row[0],
                "player_name": row[1],
                "team": row[2],
                "yards": row[3],
                "touchdowns": row[4]
            })

        cursor.execute("""
            SELECT TOP 5
                player_id,
                MAX(player_display_name),
                MAX(team),
                SUM(rushing_yards),
                SUM(rushing_tds)
            FROM dbo.PlayerWeeklyStats
            WHERE season = %(season)s
            GROUP BY player_id
            HAVING SUM(rushing_yards) > 0
            ORDER BY SUM(rushing_yards) DESC
        """, {
            "season": season
        })

        rushing = []

        for index, row in enumerate(
            cursor.fetchall()
        ):
            rushing.append({
                "rank": index + 1,
                "player_id": row[0],
                "player_name": row[1],
                "team": row[2],
                "yards": row[3],
                "touchdowns": row[4]
            })

        cursor.execute("""
            SELECT TOP 5
                player_id,
                MAX(player_display_name),
                MAX(team),
                SUM(receiving_yards),
                SUM(receiving_tds)
            FROM dbo.PlayerWeeklyStats
            WHERE season = %(season)s
            GROUP BY player_id
            HAVING SUM(receiving_yards) > 0
            ORDER BY SUM(receiving_yards) DESC
        """, {
            "season": season
        })

        receiving = []

        for index, row in enumerate(
            cursor.fetchall()
        ):
            receiving.append({
                "rank": index + 1,
                "player_id": row[0],
                "player_name": row[1],
                "team": row[2],
                "yards": row[3],
                "touchdowns": row[4]
            })

        cursor.execute("""
            SELECT TOP 6
                week,
                gameday,
                away_team,
                away_score,
                home_team,
                home_score
            FROM dbo.Games
            WHERE season = %(season)s
              AND away_score IS NOT NULL
              AND home_score IS NOT NULL
            ORDER BY
                gameday DESC,
                gametime DESC
        """, {
            "season": season
        })

        recent_games = []

        for row in cursor.fetchall():
            recent_games.append({
                "week": row[0],
                "date": (
                    row[1].isoformat()
                    if row[1]
                    else None
                ),
                "away_team": row[2],
                "away_score": row[3],
                "home_team": row[4],
                "home_score": row[5]
            })

        cursor.close()

        return func.HttpResponse(
            json.dumps({
                "season": season,
                "snapshot_date": (
                    snapshot_date.isoformat()
                ),
                "top_offenses": top_offenses,
                "leaders": {
                    "passing": passing,
                    "rushing": rushing,
                    "receiving": receiving
                },
                "recent_games": recent_games
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )

    finally:
        if connection:
            connection.close()


@app.route(
    route="matchup",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def matchup(
    req: func.HttpRequest
) -> func.HttpResponse:
    connection = None

    try:
        team1 = (
            req.params.get("team1") or ""
        ).strip().upper()

        team2 = (
            req.params.get("team2") or ""
        ).strip().upper()

        if not team1 or not team2:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": (
                        "team1 and team2 are required."
                    )
                }),
                mimetype="application/json",
                status_code=400
            )

        if team1 == team2:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": (
                        "Choose two different teams."
                    )
                }),
                mimetype="application/json",
                status_code=400
            )

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT TOP 1
                season,
                snapshot_date
            FROM dbo.TeamAnalytics
            ORDER BY
                snapshot_date DESC,
                season DESC
        """)

        snapshot = cursor.fetchone()

        if snapshot is None:
            cursor.close()

            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": (
                        "No team analytics data found."
                    )
                }),
                mimetype="application/json",
                status_code=404
            )

        season = snapshot[0]
        snapshot_date = snapshot[1]

        cursor.execute("""
            SELECT
                season,
                snapshot_date,
                team,

                plays,
                epa_per_play,
                pass_epa_per_play,
                rush_epa_per_play,
                success_rate,
                explosive_play_rate,
                pass_rate,

                def_plays,
                def_epa_per_play,
                def_pass_epa_per_play,
                def_rush_epa_per_play,
                def_success_rate_allowed,
                def_explosive_play_rate_allowed

            FROM dbo.TeamAnalytics

            WHERE season = %(season)s
              AND snapshot_date = %(snapshot_date)s
              AND team IN (
                  %(team1)s,
                  %(team2)s
              )
        """, {
            "season": season,
            "snapshot_date": snapshot_date,
            "team1": team1,
            "team2": team2
        })

        rows = cursor.fetchall()

        teams = {}

        for row in rows:
            teams[row[2]] = {
                "season": row[0],
                "snapshot_date": (
                    row[1].isoformat()
                    if row[1]
                    else None
                ),
                "team": row[2],

                "plays": row[3],
                "epa_per_play": row[4],
                "pass_epa_per_play": row[5],
                "rush_epa_per_play": row[6],
                "success_rate": row[7],
                "explosive_play_rate": row[8],
                "pass_rate": row[9],

                "def_plays": row[10],
                "def_epa_per_play": row[11],
                "def_pass_epa_per_play": row[12],
                "def_rush_epa_per_play": row[13],
                "def_success_rate_allowed": row[14],
                "def_explosive_play_rate_allowed": row[15]
            }

        cursor.close()

        missing_teams = []

        if team1 not in teams:
            missing_teams.append(team1)

        if team2 not in teams:
            missing_teams.append(team2)

        if missing_teams:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": (
                        "No analytics found for: "
                        + ", ".join(missing_teams)
                    )
                }),
                mimetype="application/json",
                status_code=404
            )

        team1_data = teams[team1]
        team2_data = teams[team2]

        def average_metric(
            first_value,
            second_value
        ):
            if (
                first_value is None
                or second_value is None
            ):
                return None

            return (
                first_value
                + second_value
            ) / 2

        team1_projection = {
            "team": team1,
            "opponent": team2,

            "expected_epa_per_play":
                average_metric(
                    team1_data[
                        "epa_per_play"
                    ],
                    team2_data[
                        "def_epa_per_play"
                    ]
                ),

            "expected_pass_epa_per_play":
                average_metric(
                    team1_data[
                        "pass_epa_per_play"
                    ],
                    team2_data[
                        "def_pass_epa_per_play"
                    ]
                ),

            "expected_rush_epa_per_play":
                average_metric(
                    team1_data[
                        "rush_epa_per_play"
                    ],
                    team2_data[
                        "def_rush_epa_per_play"
                    ]
                ),

            "expected_success_rate":
                average_metric(
                    team1_data[
                        "success_rate"
                    ],
                    team2_data[
                        "def_success_rate_allowed"
                    ]
                ),

            "expected_explosive_rate":
                average_metric(
                    team1_data[
                        "explosive_play_rate"
                    ],
                    team2_data[
                        "def_explosive_play_rate_allowed"
                    ]
                )
        }

        team2_projection = {
            "team": team2,
            "opponent": team1,

            "expected_epa_per_play":
                average_metric(
                    team2_data[
                        "epa_per_play"
                    ],
                    team1_data[
                        "def_epa_per_play"
                    ]
                ),

            "expected_pass_epa_per_play":
                average_metric(
                    team2_data[
                        "pass_epa_per_play"
                    ],
                    team1_data[
                        "def_pass_epa_per_play"
                    ]
                ),

            "expected_rush_epa_per_play":
                average_metric(
                    team2_data[
                        "rush_epa_per_play"
                    ],
                    team1_data[
                        "def_rush_epa_per_play"
                    ]
                ),

            "expected_success_rate":
                average_metric(
                    team2_data[
                        "success_rate"
                    ],
                    team1_data[
                        "def_success_rate_allowed"
                    ]
                ),

            "expected_explosive_rate":
                average_metric(
                    team2_data[
                        "explosive_play_rate"
                    ],
                    team1_data[
                        "def_explosive_play_rate_allowed"
                    ]
                )
        }

        team1_expected = (
            team1_projection[
                "expected_epa_per_play"
            ]
        )

        team2_expected = (
            team2_projection[
                "expected_epa_per_play"
            ]
        )

        advantage_team = None
        advantage_size = None

        if (
            team1_expected is not None
            and team2_expected is not None
        ):
            difference = (
                team1_expected
                - team2_expected
            )

            advantage_size = abs(difference)

            if abs(difference) < 0.001:
                advantage_team = "EVEN"
            elif difference > 0:
                advantage_team = team1
            else:
                advantage_team = team2

        return func.HttpResponse(
            json.dumps({
                "season": season,
                "snapshot_date": (
                    snapshot_date.isoformat()
                ),

                "team1": team1_data,
                "team2": team2_data,

                "team1_projection":
                    team1_projection,

                "team2_projection":
                    team2_projection,

                "matchup_advantage": {
                    "team": advantage_team,
                    "epa_per_play_edge":
                        advantage_size
                },

                "method": (
                    "Projected matchup metrics "
                    "are a simple average of "
                    "the offense's metric and "
                    "the opposing defense's "
                    "corresponding metric allowed."
                )
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )

    finally:
        if connection:
            connection.close()