"""Reproduce a chronological forecast evaluation from a schedule snapshot."""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import polars as pl

from src.forecast_model import build_forecast_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedules", type=Path, required=True, help="nflverse schedule parquet")
    parser.add_argument("--before", type=date.fromisoformat, required=True, help="Exclusive YYYY-MM-DD cutoff")
    args = parser.parse_args()
    rows = pl.read_parquet(args.schedules).to_dicts()
    games = [
        game for game in rows
        if game.get("game_type") in {"REG", "WC", "DIV", "CON", "SB"}
        and game.get("gameday")
        and date.fromisoformat(str(game["gameday"])[:10]) < args.before
        and game.get("home_score") is not None
        and game.get("away_score") is not None
    ]
    model = build_forecast_model(games)
    print(json.dumps({
        "snapshot_sha256": hashlib.sha256(args.schedules.read_bytes()).hexdigest(),
        "data_cutoff": args.before.isoformat(),
        "model": model.metadata,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
