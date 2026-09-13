"""Public, read-only endpoints for the game forecast page."""

import json
import logging

import azure.functions as func

from src.forecast_model import ForecastDataError
from src.forecast_service import matchup_forecast, upcoming_forecasts


forecast_blueprint = func.Blueprint()


def _response(data: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(data, allow_nan=False),
        mimetype="application/json",
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


@forecast_blueprint.route(
    route="forecasts", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS
)
def forecasts(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _response(upcoming_forecasts())
    except ForecastDataError as error:
        return _response({"error": str(error)}, 503)
    except Exception:
        logging.exception("Could not load game forecasts")
        return _response({
            "error": "Forecast history is temporarily unavailable. Please try again."
        }, 503)


@forecast_blueprint.route(
    route="forecast", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS
)
def forecast(req: func.HttpRequest) -> func.HttpResponse:
    home = (req.params.get("home_team") or "").strip().upper()
    away = (req.params.get("away_team") or "").strip().upper()
    neutral_value = (req.params.get("neutral") or "false").strip().lower()
    if not home or not away or home == away:
        return _response({"error": "Choose two different teams."}, 400)
    if not (home.isascii() and away.isascii() and home.isalpha() and away.isalpha()
            and 2 <= len(home) <= 3 and 2 <= len(away) <= 3):
        return _response({"error": "Use valid NFL team abbreviations."}, 400)
    if neutral_value not in {"true", "false"}:
        return _response({"error": "neutral must be true or false."}, 400)
    try:
        return _response(matchup_forecast(home, away, neutral_value == "true"))
    except ForecastDataError as error:
        return _response({"error": str(error)}, 422)
    except ValueError as error:
        return _response({"error": str(error)}, 400)
    except Exception:
        logging.exception("Could not project matchup")
        return _response({
            "error": "Forecast history is temporarily unavailable. Please try again."
        }, 503)
