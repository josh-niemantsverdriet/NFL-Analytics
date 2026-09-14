import unittest
from datetime import date
from unittest.mock import Mock, patch

import polars as pl

from src.dashboard_loader import (
    ANALYTICS_COLUMNS,
    rows_for_columns,
    refresh_team_analytics,
)


class DashboardLoaderTests(unittest.TestCase):
    def test_rows_for_columns_preserves_order_and_normalizes_missing_values(self):
        dataframe = pl.DataFrame({
            "game_id": ["game-1"],
            "season": [2026],
            "score": [float("nan")],
        })

        self.assertEqual(
            rows_for_columns(dataframe, ("game_id", "score", "missing")),
            [("game-1", None, None)]
        )

    @patch("src.dashboard_loader._get_connection")
    def test_refresh_team_analytics_replaces_snapshot_rows(self, get_connection):
        cursor = Mock()
        connection = Mock()
        connection.cursor.return_value = cursor
        get_connection.return_value = connection

        analytics = pl.DataFrame({
            "season": [2026],
            "snapshot_date": [date(2026, 9, 14)],
            "team": ["BUF"],
            **{
                column: [None]
                for column in ANALYTICS_COLUMNS
                if column not in {"season", "snapshot_date", "team"}
            }
        })

        refresh_team_analytics("2026", "2026-09-14", analytics)

        cursor.execute.assert_called_once()
        self.assertEqual(
            cursor.execute.call_args.args[1],
            {"season": "2026", "snapshot_date": "2026-09-14"}
        )
        cursor.executemany.assert_called_once()
        connection.commit.assert_called_once()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()