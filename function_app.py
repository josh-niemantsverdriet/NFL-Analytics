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