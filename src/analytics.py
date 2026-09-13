import polars as pl


def calculate_team_analytics(
    play_by_play: pl.DataFrame,
    season: int,
    snapshot_date: str
) -> pl.DataFrame:
    offensive_plays = play_by_play.filter(
        pl.col("posteam").is_not_null()
        & pl.col("defteam").is_not_null()
        & pl.col("epa").is_not_null()
        & (
            (pl.col("pass_attempt") == 1)
            | (pl.col("rush_attempt") == 1)
        )
    )

    # -------------------------
    # Offensive analytics
    # -------------------------

    offense = (
        offensive_plays
        .group_by("posteam")
        .agg(
            pl.len().alias("plays"),

            pl.col("epa")
            .mean()
            .alias("epa_per_play"),

            pl.when(
                pl.col("pass_attempt") == 1
            )
            .then(pl.col("epa"))
            .otherwise(None)
            .mean()
            .alias("pass_epa_per_play"),

            pl.when(
                pl.col("rush_attempt") == 1
            )
            .then(pl.col("epa"))
            .otherwise(None)
            .mean()
            .alias("rush_epa_per_play"),

            pl.col("success")
            .mean()
            .alias("success_rate"),

            (
                pl.col("yards_gained") >= 20
            )
            .cast(pl.Float64)
            .mean()
            .alias("explosive_play_rate"),

            pl.col("pass_attempt")
            .mean()
            .alias("pass_rate")
        )
        .rename({
            "posteam": "team"
        })
    )

    # -------------------------
    # Defensive analytics
    # -------------------------

    defense = (
        offensive_plays
        .group_by("defteam")
        .agg(
            pl.len().alias("def_plays"),

            pl.col("epa")
            .mean()
            .alias("def_epa_per_play"),

            pl.when(
                pl.col("pass_attempt") == 1
            )
            .then(pl.col("epa"))
            .otherwise(None)
            .mean()
            .alias("def_pass_epa_per_play"),

            pl.when(
                pl.col("rush_attempt") == 1
            )
            .then(pl.col("epa"))
            .otherwise(None)
            .mean()
            .alias("def_rush_epa_per_play"),

            pl.col("success")
            .mean()
            .alias("def_success_rate_allowed"),

            (
                pl.col("yards_gained") >= 20
            )
            .cast(pl.Float64)
            .mean()
            .alias(
                "def_explosive_play_rate_allowed"
            )
        )
        .rename({
            "defteam": "team"
        })
    )

    # Every offensive play has both an offense
    # and a defense, so the two sets should align.
    team_analytics = (
        offense
        .join(
            defense,
            on="team",
            how="inner"
        )
        .with_columns(
            pl.lit(season)
            .alias("season"),

            pl.lit(snapshot_date)
            .str.to_date("%Y-%m-%d")
            .alias("snapshot_date")
        )
        .select(
            "season",
            "snapshot_date",
            "team",

            # Offense
            "plays",
            "epa_per_play",
            "pass_epa_per_play",
            "rush_epa_per_play",
            "success_rate",
            "explosive_play_rate",
            "pass_rate",

            # Defense
            "def_plays",
            "def_epa_per_play",
            "def_pass_epa_per_play",
            "def_rush_epa_per_play",
            "def_success_rate_allowed",
            "def_explosive_play_rate_allowed"
        )
        .sort(
            "epa_per_play",
            descending=True
        )
    )

    return team_analytics