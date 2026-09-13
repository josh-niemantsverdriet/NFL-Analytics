import json
from datetime import datetime, timezone

import azure.functions as func

from src.azure_storage import upload_dataframe
from src.nfl_data import load_nfl_datasets

from src.analytics import calculate_team_analytics
from src.azure_storage import (
    download_dataframe,
    upload_dataframe
)

from src.database import get_connection


app = func.FunctionApp(
    http_auth_level=func.AuthLevel.FUNCTION
)


@app.route(
    route="ingest",
    methods=["POST"]
)
def ingest(req: func.HttpRequest) -> func.HttpResponse:

    try:
        # Allow season to be supplied either as:
        # ?season=2026
        # or {"season": 2026}

        season = req.params.get("season")

        if season is None:
            try:
                body = req.get_json()
                season = body.get("season")
            except ValueError:
                pass

        if season is None:
            season = datetime.now(timezone.utc).year

        season = int(season)

        snapshot_date = datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")

        print(
            f"Starting NFL ingestion for season {season}"
        )

        datasets = load_nfl_datasets(season)

        results = {}

        for dataset_name, dataframe in datasets.items():

            blob_name = (
                f"season={season}/"
                f"snapshot_date={snapshot_date}/"
                f"{dataset_name}.parquet"
            )

            upload_dataframe(
                dataframe,
                blob_name
            )

            results[dataset_name] = {
                "rows": dataframe.height,
                "columns": dataframe.width,
                "blob": blob_name
            }

        response = {
            "success": True,
            "season": season,
            "snapshot_date": snapshot_date,
            "datasets": results
        }

        return func.HttpResponse(
            json.dumps(response),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:

        print(f"Ingestion failed: {error}")

        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(error)
            }),
            mimetype="application/json",
            status_code=500
        )

@app.route(
    route="analyze",
    methods=["POST"]
)
def analyze(req: func.HttpRequest) -> func.HttpResponse:

    try:
        body = req.get_json()

        season = int(body["season"])
        snapshot_date = body["snapshot_date"]

        play_by_play_blob = (
            f"season={season}/"
            f"snapshot_date={snapshot_date}/"
            f"play_by_play.parquet"
        )

        print(
            f"Loading play-by-play from "
            f"{play_by_play_blob}"
        )

        play_by_play = download_dataframe(
            play_by_play_blob
        )

        analytics = calculate_team_analytics(
            play_by_play,
            season,
            snapshot_date
        )

        output_blob = (
            f"season={season}/"
            f"snapshot_date={snapshot_date}/"
            f"team_analytics.parquet"
        )

        upload_dataframe(
            analytics,
            output_blob
        )

        response = {
            "success": True,
            "season": season,
            "snapshot_date": snapshot_date,
            "teams": analytics.height,
            "blob": output_blob
        }

        return func.HttpResponse(
            json.dumps(response),
            mimetype="application/json",
            status_code=200
        )

    except Exception as error:

        print(f"Analytics failed: {error}")

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

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                USER_NAME() AS connected_user,
                COUNT(*) AS team_analytics_rows
            FROM dbo.TeamAnalytics
        """)

        row = cursor.fetchone()

        cursor.close()
        connection.close()

        response = {
            "success": True,
            "connected_user": row[0],
            "team_analytics_rows": row[1]
        }

        return func.HttpResponse(
            json.dumps(response),
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
    route="team-analytics",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def team_analytics(req: func.HttpRequest) -> func.HttpResponse:

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
                pass_rate
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
                "snapshot_date": row[1].isoformat(),
                "team": row[2],
                "plays": row[3],
                "epa_per_play": row[4],
                "pass_epa_per_play": row[5],
                "rush_epa_per_play": row[6],
                "success_rate": row[7],
                "explosive_play_rate": row[8],
                "pass_rate": row[9]
            })

        cursor.close()
        connection.close()

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

@app.route(
    route="dashboard",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def dashboard(req: func.HttpRequest) -> func.HttpResponse:
    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Latest analytics snapshot
        cursor.execute("""
            SELECT TOP 1
                season,
                snapshot_date
            FROM dbo.TeamAnalytics
            ORDER BY snapshot_date DESC, season DESC
        """)

        snapshot = cursor.fetchone()

        if snapshot is None:
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

        # Top offenses
        cursor.execute("""
            SELECT TOP 5
                team,
                plays,
                epa_per_play,
                success_rate,
                pass_epa_per_play,
                rush_epa_per_play
            FROM dbo.TeamAnalytics
            WHERE snapshot_date = (
                SELECT MAX(snapshot_date)
                FROM dbo.TeamAnalytics
            )
            ORDER BY epa_per_play DESC
        """)

        top_offenses = []

        for index, row in enumerate(cursor.fetchall()):
            top_offenses.append({
                "rank": index + 1,
                "team": row[0],
                "plays": row[1],
                "epa_per_play": row[2],
                "success_rate": row[3],
                "pass_epa_per_play": row[4],
                "rush_epa_per_play": row[5]
            })

        # Passing leaders
        cursor.execute("""
            SELECT TOP 5
                player_id,
                MAX(player_display_name) AS player_name,
                MAX(team) AS team,
                SUM(passing_yards) AS yards,
                SUM(passing_tds) AS touchdowns
            FROM dbo.PlayerWeeklyStats
            WHERE season = (
                SELECT MAX(season)
                FROM dbo.PlayerWeeklyStats
            )
            GROUP BY player_id
            HAVING SUM(passing_yards) > 0
            ORDER BY yards DESC
        """)

        passing = []

        for index, row in enumerate(cursor.fetchall()):
            passing.append({
                "rank": index + 1,
                "player_id": row[0],
                "player_name": row[1],
                "team": row[2],
                "yards": row[3],
                "touchdowns": row[4]
            })

        # Rushing leaders
        cursor.execute("""
            SELECT TOP 5
                player_id,
                MAX(player_display_name) AS player_name,
                MAX(team) AS team,
                SUM(rushing_yards) AS yards,
                SUM(rushing_tds) AS touchdowns
            FROM dbo.PlayerWeeklyStats
            WHERE season = (
                SELECT MAX(season)
                FROM dbo.PlayerWeeklyStats
            )
            GROUP BY player_id
            HAVING SUM(rushing_yards) > 0
            ORDER BY yards DESC
        """)

        rushing = []

        for index, row in enumerate(cursor.fetchall()):
            rushing.append({
                "rank": index + 1,
                "player_id": row[0],
                "player_name": row[1],
                "team": row[2],
                "yards": row[3],
                "touchdowns": row[4]
            })

        # Receiving leaders
        cursor.execute("""
            SELECT TOP 5
                player_id,
                MAX(player_display_name) AS player_name,
                MAX(team) AS team,
                SUM(receiving_yards) AS yards,
                SUM(receiving_tds) AS touchdowns
            FROM dbo.PlayerWeeklyStats
            WHERE season = (
                SELECT MAX(season)
                FROM dbo.PlayerWeeklyStats
            )
            GROUP BY player_id
            HAVING SUM(receiving_yards) > 0
            ORDER BY yards DESC
        """)

        receiving = []

        for index, row in enumerate(cursor.fetchall()):
            receiving.append({
                "rank": index + 1,
                "player_id": row[0],
                "player_name": row[1],
                "team": row[2],
                "yards": row[3],
                "touchdowns": row[4]
            })

        # Recent completed games
        cursor.execute("""
            SELECT TOP 6
                week,
                gameday,
                away_team,
                away_score,
                home_team,
                home_score
            FROM dbo.Games
            WHERE season = (
                SELECT MAX(season)
                FROM dbo.Games
            )
              AND away_score IS NOT NULL
              AND home_score IS NOT NULL
            ORDER BY gameday DESC, gametime DESC
        """)

        recent_games = []

        for row in cursor.fetchall():
            recent_games.append({
                "week": row[0],
                "date": row[1].isoformat() if row[1] else None,
                "away_team": row[2],
                "away_score": row[3],
                "home_team": row[4],
                "home_score": row[5]
            })

        cursor.close()

        response = {
            "season": season,
            "snapshot_date": snapshot_date.isoformat(),
            "top_offenses": top_offenses,
            "leaders": {
                "passing": passing,
                "rushing": rushing,
                "receiving": receiving
            },
            "recent_games": recent_games
        }

        return func.HttpResponse(
            json.dumps(response),
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