from datetime import datetime, timezone
from pathlib import Path
from azure_storage import upload_file

import nflreadpy as nfl
import polars as pl


SEASON = 2026
RAW_DATA_DIR = Path("data/raw")


def save_dataset(
    dataframe: pl.DataFrame,
    dataset_name: str,
    snapshot_date: str
) -> None:
    output_directory = (
        RAW_DATA_DIR
        / f"season={SEASON}"
        / f"snapshot_date={snapshot_date}"
    )

    output_directory.mkdir(parents=True, exist_ok=True)

    output_file = output_directory / f"{dataset_name}.parquet"

    dataframe.write_parquet(
    output_file,
    compression="snappy"
)

    print(
        f"Saved {dataset_name}: "
        f"{dataframe.height:,} rows x "
        f"{dataframe.width:,} columns -> "
        f"{output_file}"
    )

    blob_name = (
        f"season={SEASON}/"
        f"snapshot_date={snapshot_date}/"
        f"{dataset_name}.parquet"
    )

    upload_file(
        output_file,
        blob_name
    )


def print_dataset_summary(
    dataframe: pl.DataFrame,
    dataset_name: str
) -> None:
    print(f"\n{'=' * 60}")
    print(dataset_name.upper())
    print(f"{'=' * 60}")

    print(f"Rows: {dataframe.height:,}")
    print(f"Columns: {dataframe.width:,}")

    print("\nColumn names:")
    for column in dataframe.columns:
        print(f"  - {column}")

    print("\nFirst 5 rows:")
    print(dataframe.head(5))


def main() -> None:
    print(f"Starting NFL ingestion for the {SEASON} season...")

    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("\nDownloading schedules...")
    schedules = nfl.load_schedules([SEASON])

    print("Downloading player statistics...")
    player_stats = nfl.load_player_stats(
        [SEASON],
        summary_level="week"
    )

    print("Downloading team statistics...")
    team_stats = nfl.load_team_stats(
        [SEASON],
        summary_level="week"
    )

    print("Downloading play-by-play...")
    play_by_play = nfl.load_pbp([SEASON])

    datasets = {
        "schedules": schedules,
        "player_stats": player_stats,
        "team_stats": team_stats,
        "play_by_play": play_by_play,
    }

    for dataset_name, dataframe in datasets.items():
        print_dataset_summary(dataframe, dataset_name)

        save_dataset(
            dataframe,
            dataset_name,
            snapshot_date
        )

    print("\nNFL ingestion completed successfully.")


if __name__ == "__main__":
    main()